# Literature Summary for Hazardous Materials Vehicle Routing

## Project Direction

Our project focuses on route planning for hazardous-material transports. In the current project direction, the fleet consists of electric heavy trucks, so vehicle range and energy-related costs may also matter. The decision maker is a transport company or logistics planner who must decide:

- which vehicle serves which delivery;
- which route each vehicle should take;
- how deliveries are planned while respecting legal, technical, and logistical restrictions.

The main objective is to minimize the total risk caused by hazardous-material transportation. In our project, risk is understood as a route-dependent value that can combine:

- population density along the route;
- accident probability on road segments;
- proximity to sensitive areas such as nature reserves or critical infrastructure;
- general hazard potential of the route.

At the same time, the logistics planner cannot ignore transport cost. Therefore, cost is treated as a secondary objective, including factors such as distance, travel time, energy consumption, and tolls.

In simple words, the project asks:

> How can hazardous-material deliveries be assigned to vehicles and routed through a permitted road network so that total risk is as low as possible while transport costs remain reasonable?

## OR Problem Class

The project belongs mainly to the Vehicle Routing Problem (VRP) family. More precisely, it is a Hazardous Materials Vehicle Routing Problem (HMVRP), because the transported goods create additional safety and regulatory constraints that do not appear in a normal delivery VRP.

It can also be interpreted as a constrained multi-commodity network flow problem:

- vehicles move through a network of nodes and arcs;
- every delivery creates a separate flow through the network;
- only valid and permitted arcs may be used;
- the chosen flow of vehicles creates both risk and cost.

This classification is important because the project is not only about finding short routes. A short route through a dense city center, tunnel, or area close to critical infrastructure may be cheap but unsafe. A safer route may be longer and more expensive. This risk-cost conflict is the central OR trade-off.

## Core Literature

### Erkut and Verter (1998)

**Reference:** Erkut, E., and Verter, V. (1998). Modeling of Transport Risk for Hazardous Materials. Operations Research, 46(5), 625-642. https://doi.org/10.1287/opre.46.5.625

Erkut and Verter (1998) are mainly relevant for the risk definition. Their discussion shows that different risk measures may lead to different preferred routes, even on the same network. This matters for our model because the risk score should not be treated as a hidden variant of distance or travel time. It has to be defined explicitly and justified as a modelling choice.

### Holeczek (2019)

**Reference:** Holeczek, N. (2019). Hazardous materials truck transportation problems: A classification and state of the art literature review. Transportation Research Part D: Transport and Environment, 69, 305-328. https://doi.org/10.1016/j.trd.2019.02.010

Holeczek (2019) provides the broader classification of hazardous-material truck transportation problems. The review makes clear why hazmat routing is not just a standard delivery problem: legal restrictions, exposed population, environmental consequences, and accident severity change the structure of the routing decision. This source supports the HMVRP classification and helps explain why prohibited arcs and hazardous-material-specific permissions belong in the model.

### Zografos and Androutsopoulos (2004)

**Reference:** Zografos, K. G., and Androutsopoulos, K. N. (2004). A heuristic algorithm for solving hazardous materials distribution problems. European Journal of Operational Research, 152(2), 507-519. https://doi.org/10.1016/S0377-2217(03)00041-9

Zografos and Androutsopoulos (2004) connect hazardous-material distribution with a bi-objective routing view, where risk and cost have to be considered together. Their heuristic approach is useful as a reference for building feasible solutions without relying only on exact optimization. In our heuristic discussion, this supports the idea of comparing candidate routing choices by both safety and cost instead of using a pure shortest-path rule.

### Androutsopoulos and Zografos (2012)

**Reference:** Androutsopoulos, K. N., and Zografos, K. G. (2012). A bi-objective time-dependent vehicle routing and scheduling problem for hazardous materials distribution. EURO Journal on Transportation and Logistics, 1, 157-183. https://doi.org/10.1007/s13676-012-0004-y

Androutsopoulos and Zografos (2012) show that more detailed HMVRP models may include time-dependent travel conditions, delivery order, time windows, and scheduling decisions. In our current project scope, these aspects are treated as possible extensions. The first heuristic direction focuses on assigning each origin-destination delivery to a feasible path and vehicle, while still keeping the risk-cost trade-off visible.

