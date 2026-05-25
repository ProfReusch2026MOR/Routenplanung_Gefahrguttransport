# Heuristic Design for Hazardous Materials Vehicle Routing

## 1. Purpose and Project Context

This document describes the planned heuristic method for our project **Hazardous Materials Vehicle Routing Optimization (HMVRP)**.

The decision maker is a **transport company or logistics planner** (`Transportunternehmen bzw. Logistikplaner`). The planner has to decide:

- which electric truck is assigned to which hazardous-material delivery;
- which permitted path through the road network is used for each delivery;
- how risk and transport cost are balanced in the final plan.

The current MILP notebook in `dist/Model_MILP_Gefahrgut_DE.ipynb` gives an important direction for the heuristic. The model is not a classic depot-customer-depot CVRP tour model. Instead, each delivery `l` has:

- an origin node `O_l`;
- a destination node `D_l`;
- a demand `Dem_l`;
- a hazardous-material class `Class_l`.

The route decision is therefore a **network path decision for each delivery**, combined with a **vehicle assignment decision**. To stay consistent with the solver, the heuristic should follow the same structure.

In short:

> For every hazardous-material delivery, find a legally allowed low-risk path from origin to destination and assign the delivery to a suitable electric truck, while respecting vehicle capacity, battery range, ADR restrictions, and transport cost.

## 2. Problem Class and Routing Difficulty

The main OR problem class is still the **Vehicle Routing Problem (VRP)** family, because vehicles have to be assigned to transport tasks under capacity and routing constraints.

More precisely, our project is a **Hazardous Materials Vehicle Routing Problem (HMVRP)** with a strong **multi-commodity network flow** character:

- each delivery behaves like one commodity moving from `O_l` to `D_l`;
- every selected edge contributes risk and cost;
- edges may be forbidden for specific hazardous-material classes;
- each delivery must be assigned to exactly one vehicle;
- each vehicle has payload capacity and battery range.

The problem is difficult because the safest path is not always the cheapest path, and the cheapest vehicle assignment is not always feasible. For example, an electric truck may be cheap but have insufficient range for a long path, or a short road segment may be forbidden for a specific ADR class.

Important constraints are:

- **Transportpflicht:** every delivery must be transported exactly once;
- **Fahrzeugkapazitaet:** total assigned delivery weight must not exceed vehicle payload;
- **ADR / Gefahrgut restrictions:** edges are allowed only for compatible hazardous-material classes;
- **Road-network logic:** routes must be connected paths from origin to destination;
- **Battery range:** route distance must fit the assigned electric truck range;
- **Limited fleet:** only available vehicles can be used.

## 3. Literature-Based Motivation

The literature summary gives the logic behind the heuristic. The main lesson is that hazardous-material routing should not be reduced to distance minimization. Risk must be visible in the data, the objective, and the final comparison.

### Erkut and Verter (1998): Risk Must Be Explicit

Erkut and Verter show that the definition of risk can strongly influence the selected route. For our project, this means that risk cannot be hidden inside a generic travel cost.

How this shapes our heuristic:

- each edge should have an explicit risk score;
- path selection should use risk directly;
- the output should report risk and cost separately.

### Holeczek (2019): HMVRP Is Different From Standard VRP

Holeczek helps place the project in the hazmat routing literature. Hazardous-material truck routing is different from normal delivery routing because legal restrictions, accident consequences, population exposure, and environmental effects matter.

How this shapes our heuristic:

- prohibited edges are infeasible, not just expensive;
- ADR class compatibility must be checked during path generation;
- the heuristic should be described as HMVRP-specific.

### Zografos and Androutsopoulos (2004): Risk and Cost Together

Zografos and Androutsopoulos treat hazardous-material distribution as a problem with both risk and cost. This matches our project because the planner wants safe routes but cannot ignore operating cost.

How this shapes our heuristic:

- use a weighted risk-cost score for path selection;
- keep risk and cost as separate reporting metrics;
- use weight changes later for sensitivity analysis.

### Androutsopoulos and Zografos (2012): Path Choice Matters

This work is useful because it separates the idea of delivery planning from the actual path through the network. In our project, this is very relevant: each delivery has an origin and destination, and the heuristic must choose the path between them.

How this shapes our heuristic:

- generate candidate paths for each delivery;
- evaluate these paths using edge risk, cost, permission, and distance;
- then combine path choice with vehicle assignment.

### Bula et al. (2016): Solver Structure and Vehicle Assignment

