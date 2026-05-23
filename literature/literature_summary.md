# Literature Summary for Hazardous Materials Vehicle Routing

## Project Direction

Our project focuses on route planning for hazardous-material transports. The decision maker is a transport company or logistics planner who must decide:

- which vehicle serves which delivery;
- which route each vehicle should take;
- how deliveries are planned while respecting legal, technical, and logistical restrictions.

The main objective is to minimize the total risk caused by hazardous-material transportation. In our project, risk is understood as a route-dependent value that can combine:

- population density along the route;
- accident probability on road segments;
- proximity to critical infrastructure;
- general hazard potential of the route.

At the same time, the logistics planner cannot ignore transport cost. Therefore, cost is treated as a secondary objective, including factors such as distance, travel time, energy consumption, and tolls.

In simple words, the project asks:

> How can hazardous-material deliveries be assigned to vehicles and routed through a permitted road network so that total risk is as low as possible while transport costs remain reasonable?

## OR Problem Class

The project belongs mainly to the Vehicle Routing Problem (VRP) family. More precisely, it is a Hazardous Materials Vehicle Routing Problem (HMVRP), because the transported goods create additional safety and regulatory constraints that do not appear in a normal delivery VRP.

It can also be interpreted as a multi-objective network flow problem:

- vehicles move through a network of nodes and arcs;
- every delivery must be transported;
- only valid and permitted arcs may be used;
- the chosen flow of vehicles creates both risk and cost.

This classification is important because the project is not only about finding short routes. A short route through a dense city center, tunnel, or area close to critical infrastructure may be cheap but unsafe. A safer route may be longer and more expensive. This risk-cost conflict is the central OR trade-off.

## Core Literature

### Erkut and Verter (1998)

**Reference:** Erkut, E., and Verter, V. (1998). Modeling of Transport Risk for Hazardous Materials. Operations Research, 46(5), 625-642. https://doi.org/10.1287/opre.46.5.625

This paper is useful because it explains why risk modeling is a central issue in hazardous-material transport. The authors show that different definitions of transport risk can lead to different "best" routes. This is directly relevant for our project: we cannot simply say that the safest route is the shortest route.

For our model, this paper supports the idea that risk should be explicitly calculated for each road segment. A practical project-level risk value can be based on accident probability, population exposure, and route hazard factors. The paper also reminds us to describe our risk function clearly, because it is a modeling assumption, not a universal truth.

### Holeczek (2019)

**Reference:** Holeczek, N. (2019). Hazardous materials truck transportation problems: A classification and state of the art literature review. Transportation Research Part D: Transport and Environment, 69, 305-328. https://doi.org/10.1016/j.trd.2019.02.010

This review gives the broader academic context for hazardous-material truck routing. It shows that hazmat routing is treated separately from standard transport planning because safety, regulation, population exposure, and environmental consequences matter.

For our project, this source helps us explain the problem class. It supports calling our topic HMVRP and helps justify why our constraints include road restrictions, prohibited areas, and hazardous-material-specific permissions. It is also useful for discussing limitations, especially if we use generated data instead of complete real-world accident and population datasets.

### Zografos and Androutsopoulos (2004)

**Reference:** Zografos, K. G., and Androutsopoulos, K. N. (2004). A heuristic algorithm for solving hazardous materials distribution problems. European Journal of Operational Research, 152(2), 507-519. https://doi.org/10.1016/S0377-2217(03)00041-9

This paper is closely connected to our planned heuristic part. It describes hazardous-material distribution as a bi-objective routing problem where risk and cost both matter. The paper also proposes a heuristic approach for solving hazardous-material distribution problems.

For our project, this supports a simple and explainable heuristic design: build feasible routes step by step, insert deliveries where they create the smallest weighted increase in risk and cost, and then improve the result with local search. This fits our coursework setting because the method is understandable, implementable, and still clearly connected to the literature.

### Androutsopoulos and Zografos (2012)

