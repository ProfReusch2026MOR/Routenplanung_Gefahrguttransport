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

For our project, this paper supports the idea that risk should be discussed explicitly instead of being hidden behind distance or travel time. It also reminds us that the final risk function is a modeling choice that the team should justify clearly.

### Holeczek (2019)

**Reference:** Holeczek, N. (2019). Hazardous materials truck transportation problems: A classification and state of the art literature review. Transportation Research Part D: Transport and Environment, 69, 305-328. https://doi.org/10.1016/j.trd.2019.02.010

This review gives the broader academic context for hazardous-material truck routing. It shows that hazmat routing is treated separately from standard transport planning because safety, regulation, population exposure, and environmental consequences matter.

For our project, this source helps us explain the problem class. It supports calling our topic HMVRP and helps justify why road restrictions, prohibited areas, and hazardous-material-specific permissions are relevant. It is also useful for discussing limitations, especially if complete real-world accident and population data are not available.

### Zografos and Androutsopoulos (2004)

**Reference:** Zografos, K. G., and Androutsopoulos, K. N. (2004). A heuristic algorithm for solving hazardous materials distribution problems. European Journal of Operational Research, 152(2), 507-519. https://doi.org/10.1016/S0377-2217(03)00041-9

This paper is closely connected to our planned heuristic part. It describes hazardous-material distribution as a bi-objective routing problem where risk and cost both matter. The paper also proposes a heuristic approach for solving hazardous-material distribution problems.

For our project, this paper is useful when discussing a possible heuristic direction. It suggests that a constructive route-building method can be a reasonable starting point, especially when risk and cost must both be considered.

### Androutsopoulos and Zografos (2012)

**Reference:** Androutsopoulos, K. N., and Zografos, K. G. (2012). A bi-objective time-dependent vehicle routing and scheduling problem for hazardous materials distribution. EURO Journal on Transportation and Logistics, 1, 157-183. https://doi.org/10.1007/s13676-012-0004-y

This paper extends the hazmat routing idea by considering time-dependent travel conditions and delivery scheduling. It formulates the problem as a bi-objective vehicle routing and scheduling problem with time windows.

For our project, the most important insight is that hazardous-material routing can involve two connected decisions: the order of deliveries and the actual path between them. If the team later includes time windows, travel-time effects, or route duration limits, this paper can provide a useful reference.

### Bula et al. (2016)

**Reference:** Bula, G. A., Gonzalez, F. A., Prodhon, C., Afsar, H. M., and Velasco, N. M. (2016). Mixed Integer Linear Programming Model for Vehicle Routing Problem for Hazardous Materials Transportation. IFAC-PapersOnLine, 49(12), 966-971. https://doi.org/10.1016/j.ifacol.2016.07.691

This paper is useful for the solver-based side of the project. It presents a mixed-integer linear programming model for hazardous-material vehicle routing and discusses risk minimization in a heterogeneous vehicle setting.

For our project, it supports the idea that a solver-based HMVRP model can be formulated with binary routing decisions, vehicle capacity constraints, and a risk-related objective. The paper also discusses load-dependent risk, which could be considered later if the team decides that this level of detail fits the project scope.

### Bula et al. (2017)

**Reference:** Bula, G. A., Prodhon, C., Gonzalez, F. A., Afsar, H. M., and Velasco, N. (2017). Variable neighborhood search to solve the vehicle routing problem for hazardous materials transportation. Journal of Hazardous Materials, 324, 472-480. https://doi.org/10.1016/j.jhazmat.2016.11.015

This paper is especially relevant for the heuristic part. It applies Variable Neighborhood Search (VNS) to a hazardous-material vehicle routing problem. The risk depends on vehicle load, vehicle type, and exposed population.

For our project, a full VNS may be more complex than necessary for the first milestone. However, the general idea of improving an initial route plan through neighborhood moves is relevant for discussing heuristic options.

### Cuneo et al. (2018)

**Reference:** Cuneo, V., Nigro, M., Carrese, S., Ardito, C. F., and Corman, F. (2018). Risk based, multi objective vehicle routing problem for hazardous materials: A test case in downstream fuel logistics. Transportation Research Procedia, 30, 43-52. https://doi.org/10.1016/j.trpro.2018.09.006

This paper is valuable because it is close to a practical logistics setting. It studies fuel distribution and uses a risk index based on population density and accident estimates. This matches our project idea very well because our risk components also include population density and accident probability.

For our project, this paper can guide the discussion of data assumptions. It shows how a practical risk index can connect accident estimates and population exposure, which fits our current understanding of route-based risk.

## Project Implications from the Literature

The literature does not decide the final model for us, but it gives useful guidance for the team discussion.

### Modeling direction

The reviewed papers support describing the problem as a risk-based HMVRP. The model should probably distinguish between risk and cost instead of using distance as the only objective. A simple risk idea that appears repeatedly in the literature is that road segments become more critical when accident probability and exposed population are high.

Possible modeling elements to discuss with the team:

- vehicle-route decisions on a network;
- delivery assignment and service constraints;
- vehicle capacity and limited fleet size;
- road permissions or prohibited arcs;
- a risk measure based on accident probability, population exposure, and route-specific hazard factors;
- a cost measure based on distance, travel time, energy use, tolls, or a combination of these.

### Heuristic direction

The heuristic literature suggests that a constructive route-building method combined with local improvement could be a realistic option for the project. This is not a final algorithm decision yet, but the following ideas appear suitable for further team discussion:

- build feasible routes step by step;
- evaluate candidate route changes with both risk and cost in mind;
- respect capacity and road-permission constraints during route construction;
- improve a first solution with local search or neighborhood moves.

This direction is stronger than a pure nearest-neighbor rule, but still easier to explain than a full metaheuristic such as VNS or ALNS.

### Data and experiment direction

The literature also shows that the data should be meaningful from a transport-risk perspective. Accident data, population exposure, road restrictions, infrastructure sensitivity, vehicle data, and cost data can all influence the final routing decision.

For experiments, the team should later decide which instance sizes and metrics fit the solver and heuristic implementation. The literature suggests that useful comparison metrics may include:

- runtime;
- solver status;
- objective value;
- total risk and total cost shown separately;
- feasibility of all routes;
- solver gap or best bound, if available;
- heuristic quality compared with the solver solution or bound.

## Open Modeling Choices

The literature leaves several choices open. These should be decided together with the team members responsible for data, model, solver, and experiments:

- Do we model cost as distance, travel time, energy use, tolls, or a weighted combination?
- Are forbidden roads completely removed, or are risky roads allowed with high penalties?
- Do we include time windows now, or only route duration limits?
- Is risk fixed per road segment, or does it increase with load and vehicle type?
- Do we use one weighted objective, or do we generate several trade-off solutions with different risk-cost weights?

These points can help the team decide together which modeling choices are realistic for the next project steps.
