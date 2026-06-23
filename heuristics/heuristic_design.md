# Heuristic Design for Hazardous Materials Vehicle Routing

## 1. Scope

This document defines the heuristic for the routing-and-assignment part of the project.

Each delivery `l` is treated as an independent one-way origin-destination task with `O_l`, `D_l`, `Dem_l`, and `Class_l`. The heuristic chooses one feasible network path and one suitable electric truck for that delivery. It does not calculate a return trip, schedule the order of several deliveries, or model vehicle repositioning between tasks. Payload capacity is released after unloading.

## 2. Selected Method

The selected method is a:

> **Risk-cost candidate path heuristic with vehicle-assignment local search.**

The idea is simple:

1. For every delivery, generate a small set of feasible candidate paths from `O_l` to `D_l`.
2. Assign each delivery-path combination to an electric truck while checking capacity and range.
3. Improve the first solution by switching paths or changing vehicle assignments.

This method fits the project because the routing decision and the vehicle decision are connected but can still be handled in understandable steps.

## 3. Why This Heuristic Fits

The method matches the current data and model structure:

- deliveries already have origin and destination nodes;
- edges carry length, risk, cost, and permission information;
- vehicles have capacity, fixed cost, variable cost, and battery range;
- a feasible solution can be represented by selected path edges, vehicle assignments, and active vehicles.

This makes the heuristic easy to compare with the solver while still keeping the implementation manageable.

## 4. Input Data

The heuristic uses the same conceptual data as the mathematical model.

The heuristic assumes that edge risk scores and legal feasibility parameters are provided by the data and model work packages. It does not derive legal restrictions itself; it uses `Risk_{e,k}` and `Allow_{e,k}` to build feasible paths and evaluate risk-cost trade-offs. Origin and destination coordinates must both map to an eligible road-network node within the agreed mapping threshold.

### Sets

- `V`: available electric trucks;
- `L`: hazardous-material deliveries;
- `N`: road network nodes;
- `E`: directed road edges;
- `K`: hazardous-material classes.

### Delivery Data

For each delivery `l`:

- `O_l`: origin node;
- `D_l`: destination node;
- `Dem_l`: delivery weight;
- `Class_l`: hazardous-material class.

### Vehicle Data

For each vehicle `v`:

- `Cap_v`: payload capacity;
- `Range_v`: battery range;
- `FC_v`: fixed cost if the vehicle is used;
- `VC_{v,e}`: variable cost on edge `e`, based on length and energy cost.

### Edge Data

For each directed edge `e` and hazardous-material class `k`:

- `Len_e`: edge length;
- `Risk_{e,k}`: risk score;
- `Allow_{e,k}`: 1 if edge `e` is allowed for class `k`, otherwise 0.

## 5. Risk and Cost Scoring

The heuristic should use the same risk idea as the model. A practical edge risk score is:

```text
BaseRiskRate_e =
    0.40 * PopRate_e
    + 0.40 * AccRate_e
    + 0.20 * NatRate_e

RiskRate_{e,k} = min(1, BaseRiskRate_e * HazardFactor_k)
Risk_{e,k} = RiskRate_{e,k}
```

where:

- `PopRate_e` is the min-max normalized `pop_per_meter` value;
- `AccRate_e` is the min-max normalized accident `score`, which the current data defines as accidents divided by the accident-edge length;
- `NatRate_e` is `1 - minmax(dist_to_nature_m)`, so shorter distance to a protected area means higher risk;
- `HazardFactor_k` uses the agreed class multipliers, such as `2.0` for class `1.1D`, `1.0` for class `3`, and `0.8` for class `2`.

This is a simplified solver-aligned edge risk index. The current comparison version does not multiply the risk score by `Len_e`, because the mathematical model snapshot uses the normalized edge score directly. Normalization uses the complete loaded regional edge data before SCC and OD cropping. The minima, maxima, source fields, transformations, and the missing length factor are recorded in the result metadata.

The variable vehicle cost on an edge can be scored as:

```text
VC_{v,e} =
    Len_e * km_cost_v
    + Len_e * energy_kwh_per_km_v * energy_price_e
```

The energy price is an explicit run parameter. For the current Berlin solver-comparison run, the heuristic can use `0.35 EUR/kWh` to match the solver snapshot.

For one delivery `l`, vehicle `v`, and candidate path `p`, the heuristic uses:

```text
incremental_cost(l, v, p) =
    path_cost(v, p)
    + FC_v

assignment_score(l, v, p) =
    w1 * path_risk(l, p) / fixed_path_risk_scale
    + w2 * incremental_cost(l, v, p) / fixed_cost_scale
```