Bula et al. support the MILP-style view with routing variables and vehicle assignment variables. Our group member's notebook follows a similar idea: routing is represented by delivery-edge flow variables, and assignment is represented by delivery-vehicle variables.

How this shapes our heuristic:

- keep path selection and vehicle assignment connected but modular;
- include capacity and activation logic for vehicles;
- compare heuristic output with the same quantities as the solver.

### Bula et al. (2017): Improvement Through Neighborhoods

Bula et al. use neighborhood search for HMVRP. We do not need a full VNS as a first step, but the idea of improving a feasible solution by local changes is useful.

How this shapes our heuristic:

- start with a feasible path-and-assignment solution;
- improve it by changing one delivery path, moving a delivery to another vehicle, or swapping vehicle assignments;
- accept only changes that keep all constraints feasible.

### Cuneo et al. (2018): Practical Risk Index

Cuneo et al. use a practical risk index for hazardous-material logistics. This fits our project because the MILP notebook defines edge risk from population density, accident rate, and nature reserve proximity.

How this shapes our heuristic:

- use the same edge risk logic as the MILP;
- avoid artificial route choices that ignore the meaning of the risk score;
- make the safety-cost trade-off visible in experiments.

## 4. Consistency With the Current MILP Model

The heuristic should be aligned with the current MILP structure.

### MILP Sets

- `V`: available electric trucks;
- `L`: hazardous-material deliveries;
- `N`: road network nodes;
- `E`: directed road edges;
- `K`: hazardous-material classes.

### MILP Parameters Relevant for the Heuristic

- `Cap_v`: payload capacity of vehicle `v`;
- `FC_v`: fixed cost of using vehicle `v`;
- `VC_{v,e}`: variable cost of vehicle `v` on edge `e`;
- `Dem_l`: weight of delivery `l`;
- `Class_l`: hazardous-material class of delivery `l`;
- `O_l`, `D_l`: origin and destination of delivery `l`;
- `Risk_{e,k}`: risk score of edge `e` for hazardous-material class `k`;
- `Allow_{e,k}`: permission flag for edge `e` and class `k`;
- `Dist_e`: edge distance;
- `Range_v`: battery range of vehicle `v`.

### MILP Decisions to Mirror

The solver uses:

- `f_{l,e}`: whether delivery `l` uses edge `e`;
- `y_{l,v}`: whether delivery `l` is assigned to vehicle `v`;
- `z_v`: whether vehicle `v` is active.

The heuristic should return the same type of information:

- selected path edges for each delivery;
- assigned vehicle for each delivery;
- active vehicles;
- risk, cost, distance, and feasibility status.

## 5. Risk and Cost Definition

The MILP notebook defines the edge risk score as a weighted sum:

```text
Risk_{e,k} =
    alpha * PopDens_e
    + beta * AccRate_e
    + gamma * NatRes_e
```

with:

```text
alpha + beta + gamma = 1
```

This is more consistent with the current project than the earlier multiplicative risk formula. Therefore, the heuristic should use the same risk score.

The variable cost for vehicle `v` on edge `e` is:

```text
VC_{v,e} =
    Dist_e * km_cost_v
    + Dist_e * energy_kwh_per_km_v * energy_price_e
```

The objective should follow the same idea as the solver: a normalized weighted sum of risk and cost.

For heuristic scoring, a practical path score for delivery `l` and vehicle `v` is:

```text
score(l, v, path) =
    w1 * normalized_path_risk(l, path)
    + w2 * normalized_vehicle_cost(v, path)
```

where:

```text
path_risk(l, path) = sum Risk_{e, Class_l} over all edges e in path
path_cost(v, path) = fixed_cost_share_v + sum VC_{v,e} over all edges e in path
path_distance(path) = sum Dist_e over all edges e in path
```

The fixed vehicle cost `FC_v` should be counted once if a vehicle is used, not once per delivery. During construction, we can approximate it with an activation penalty when opening a new vehicle.

## 6. Selected Heuristic Method

The recommended heuristic is:

> **Risk-cost candidate path heuristic with vehicle-assignment local search.**

This better matches the current MILP than a classic customer-insertion route heuristic.

The method has three phases:

1. Generate feasible candidate paths for each delivery.
2. Construct an initial vehicle assignment using the best feasible path-vehicle combinations.
3. Improve the solution by changing paths or reassigning deliveries between vehicles.

## 7. Phase 1: Candidate Path Generation