### Bula et al. (2016)

**Reference:** Bula, G. A., Gonzalez, F. A., Prodhon, C., Afsar, H. M., and Velasco, N. M. (2016). Mixed Integer Linear Programming Model for Vehicle Routing Problem for Hazardous Materials Transportation. IFAC-PapersOnLine, 49(12), 966-971. https://doi.org/10.1016/j.ifacol.2016.07.691

Bula et al. (2016) are relevant for the solver-based part of the project. Their MILP formulation shows how hazardous-material routing can be represented with binary routing decisions, vehicle-related constraints, and a risk-oriented objective. The paper also discusses load-dependent risk, which is useful background even if the first project version keeps the risk score simpler.

### Bula et al. (2017)

**Reference:** Bula, G. A., Prodhon, C., Gonzalez, F. A., Afsar, H. M., and Velasco, N. (2017). Variable neighborhood search to solve the vehicle routing problem for hazardous materials transportation. Journal of Hazardous Materials, 324, 472-480. https://doi.org/10.1016/j.jhazmat.2016.11.015

Bula et al. (2017) focus on a Variable Neighborhood Search for HMVRP. The full method is more advanced than what is needed for a first implementation, but the underlying idea is still useful: start from a feasible solution and improve it through controlled changes. This supports local search ideas such as switching paths or changing vehicle assignments after an initial solution has been built.

### Cuneo et al. (2018)

**Reference:** Cuneo, V., Nigro, M., Carrese, S., Ardito, C. F., and Corman, F. (2018). Risk based, multi objective vehicle routing problem for hazardous materials: A test case in downstream fuel logistics. Transportation Research Procedia, 30, 43-52. https://doi.org/10.1016/j.trpro.2018.09.006

Cuneo et al. (2018) are useful because the paper is close to a practical logistics setting. Their case study uses a risk index based on population density and accident estimates, which fits well with our planned risk data. The paper helps justify why accident exposure and population exposure should appear as separate components instead of being replaced by distance alone.

## Project Implications from the Literature

The reviewed literature gives a clear direction for the project while still leaving room for team decisions on the exact implementation.

### Modeling direction

The reviewed papers point toward a model in which risk and cost are treated as separate dimensions. Distance alone would not capture the main safety trade-off of hazardous-material routing. A simple risk idea that appears repeatedly in the literature is that road segments become more critical when accident probability and exposed population are high.

Possible modeling elements to discuss with the team:

- path and vehicle-assignment decisions on a network;
- delivery assignment and service constraints;
- vehicle capacity and limited fleet size;
- road permissions or prohibited arcs, possibly based on ADR classes;
- a risk measure based on accident probability, population exposure, nature reserve proximity, and route-specific hazard factors;
- a cost measure based on distance, travel time, energy use, charging cost, tolls, or a combination of these;
- electric-truck constraints such as battery range, if this remains part of the final model.

### Heuristic direction

The heuristic literature suggests that candidate path generation combined with local improvement could be a realistic option for the project. This matches the current OD-based heuristic direction better than a classic depot-customer-depot tour.

- generate feasible origin-destination paths for each delivery;
- evaluate candidate path and vehicle choices with both risk and cost in mind;
- respect capacity, battery range, and road-permission constraints during assignment;
- improve a first solution with path switches, vehicle reassignment, or similar local moves.

This direction is stronger than a pure nearest-neighbor rule, but still easier to explain than a full metaheuristic such as VNS or ALNS.

### Data and experiment direction

The literature also shows that the data should be meaningful from a transport-risk perspective. Accident data, population exposure, road restrictions, sensitive areas, ADR information, vehicle data, charging infrastructure, and cost data can all influence the final routing decision.

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
- Should ADR classes and tunnel restrictions be modeled directly from the ADR data?
- Should battery range be a hard constraint for electric trucks?
- Should charging stops be included now, or left for a later extension?
- Do we use one weighted objective, or do we generate several trade-off solutions with different risk-cost weights?

These points can help the team decide together which modeling choices are realistic for the next project steps.