with:

```text
path_risk(l, p) = sum Risk_{e, Class_l} for all e in p
path_cost(v, p) = sum VC_{v,e} for all e in p
path_length(p) = sum Len_e for all e in p
```

Both scales are calculated once from the complete candidate set and then kept fixed for the whole assignment run. Ties are resolved by assignment score, path risk, incremental cost, vehicle ID, and path label. Fixed vehicle cost is charged per delivery/trip to match the current solver snapshot.

## 6. Phase 1: Candidate Path Generation

For each delivery `l`, generate candidate paths from `O_l` to `D_l`.

Before searching for paths, remove all edges that are not allowed for the delivery class:

```text
Allow_{e, Class_l} = 0  =>  edge e is not available
```

Legal feasibility is a hard constraint. Forbidden edges are not high-cost alternatives. The current tunnel rule follows the shared A/B/C/D category matrix: classes `1.1D` and `1.5D` are forbidden in C/D tunnels, while classes `6` and `9` are forbidden in D tunnels.

The implementation supports two network modes. `full` searches the complete routing graph. `solver_cropped` first keeps the largest strongly connected component and then applies the solver OD bounding box with buffer `0.3` for each delivery. Original arc IDs are retained instead of contracting degree chains. Because cropping can remove a legal detour, this case is reported as `crop_infeasible`, not as full-network route infeasibility.

Then generate a small path set, for example:

- one lowest-risk path;
- one lowest-cost or shortest path;
- one weighted risk-cost path;
- a few alternatives from k-shortest path logic, if available.

The weighted path uses one pair of global scales for the complete run:

```text
weighted_edge_cost(e) =
    w1 * Risk_e / fixed_weighted_path_risk_scale
    + w2 * Len_e / fixed_weighted_path_length_scale
```

The scales are calculated once from the complete set of distance and risk candidates before weighted-path generation. They remain unchanged across all deliveries and permission masks and are recorded in the output metadata. This keeps the edge metric additive while making `w1` and `w2` meaningful across risk and distance units.

The current default is `w1 = 0.65` and `w2 = 0.35`. Both values are runtime parameters, must be non-negative, and must sum to `1.0`.

If variable cost differs strongly between vehicles, cost-based candidate paths can either use a vehicle-independent proxy cost or be generated separately for relevant vehicle types.

Each candidate path stores:

- edge sequence;
- total path length;
- total risk;
- total variable cost per vehicle;
- feasible vehicles based on range.

If no permitted path exists for a delivery, the heuristic marks the instance as infeasible.

## 7. Phase 2: Initial Vehicle Assignment

After candidate paths are generated, deliveries are assigned to vehicles.

Deliveries should be processed in a priority order so that difficult cases are handled early:

```text
priority_l =
    normalized_demand_l
    + normalized_min_path_length_l
    + normalized_min_path_risk_l
    + penalty_if_few_feasible_vehicles
```

For each delivery in this order:

1. test all candidate paths;
2. test all vehicles;
3. keep only combinations where:
   - `Dem_l <= Cap_v` for this independent delivery;
   - `path_length(p) <= Range_v`;
   - all path edges are allowed for `Class_l`;
4. choose the feasible path-vehicle combination with the lowest incremental score.

If no feasible combination exists, the heuristic returns infeasible for the current instance.

## 8. Phase 3: Local Search Improvement

The initial solution is feasible, but not necessarily good. Local search tries small changes and accepts them only if they improve the score and keep all constraints feasible.

These moves are chosen because they directly match the two decisions of the heuristic: path selection and vehicle assignment.

### Alternative Path Switch

For one delivery, replace the current path with another candidate path.

This can reduce risk or cost without changing the assigned vehicle.

The move is accepted only if the new path is connected from `O_l` to `D_l`, all edges are legally allowed, range remains feasible, and risk and cost are recomputed.

### Vehicle Reassignment

Move one delivery from its current vehicle to another vehicle.

This can reduce cost or avoid using an additional vehicle. The move is accepted only if the target vehicle can carry the delivery and cover the selected path length.

After the move, per-delivery capacity, range feasibility, vehicle activation, fixed cost, total risk, and total cost are updated.

### Assignment Swap

Swap the assigned vehicles of two deliveries.

This can help when two single reassignments are infeasible separately, but feasible together.

The swap is accepted only if both vehicles remain feasible after the exchange.

### Combined Path-and-Vehicle Change

Change both the path and the vehicle for one delivery.

This is useful when a safer path is longer and therefore needs a vehicle with a larger range.