For each delivery `l`, the heuristic generates several candidate paths from `O_l` to `D_l`.

Before path search, remove all edges that are forbidden for the delivery class:

```text
Allow_{e, Class_l} = 0  =>  edge e cannot be used for delivery l
```

For the remaining edges, define a delivery-specific edge score:

```text
edge_score_{l,e} =
    w1 * Risk_{e, Class_l}
    + w2 * average_cost_e
```

`average_cost_e` can be the average variable cost across vehicles or a normalized distance-based cost. This keeps path generation independent from the later vehicle assignment.

Then generate candidate paths such as:

- lowest-risk path;
- lowest-cost or shortest path;
- lowest weighted risk-cost path;
- a few alternative paths from k-shortest path logic.

Each candidate path stores:

- list of edges;
- total distance;
- total risk for the delivery class;
- whether it is legally permitted;
- possible vehicles that can cover its distance.

If no permitted path exists from `O_l` to `D_l`, the heuristic reports the delivery as infeasible.

## 8. Phase 2: Initial Vehicle Assignment

After candidate paths are available, the heuristic assigns deliveries to vehicles.

### Delivery Priority

Deliveries that are harder to place should be handled early. A useful priority order is:

```text
priority_l =
    normalized_demand_l
    + normalized_min_path_distance_l
    + normalized_min_path_risk_l
    + penalty_if_few_feasible_vehicles
```

This means:

- heavy deliveries are assigned early because of capacity;
- long deliveries are assigned early because of battery range;
- high-risk deliveries are handled carefully;
- deliveries with few feasible vehicles should not be left until the end.

### Best Feasible Assignment Step

For each delivery `l` in priority order:

1. try all candidate paths for `l`;
2. try all vehicles `v`;
3. keep only combinations where:
   - `Dem_l` fits into remaining capacity of vehicle `v`;
   - path distance is within `Range_v`;
   - all path edges are allowed for `Class_l`;
4. choose the feasible combination with the lowest incremental score.

The incremental score includes:

```text
incremental_score =
    w1 * path_risk
    + w2 * path_variable_cost
    + activation_penalty_if_vehicle_not_yet_used
```

If no vehicle-path combination is feasible, the heuristic reports that it could not construct a feasible full solution.

## 9. Phase 3: Local Search Improvement

The initial solution is feasible but may not be high quality. Local search improves it using small changes.

### Move 1: Alternative Path Switch

For one delivery, replace the current path with another candidate path.

Accept the move if:

- the new path is allowed for the delivery class;
- the assigned vehicle range is still sufficient;
- the weighted objective improves.

This move directly improves the network routing part.

### Move 2: Reassign Delivery to Another Vehicle

Move one delivery from vehicle `v1` to vehicle `v2`.

Accept the move if:

- capacity of `v2` is sufficient;
- range of `v2` is sufficient for the selected path;
- total cost and risk objective improves;
- fixed vehicle cost logic is updated correctly.

This move improves the vehicle-allocation part.

### Move 3: Swap Two Delivery Assignments

Swap the assigned vehicles of two deliveries.

Accept the move if:

- both vehicles remain within capacity;
- both vehicles can cover their assigned path distances;
- total objective improves.

This helps when a single reassignment is blocked but a paired exchange is feasible.

### Move 4: Path-and-Vehicle Combined Change

For one delivery, change both the path and the assigned vehicle at the same time.

This is useful because a low-risk path may be longer and therefore require a different electric truck with sufficient range.

## 10. Constraint Handling

### Transport Duty

Every delivery must be assigned exactly once:

```text
each l in L has exactly one selected vehicle and one selected path
```

### Vehicle Capacity

For each vehicle:

```text
sum Dem_l for deliveries assigned to v <= Cap_v
```

### Vehicle Activation

A vehicle is active if at least one delivery is assigned to it:

```text
z_v = 1 if any delivery l uses vehicle v
```

Fixed cost is counted only for active vehicles.

### Hazardous-Material Restrictions

For every edge in a selected path:

```text
Allow_{e, Class_l} = 1
```

Forbidden edges are hard constraints and cannot be used.

### Network Feasibility

Each selected path must be a connected path from origin to destination:

```text
O_l -> ... -> D_l
```

This replaces the classic depot-customer-depot route assumption.

### Battery Range

For each delivery and its assigned vehicle:

```text
path_distance_l <= Range_v
```

Charging stops are not part of the first heuristic version. They can be added later if the model includes charging infrastructure.