**Reference:** Androutsopoulos, K. N., and Zografos, K. G. (2012). A bi-objective time-dependent vehicle routing and scheduling problem for hazardous materials distribution. EURO Journal on Transportation and Logistics, 1, 157-183. https://doi.org/10.1007/s13676-012-0004-y

This paper extends the hazmat routing idea by considering time-dependent travel conditions and delivery scheduling. It formulates the problem as a bi-objective vehicle routing and scheduling problem with time windows.

For our project, the most important insight is that hazardous-material routing can involve two connected decisions: the order of deliveries and the actual path between them. In a simplified model, we can precompute risk and cost between relevant nodes and then solve the vehicle routing problem on this reduced network. If we later include time windows or route duration limits, this paper gives a strong reference.

### Bula et al. (2016)

**Reference:** Bula, G. A., Gonzalez, F. A., Prodhon, C., Afsar, H. M., and Velasco, N. M. (2016). Mixed Integer Linear Programming Model for Vehicle Routing Problem for Hazardous Materials Transportation. IFAC-PapersOnLine, 49(12), 966-971. https://doi.org/10.1016/j.ifacol.2016.07.691

This paper is useful for the solver-based side of the project. It presents a mixed-integer linear programming model for hazardous-material vehicle routing and discusses risk minimization in a heterogeneous vehicle setting.

For our project, it supports using a MILP-style model with binary route decisions, vehicle capacity constraints, and a risk-based objective. The paper also discusses load-dependent risk. We can start with a simpler fixed arc-risk model and mention load-dependent risk as a possible extension if the basic model is already working.

### Bula et al. (2017)

**Reference:** Bula, G. A., Prodhon, C., Gonzalez, F. A., Afsar, H. M., and Velasco, N. (2017). Variable neighborhood search to solve the vehicle routing problem for hazardous materials transportation. Journal of Hazardous Materials, 324, 472-480. https://doi.org/10.1016/j.jhazmat.2016.11.015

This paper is especially relevant for the heuristic part. It applies Variable Neighborhood Search (VNS) to a hazardous-material vehicle routing problem. The risk depends on vehicle load, vehicle type, and exposed population.

For our project, a full VNS may be more complex than necessary, but the idea of improving an initial solution through neighborhoods is very useful. We can implement a smaller version with common local search moves such as 2-opt, relocate, and swap. This gives us a meaningful heuristic without making the project too hard to explain.

### Cuneo et al. (2018)

**Reference:** Cuneo, V., Nigro, M., Carrese, S., Ardito, C. F., and Corman, F. (2018). Risk based, multi objective vehicle routing problem for hazardous materials: A test case in downstream fuel logistics. Transportation Research Procedia, 30, 43-52. https://doi.org/10.1016/j.trpro.2018.09.006

This paper is valuable because it is close to a practical logistics setting. It studies fuel distribution and uses a risk index based on population density and accident estimates. This matches our project idea very well because our risk components also include population density and accident probability.

For our project, this paper can guide the data model. Even if we generate artificial data, the generated risk values should have a realistic interpretation: road segments near dense population or risky infrastructure should receive higher risk values than remote or safer roads.

## How the Literature Shapes Our Model

### Decision variables

The literature supports decision variables that describe:

- whether vehicle `k` travels from node `i` to node `j`;
- whether customer or delivery `d` is served by vehicle `k`;
- possibly the load carried after visiting a node;
- possibly the arrival time at a customer, if time windows are included.

For a first implementation, binary arc variables and load variables are enough.

### Objective

The project should keep risk as the primary objective and cost as the secondary objective. A practical formulation is a weighted objective:

`minimize alpha * total_risk + beta * total_cost`

where:

- `total_risk` is the sum of risk values on used arcs;
- `total_cost` is based on distance, travel time, energy use, or tolls;
- `alpha` and `beta` control how strongly the model prefers safety over cost.

For experiments, we can test different weights to show how the selected routes change when the planner cares more about safety or more about cost.

### Risk calculation

A simple and explainable arc risk formula is:

`risk_ij = accident_probability_ij * population_exposure_ij * hazard_factor_ij`

The `hazard_factor_ij` can represent critical infrastructure, tunnel usage, dense residential areas, or other dangerous route properties.

Later extensions could include:

- vehicle type;
- remaining load;
- hazardous-material class;
- time-dependent traffic risk;
- route-specific legal restrictions.

### Constraints

The literature and project scope suggest the following core constraints:

- every delivery must be transported exactly once;
- vehicle capacity must not be exceeded;
- the number of available vehicles is limited;
- vehicles must move along valid network paths;
- prohibited road segments, tunnels, city centers, or residential areas must be excluded or penalized;
- roads may allow only specific hazardous-material classes;
- each route must start and end at the depot, unless the final model defines a different operational rule.

These constraints are what make the problem a real OR model instead of a normal shortest-path problem.

## Heuristic Direction

The planned heuristic should be simple enough to implement but still meaningful for HMVRP.

A suitable first version is a risk-aware insertion heuristic:

1. Start with empty routes for the available vehicles.
2. Sort deliveries by a priority score, for example high demand, high direct risk, or distance from the depot.
3. Insert each delivery into the feasible route position with the smallest increase in weighted risk and cost.
4. Respect capacity and road-permission constraints during insertion.
5. Improve the solution with local search:
   - 2-opt inside a route;
   - relocate one delivery to another route;
   - swap two deliveries between routes.

This heuristic is easy to explain in the review meeting: it imitates how a logistics planner might build routes, but it evaluates every insertion with a risk-cost score instead of distance only.

## Experiment Ideas

The experiments should show that the solver and the heuristic behave differently as the instance grows.

Suggested instance levels:

| Instance | Possible structure | Purpose |
|---|---:|---|
| Small | about 8-12 deliveries, 2 vehicles | Check whether the MILP model works and can prove optimality |
| Medium | about 25-40 deliveries, 4-6 vehicles | Compare solver quality and heuristic runtime |
| Large | about 70-100 deliveries, 8-12 vehicles | Show scalability limits of the solver and usefulness of the heuristic |

Important metrics:

- total risk;
- total cost;
- weighted objective value;
- runtime;
- solver status;
- MIP gap or best bound, if available;
- number of vehicles used;
- feasibility of all routes;
- heuristic gap compared with the solver solution or bound.

## Open Modeling Choices

Some decisions should be made consistently before implementation:

- Do we model cost as distance, travel time, energy use, tolls, or a weighted combination?
- Are forbidden roads completely removed, or are risky roads allowed with high penalties?
- Do we include time windows now, or only route duration limits?
- Is risk fixed per road segment, or does it increase with load and vehicle type?
- Do we use one weighted objective, or do we generate several trade-off solutions with different risk-cost weights?

For the current project scope, the most practical first version is:

- fixed arc risk;
- cost based mainly on distance or travel time;
- vehicle capacity and limited fleet;
- hard exclusion of forbidden road segments;
- weighted objective with different risk-cost settings for experiments.

## Short Review Meeting Explanation

Our literature review confirms that our topic belongs to the Hazardous Materials Vehicle Routing Problem. The decision maker is a logistics planner who must assign vehicles, select routes, and plan deliveries. The main objective is to reduce total transport risk, especially risk caused by population exposure, accident probability, critical infrastructure, and dangerous road segments. Transport cost is still important, but it is secondary to safety.

The literature also shows that hazardous-material routing is different from standard VRP because the shortest or cheapest route may be unacceptable for safety or legal reasons. Therefore, our model should use explicit risk values on road segments and include constraints for vehicle capacity, mandatory delivery service, limited fleet size, valid network paths, and hazardous-material road restrictions.

For the solver part, we plan a MILP-style capacitated HMVRP model. For the heuristic part, we plan a risk-aware insertion heuristic with local search. The experiments will compare both approaches on small, medium, and large instances using risk, cost, runtime, feasibility, and solver gap.

