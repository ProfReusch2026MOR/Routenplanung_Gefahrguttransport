# Heuristic Design for Hazardous Materials Vehicle Routing

## 1. Scope

This document defines the heuristic for the routing-and-assignment part of the project.

Each delivery `l` is treated as an origin-destination task with `O_l`, `D_l`, `Dem_l`, and `Class_l`. The heuristic therefore chooses one feasible network path for each delivery and assigns that delivery to a suitable electric truck. It does not build a classic depot-customer-depot tour.

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
- edges carry distance, risk, cost, and permission information;
- vehicles have capacity, fixed cost, variable cost, and battery range;
- a feasible solution can be represented by selected path edges, vehicle assignments, and active vehicles.

This makes the heuristic easy to compare with the solver while still keeping the implementation manageable.

## 4. Input Data

The heuristic uses the same conceptual data as the mathematical model.

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
- `VC_{v,e}`: variable cost on edge `e`, based on distance and energy cost.

### Edge Data

For each directed edge `e` and hazardous-material class `k`:

- `Dist_e`: distance;
- `Risk_{e,k}`: risk score;
- `Allow_{e,k}`: 1 if edge `e` is allowed for class `k`, otherwise 0.

## 5. Risk and Cost Scoring

The heuristic should use the same risk idea as the model. A practical edge risk score is:

```text
Risk_{e,k} =
    alpha * PopDens_e
    + beta * AccRate_e
    + gamma * NatRes_e
```

where:

- `PopDens_e` represents population exposure;
- `AccRate_e` represents accident exposure;
- `NatRes_e` represents proximity to sensitive natural areas;
- `alpha + beta + gamma = 1`.

The variable vehicle cost on an edge can be scored as:

```text
VC_{v,e} =
    Dist_e * km_cost_v
    + Dist_e * energy_kwh_per_km_v * energy_price_e
```

For one delivery `l`, vehicle `v`, and candidate path `p`, the heuristic score is:

```text
score(l, v, p) =
    w1 * normalized_path_risk(l, p)
    + w2 * normalized_path_cost(v, p)
    + activation_penalty(v)
```

with:

```text
path_risk(l, p) = sum Risk_{e, Class_l} for all e in p
path_cost(v, p) = sum VC_{v,e} for all e in p
path_distance(p) = sum Dist_e for all e in p
```

The activation penalty is used only when a previously unused vehicle becomes active. This keeps fixed vehicle cost from being counted multiple times.

## 6. Phase 1: Candidate Path Generation

For each delivery `l`, generate candidate paths from `O_l` to `D_l`.

Before searching for paths, remove all edges that are not allowed for the delivery class:

```text
Allow_{e, Class_l} = 0  =>  edge e is not available
```

Then generate a small path set, for example:

- one lowest-risk path;
- one lowest-cost or shortest path;
- one weighted risk-cost path;
- a few alternatives from k-shortest path logic, if available.

Each candidate path stores:

- edge sequence;
- total distance;
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
    + normalized_min_path_distance_l
    + normalized_min_path_risk_l
    + penalty_if_few_feasible_vehicles
```

For each delivery in this order:

1. test all candidate paths;
2. test all vehicles;
3. keep only combinations where:
   - `Dem_l` fits into the remaining capacity of vehicle `v`;
   - `path_distance(p) <= Range_v`;
   - all path edges are allowed for `Class_l`;
4. choose the feasible path-vehicle combination with the lowest incremental score.

If no feasible combination exists, the heuristic returns infeasible for the current instance.

## 8. Phase 3: Local Search Improvement

The initial solution is feasible, but not necessarily good. Local search tries small changes and accepts them only if they improve the score and keep all constraints feasible.

### Alternative Path Switch

For one delivery, replace the current path with another candidate path.

This can reduce risk or cost without changing the assigned vehicle.

### Vehicle Reassignment

Move one delivery from its current vehicle to another vehicle.

This can reduce cost, improve capacity usage, or avoid using an additional vehicle. The move is accepted only if the target vehicle has enough remaining capacity and range.

### Assignment Swap

Swap the assigned vehicles of two deliveries.

This can help when two single reassignments are infeasible separately, but feasible together.

### Combined Path-and-Vehicle Change

Change both the path and the vehicle for one delivery.

This is useful when a safer path is longer and therefore needs a vehicle with a larger range.

## 9. Feasibility Checks

The heuristic must validate the solution after construction and after local search.

Checks:

- every delivery has exactly one selected path;
- every delivery is assigned to exactly one vehicle;
- every selected path connects `O_l` to `D_l`;
- no selected edge violates `Allow_{e, Class_l}`;
- vehicle capacity is respected:

```text
sum Dem_l for deliveries assigned to v <= Cap_v
```

- battery range is respected:

```text
path_distance_l <= Range_v
```

- fixed cost is counted only for active vehicles;
- total risk and total cost are recomputed from the selected paths.

Charging stops are not part of the first heuristic version. The first version only checks whether a selected path fits the assigned vehicle range. Charging infrastructure can be added later as an extension.

## 10. Output

The heuristic should return:

- selected path for each delivery;
- assigned vehicle for each delivery;
- active vehicles;
- total assigned demand per vehicle;
- remaining capacity per vehicle;
- distance per delivery;
- risk per delivery;
- variable cost per delivery;
- fixed vehicle cost;
- total risk;
- total cost;
- normalized objective value;
- feasibility status;
- runtime.

These outputs are enough to compare the heuristic with the solver result:

- selected edges correspond to routing decisions;
- vehicle assignments correspond to assignment decisions;
- active vehicles correspond to vehicle activation.

## 11. Solver Comparison

The heuristic should be compared with the solver on the same instances and the same objective interpretation.

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
- heuristic gap compared with the solver objective or bound.

If the solver proves optimality:

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
    distance Dist_e, range Range_v, capacity Cap_v,
    fixed cost FC_v, variable cost VC_{v,e},
    weights w1 and w2

For each delivery l:
    remove edges where Allow_{e, Class_l} = 0
    generate candidate paths from O_l to D_l
    calculate risk, distance, and cost for each path
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
        update vehicle capacity and activation

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