## 11. Output of the Heuristic

The heuristic should output:

- assigned vehicle for each delivery;
- selected path for each delivery;
- active vehicles;
- total assigned demand per vehicle;
- remaining capacity per vehicle;
- distance per delivery path;
- risk per delivery path;
- variable cost per delivery path;
- fixed vehicle cost;
- total normalized objective;
- feasibility status;
- runtime.

This output is directly comparable with the MILP result:

- `y_{l,v}` corresponds to the heuristic vehicle assignment;
- `f_{l,e}` corresponds to the selected path edges;
- `z_v` corresponds to active vehicles.

## 12. Feasibility Validation

A separate validation step should check:

- every delivery has exactly one vehicle;
- every delivery has exactly one connected origin-destination path;
- no forbidden edge is used;
- vehicle capacities are respected;
- vehicle ranges are respected;
- fixed costs are counted only for active vehicles;
- total risk, distance, cost, and objective are recomputed from the selected paths.

This is important because the heuristic solution should be credible when compared with the solver.

## 13. Comparison With the Solver

The heuristic should be compared with the MILP on the same data.

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
- solver MIP gap or best bound;
- heuristic gap compared with the solver result or bound.

If the solver proves optimality:

```text
heuristic_gap_percent =
    (heuristic_objective - solver_objective)
    / solver_objective
    * 100
```

If the solver does not prove optimality, the report should clearly state whether the heuristic is compared against the solver incumbent or the solver lower bound.

## 14. Pseudocode

```text
Input:
    vehicles V, deliveries L, nodes N, edges E,
    demand Dem_l, class Class_l, origins O_l, destinations D_l,
    risk Risk_{e,k}, permission Allow_{e,k},
    distance Dist_e, range Range_v, capacity Cap_v,
    fixed cost FC_v, variable cost VC_{v,e},
    weights w1 and w2

For each delivery l:
    remove edges e where Allow_{e, Class_l} = 0
    generate candidate paths from O_l to D_l
    store path risk, distance, and edge list
    if no candidate path exists:
        return infeasible

Sort deliveries by priority:
    high demand, long path, high risk, few feasible vehicles first

Initialize:
    no vehicle is active
    all capacities are unused
    no delivery is assigned

For each delivery l in priority order:
    best_choice = None
    for each candidate path p of delivery l:
        for each vehicle v:
            if capacity and range are feasible:
                compute incremental risk-cost score
                update best_choice if score is lower
    if best_choice exists:
        assign delivery l to vehicle v and path p
        update capacity and vehicle activation
    else:
        return infeasible

Local search:
    repeat:
        try alternative path switch
        try delivery reassignment
        try swap of vehicle assignments
        try combined path-and-vehicle change
        accept only feasible improving moves
    until no improvement or limit reached

Validate:
    check assignment, paths, ADR restrictions, capacity, range, cost, risk

Output:
    selected paths, vehicle assignments, active vehicles,
    objective, risk, cost, runtime, feasibility status
```

## 15. Why This Heuristic Fits Better Than the Earlier Route-Insertion Idea

An earlier idea was a classic customer insertion heuristic:

```text
depot -> customer 1 -> customer 2 -> depot
```

This is useful for a capacitated delivery tour problem, but the current MILP notebook models each delivery as an origin-destination flow:

```text
O_l -> ... -> D_l
```

Therefore, the heuristic should not focus first on inserting customers into depot tours. It should first choose feasible network paths for deliveries and then assign these deliveries to vehicles. This makes the heuristic consistent with:

- the flow variables `f_{l,e}`;
- the assignment variables `y_{l,v}`;
- the activation variables `z_v`;
- the ADR edge restrictions `Allow_{e,k}`;
- the electric truck range constraint.

## 16. Review Meeting Explanation

For the review meeting, the heuristic can be explained as follows:

> Our MILP model treats each hazardous-material delivery as a flow from its origin to its destination and assigns each delivery to an electric truck. Therefore, our heuristic follows the same logic. First, for every delivery, we generate several legally allowed candidate paths through the road network, using edge risk values based on population density, accident rate, and nature reserve proximity. Then we assign each delivery to a feasible electric truck while checking payload capacity and battery range. After that, local search improves the solution by switching paths, reassigning deliveries, or swapping vehicle assignments. This gives us a fast method that is directly comparable with the solver in terms of selected edges, vehicle assignment, active vehicles, risk, cost, runtime, and feasibility.