This move is accepted only after checking path permission, path connectivity, vehicle capacity, range, trip fixed cost, and the updated objective value.

## 9. Feasibility Checks

The heuristic must validate the solution after construction and after local search.

Checks:

- every delivery has exactly one selected path;
- every delivery is assigned to exactly one vehicle;
- every selected path connects `O_l` to `D_l`;
- no selected edge violates `Allow_{e, Class_l}`;
- vehicle capacity is respected:

```text
Dem_l <= Cap_v
```

Each delivery is an independent one-way OD task. The vehicle unloads at `D_l`, after which its payload capacity is available for another delivery. The current heuristic does not schedule when deliveries occur, model repositioning between tasks, or add a return path.

- battery range is respected:

```text
path_length_l <= Range_v
```

- fixed cost is counted once for each selected delivery/trip;
- total risk and total cost are recomputed from the selected paths.

Charging stops are not included in the first heuristic version. A path is feasible only if its total length fits within the assigned vehicle range. This keeps the first implementation focused on path selection and vehicle assignment, while leaving charging decisions as a later extension.

## 10. Output

The heuristic should return:

- selected path for each delivery;
- assigned vehicle for each delivery;
- active vehicles;
- capacity feasibility per delivery;
- mapping status and coordinate-to-node distance;
- path length per delivery;
- risk per delivery;
- variable cost per delivery;
- fixed vehicle cost;
- risk normalization metadata and assignment scales;
- total risk;
- total cost;
- normalized objective value;
- feasibility status;
- data-preparation, network-preprocessing, mapping, candidate-generation, vehicle-assignment, export, algorithm, and end-to-end runtime;
- network mode, crop buffer, cropped edge counts, hazard factors, and active risk components.

The CSV/JSON files and solver-style text report prepare a later comparison:

- selected edges correspond to routing decisions;
- vehicle assignments correspond to assignment decisions;
- active vehicles are reported as used vehicle types, while fixed cost is charged per selected delivery/trip.

## 11. Solver Comparison

The heuristic should be compared with the solver on the same instances and the same objective interpretation. Solver-style formatting alone does not make the objective values directly comparable.

Useful metrics:

- feasibility status;
- total normalized objective;
- total risk;
- total transport cost;
- fixed cost and variable cost separately;
- runtime;
- active vehicles;
- capacity usage;
- solver status;
- solver bound or gap, if available;
- heuristic gap compared with the solver objective or bound, but only after both methods share the same evaluator and feasible network.

If the solver proves optimality on the same network and both results use the same objective definition:

```text
heuristic_gap_percent =
    (heuristic_objective - solver_objective)
    / solver_objective
    * 100
```

One important detail: the heuristic should calculate cost from the selected path edges. If the solver uses an approximation for variable cost, the comparison table should make clear which cost definition is used.

## 12. Pseudocode

```text
Input:
    vehicles V, deliveries L, nodes N, edges E,
    demand Dem_l, class Class_l, origins O_l, destinations D_l,
    risk Risk_{e,k}, permission Allow_{e,k},
    edge length Len_e, range Range_v, capacity Cap_v,
    fixed cost FC_v, variable cost VC_{v,e},
    weights w1 and w2

For each delivery l:
    remove edges where Allow_{e, Class_l} = 0
    generate candidate paths from O_l to D_l
    calculate risk, length, and cost for each path
    if no candidate path exists:
        return infeasible

Sort deliveries:
    high demand, long path, high risk, few feasible vehicles first

Construct initial solution:
    for each delivery l:
        test candidate path and vehicle combinations
        keep combinations satisfying capacity, range, and permission checks
        choose the lowest incremental score
        assign delivery to path and vehicle
        update vehicle activation

Improve solution:
    repeat:
        try path switch
        try vehicle reassignment
        try assignment swap
        try combined path-and-vehicle change
        accept only feasible improving moves
    until no improvement or limit reached

Validate:
    check path connectivity, assignment, permissions, capacity, range, risk, cost

Output:
    paths, vehicle assignments, active vehicles,
    risk, cost, objective, runtime, feasibility status
```

## 13. Dependencies and Next Steps

Implementation depends on a few project decisions becoming stable:

- finalized data format for nodes, edges, deliveries, vehicles, risks, and permissions;
- final objective weights `w1` and `w2`;
- solver output format for comparing selected edges, vehicle assignments, active vehicles, objective value, risk, and cost;
- small, medium, and large test instances.

The next practical steps are to finalize the shared risk and energy-price definitions, add charging-stop decisions for long routes, and run systematic solver-versus-heuristic experiments.
