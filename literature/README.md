# Literature Summary

## Project Direction

Our project focuses on route planning for hazardous-material transports with a heterogeneous fleet of electric heavy trucks operating from a single depot. The decision maker is a transport company or logistics planner who must decide:

- which vehicle serves which delivery;
- how customers are combined and ordered within depot-to-depot trips;
- which permitted road connections are used between consecutive stops;
- when vehicles return to the depot, recharge, or start another trip.

The main objective is to minimize the total risk caused by hazardous-material transportation. The literature identifies several possible route-dependent risk components:

- population density along the route;
- accident probability on road segments;
- proximity to sensitive areas such as nature reserves or critical infrastructure;
- general hazard potential of the route.

These components describe the intended risk perspective, not a confirmed formula for the current optimization input. The heuristic consumes a precomputed OD risk value, and the exact meaning and composition of that field must be documented by the data preparation before it can be interpreted as population, accident, environmental, or expected-damage risk.

At the same time, the logistics planner cannot ignore transport cost and time. The evaluation therefore keeps risk, cost, and travel time as separate components before combining them in a normalized weighted objective.

In simple words, the project asks:

> How can hazardous-material deliveries be assigned to electric vehicles and organized into feasible trips so that total risk is kept low without losing sight of cost and time?

## OR Problem Class

The project belongs to the Vehicle Routing Problem (VRP) family and combines several extensions. More specifically, it is a single-depot, heterogeneous-fleet Hazardous Materials Vehicle Routing Problem with Multi-Trip and electric-vehicle extensions. A physical vehicle may perform several depot-to-depot trips, while battery capacity, charging opportunities, time restrictions, vehicle capacity, and hazardous-material compatibility all affect feasibility.

This classification is important because the project is not only about finding short routes. A short route through a dense city center, tunnel, or area close to critical infrastructure may be cheap but unsafe. A safer route may be longer and more expensive, while an electric vehicle may also need enough battery reserve or a charging stop. These interacting decisions create the central OR trade-off.

The classical VRP is already combinatorial because customer assignment and visit order have to be chosen together. The present problem adds vehicle compatibility, repeated trips, legal path selection, charging, and time-dependent resource states. As the number of customers and feasible insertions grows, an exact MILP has to consider many coupled decisions, which motivates a heuristic alongside the solver.

## Hazardous-Materials Routing Literature

### Erkut and Verter (1998)

**Reference:** Erkut, E., and Verter, V. (1998). Modeling of Transport Risk for Hazardous Materials. Operations Research, 46(5), 625-642. https://doi.org/10.1287/opre.46.5.625

Erkut and Verter (1998) are mainly relevant for the risk definition. Their discussion shows that different risk measures may lead to different preferred routes, even on the same network. This matters for our model because the risk score should not be treated as a hidden variant of distance or travel time. It has to be defined explicitly and justified as a modelling choice.

### Holeczek (2019)

**Reference:** Holeczek, N. (2019). Hazardous materials truck transportation problems: A classification and state of the art literature review. Transportation Research Part D: Transport and Environment, 69, 305-328. https://doi.org/10.1016/j.trd.2019.02.010

Holeczek (2019) provides the broader classification of hazardous-material truck transportation problems. The review makes clear why hazmat routing is not just a standard delivery problem: legal restrictions, exposed population, environmental consequences, and accident severity change the structure of the routing decision. This source supports the HMVRP classification and helps explain why prohibited arcs and hazardous-material-specific permissions belong in the model.

### Zografos and Androutsopoulos (2004)

**Reference:** Zografos, K. G., and Androutsopoulos, K. N. (2004). A heuristic algorithm for solving hazardous materials distribution problems. European Journal of Operational Research, 152(2), 507-519. https://doi.org/10.1016/S0377-2217(03)00041-9

Zografos and Androutsopoulos (2004) connect hazardous-material distribution with a bi-objective routing view, where risk and cost have to be considered together. Their route-building heuristic is also a useful basis for a construction procedure that extends partial routes through feasible insertions. The project adapts this principle by evaluating an insertion through the resulting risk, cost, time, and resource use.

### Androutsopoulos and Zografos (2012)

**Reference:** Androutsopoulos, K. N., and Zografos, K. G. (2012). A bi-objective time-dependent vehicle routing and scheduling problem for hazardous materials distribution. EURO Journal on Transportation and Logistics, 1, 157-183. https://doi.org/10.1007/s13676-012-0004-y

Androutsopoulos and Zografos (2012) show how delivery order, time-dependent travel conditions, scheduling, and risk-cost decisions can be connected in one hazardous-material routing problem. Their insertion-oriented view fits the constructive phase of the project heuristic, where customers are added to depot-to-depot trips only when the updated schedule remains feasible.

### Bula et al. (2016)

**Reference:** Bula, G. A., Gonzalez, F. A., Prodhon, C., Afsar, H. M., and Velasco, N. M. (2016). Mixed Integer Linear Programming Model for Vehicle Routing Problem for Hazardous Materials Transportation. IFAC-PapersOnLine, 49(12), 966-971. https://doi.org/10.1016/j.ifacol.2016.07.691

Bula et al. (2016) are relevant for the solver-based part of the project. Their MILP formulation shows how hazardous-material routing can be represented with binary routing decisions, vehicle-related constraints, and a risk-oriented objective. The paper also discusses load-dependent risk, which provides a useful point of comparison for the project's simpler static risk representation based on precomputed OD information.

### Bula et al. (2017)

**Reference:** Bula, G. A., Prodhon, C., Gonzalez, F. A., Afsar, H. M., and Velasco, N. (2017). Variable neighborhood search to solve the vehicle routing problem for hazardous materials transportation. Journal of Hazardous Materials, 324, 472-480. https://doi.org/10.1016/j.jhazmat.2016.11.015

Bula et al. (2017) apply Variable Neighborhood Descent and Variable Neighborhood Search directly to HMVRP. This is the closest methodological reference for the improvement phase of the project heuristic: VND examines several neighborhood structures systematically, while Basic VNS adds controlled shaking before running local improvement again.

### Cuneo et al. (2018)

**Reference:** Cuneo, V., Nigro, M., Carrese, S., Ardito, C. F., and Corman, F. (2018). Risk based, multi objective vehicle routing problem for hazardous materials: A test case in downstream fuel logistics. Transportation Research Procedia, 30, 43-52. https://doi.org/10.1016/j.trpro.2018.09.006

Cuneo et al. (2018) are useful because the paper is close to a practical logistics setting. Their case study uses a risk index based on population density and accident estimates, which fits the conceptual design of the project data. The paper helps justify why accident exposure and population exposure should be distinguished from distance, without proving that the current precomputed OD risk field already contains these components in the same form.

## Related Routing, Modeling, and Data Literature

### Laporte (2009)

**Reference:** Laporte, G. (2009). Fifty years of vehicle routing. Transportation Science, 43(4), 408-416. https://doi.org/10.1287/trsc.1090.0301

Laporte traces the development of the classical Vehicle Routing Problem and the roles of exact algorithms, heuristics, and metaheuristics. This provides the general OR background for describing the project as an extension of the VRP rather than as a collection of independent shortest-path tasks.

### Solomon (1987)

**Reference:** Solomon, M. M. (1987). Algorithms for the vehicle routing and scheduling problems with time window constraints. Operations Research, 35(2), 254-265. https://doi.org/10.1287/opre.35.2.254

Solomon is a standard reference for route construction under time-window constraints and includes insertion-based heuristics. The project does not reproduce these algorithms directly, but the paper gives the general methodological background for building a route by adding feasible customers one at a time.

### Mladenovic and Hansen (1997)

**Reference:** Mladenovic, N., and Hansen, P. (1997). Variable neighborhood search. Computers & Operations Research, 24(11), 1097-1100. https://doi.org/10.1016/S0305-0548(97)00031-2

Mladenovic and Hansen introduce the general Variable Neighborhood Search framework. Systematic neighborhood changes and the combination of shaking with local search form the methodological basis of Basic VNS, while Bula et al. (2017) show how this principle can be used specifically for hazardous-material routing.

### Cattaruzza et al. (2016)

**Reference:** Cattaruzza, D., Absi, N., and Feillet, D. (2016). Vehicle routing problems with multiple trips. 4OR, 14, 223-259.

This review defines the main variants and solution approaches of the Multi-Trip Vehicle Routing Problem. Its relevance is direct: a physical vehicle in the project can return to the depot, reload, and perform another trip during the planning horizon rather than being limited to one tour.

### Cattaruzza et al. (2014)

**Reference:** Cattaruzza, D., Absi, N., Feillet, D., and Vigo, D. (2014). An iterated local search for the multi-commodity multi-trip vehicle routing problem with time windows. Computers & Operations Research, 51, 257-267. https://doi.org/10.1016/j.cor.2014.06.006

The paper brings together multiple trips, time windows, incompatible commodities, and local search. This combination is close to the modeled project setting, in which hazardous-material classes restrict which deliveries can share a trip and local changes must be checked against the full trip schedule. The implementation supports class compatibility, but the current Small, Medium, and Large experiments use class 3 deliveries only and therefore do not validate a multi-commodity effect.

### Crevier et al. (2007)

**Reference:** Crevier, B., Cordeau, J.-F., and Laporte, G. (2007). The multi-depot vehicle routing problem with inter-depot routes. European Journal of Operational Research, 176(2), 756-773.

Crevier et al. use intermediate depot visits within vehicle routes. Although their problem is multi-depot, the formulation provides useful background for representing reload visits and repeated trips without introducing a separate copy of every decision for every possible tour.

### Kallehauge et al. (2005)

**Reference:** Kallehauge, B., Larsen, J., Madsen, O. B. G., and Solomon, M. M. (2005). Vehicle Routing Problem with Time Windows. In Column Generation, Springer, 67-98.

This chapter provides the standard VRPTW background for arrival times, service periods, and time-feasible customer sequences. It supports the time-propagation logic used to reject insertions that would violate the planning horizon or customer-related time limits.

### Desrochers and Laporte (1991)

**Reference:** Desrochers, M., and Laporte, G. (1991). Improvements and extensions to the Miller-Tucker-Zemlin subtour elimination constraints. Operations Research Letters, 10(1), 27-36.

Desrochers and Laporte develop stronger time-based subtour-elimination constraints for routing models. The report uses this work to place its own time-propagation constraints in context: strictly increasing arrival times along used arcs prevent disconnected cycles.

### Erdogan and Miller-Hooks (2012)

**Reference:** Erdogan, S., and Miller-Hooks, E. (2012). A Green Vehicle Routing Problem. Transportation Research Part E: Logistics and Transportation Review, 48(1), 100-114.

This paper establishes a routing problem with limited vehicle range and alternative-fuel stations. It supports the inclusion of energy feasibility and charging infrastructure, while the project's charging representation remains a simplified adaptation for electric heavy trucks.

### Schneider et al. (2014)

**Reference:** Schneider, M., Stenger, A., and Goeke, D. (2014). The electric vehicle-routing problem with time windows and recharging stations. Transportation Science, 48(4), 500-520.

Schneider et al. connect battery tracking, charging decisions, time windows, and route construction. Their model is the main reference for checking whether a customer sequence remains feasible after energy consumption and possible charging activities have been added to its schedule.

### Goel (2009)

**Reference:** Goel, A. (2009). Vehicle scheduling and routing with drivers' working hours. Transportation Science, 43(1), 17-26.

Goel examines routing under driver working-hour rules. This gives the methodological background for tracking continuous driving time and for treating breaks as part of route feasibility rather than as an optional cost adjustment. The paper does not by itself establish the numerical driving, working-time, or break parameters used in the project scenarios.

### Marler and Arora (2004)

**Reference:** Marler, R. T., and Arora, J. S. (2004). Survey of multi-objective optimization methods for engineering. Structural and Multidisciplinary Optimization, 26, 369-395.

Risk, cost, and time use different units and numerical ranges. Marler and Arora explain why weighted multi-objective methods require scaling or normalization before aggregation. This supports the project's normalized weighted objective and the separate reporting of all three components.

### Abdel-Aty and Radwan (2000)

**Reference:** Abdel-Aty, M., and Radwan, E. (2000). Modeling traffic accident occurrence and involvement. Accident Analysis & Prevention, 32(5), 633-642.

The study links accident occurrence to road and traffic characteristics. It supports using accident observations during network-risk preprocessing rather than reproducing the original statistical model. How this information is aggregated into the OD risk value used by the optimization methods still needs to be stated explicitly in the data documentation.

### Boeing (2017)

**Reference:** Boeing, G. (2017). OSMnx: New methods for acquiring, constructing, analyzing, and visualizing complex street networks. Computers, Environment and Urban Systems, 65, 126-139.

OSMnx provides a reproducible way to obtain and process routable street networks from OpenStreetMap. In the project it underpins the network representation and the preparation of permitted connections used by both the solver and the heuristic.

### Haklay and Weber (2008)

**Reference:** Haklay, M., and Weber, P. (2008). OpenStreetMap: User-generated street maps. IEEE Pervasive Computing, 7(4), 12-18.

Haklay and Weber describe OpenStreetMap as a collaborative geographic data source. The paper supports the choice of OSM road data, while also reminding us that user-generated attributes need validation before they are interpreted as complete legal or safety information.

### OpenStreetMap / Geofabrik

**Reference:** OpenStreetMap contributors. OpenStreetMap data for Germany, distributed through Geofabrik. https://download.geofabrik.de/europe/germany.html

**Type:** Open geographic data source.

OpenStreetMap provides the raw road-network data used to build the project graph. Geofabrik is relevant as a practical distribution channel for country-level OSM extracts. This source supports the data basis of the network, while Boeing (2017) and Haklay and Weber (2008) provide the methodological and academic background for working with OSM data.

### Jones and Purves (2008)

**Reference:** Jones, C. B., and Purves, R. S. (2008). Geographical information retrieval. International Journal of Geographical Information Science, 22(3), 219-228.

**Type:** Academic source.

Jones and Purves discuss geographical information retrieval and spatial search concepts. In the project, this source is relevant for the preprocessing idea of limiting and querying geographic data around the relevant depot, customer, and network area. It supports the general spatial-data handling logic, not a specific optimization algorithm.

### Kim and Jeong (2009)

**Reference:** Kim, B.-I., and Jeong, S. (2009). A comparison of algorithms for origin-destination matrix generation on real road networks and an approximation approach. Computers & Industrial Engineering, 56(1), 70-76.

This work discusses the generation of origin-destination matrices on real road networks. It is relevant to the project's preprocessing step, which converts network paths into reusable distance, time, risk, and cost relations for optimization.

### Maria et al. (2020)

**Reference:** Maria, E., Budiman, E., Haviluddin, and Taruk, M. (2020). Measure distance locating nearest public facilities using Haversine and Euclidean methods. Journal of Physics: Conference Series, 1450, 012080.

Maria et al. compare common geographic distance calculations. The source provides background for coordinate-based proximity checks, such as mapping locations to network nodes or measuring distance to nearby infrastructure, but not for road-route distance itself.

### UNECE (2025)

**Reference:** United Nations Economic Commission for Europe. (2025). ADR 2025: Agreement concerning the International Carriage of Dangerous Goods by Road. https://unece.org/adr-2025-files

ADR is a regulatory source rather than an academic paper. It defines the legal framework for dangerous-goods classes, transport requirements, and route restrictions such as tunnel categories. In the project, these rules are represented as hard compatibility and permission constraints; an illegal connection is excluded instead of merely receiving a high risk penalty.

### German Accident Atlas

**Reference:** Statistical Offices of the Federation and the Länder. Unfallatlas: road accident data as geo-open-data. https://unfallatlas.statistikportal.de/

**Type:** Official data source.

The accident atlas provides georeferenced road-accident information. It is relevant for the data-preparation side of the project because accident observations can be linked to road segments and used as one input for risk-related network attributes. The source supports the availability of accident data, but it does not by itself define the final OD risk value used by the optimization methods.

### Zensus 2021

**Reference:** Statistisches Bundesamt (Destatis). Zensus 2021 population data. https://www.zensus2022.de/

**Type:** Official data source.

Zensus population data support the exposure perspective of hazardous-material routing. They can be used to estimate how many people may be located near a road segment or within a relevant buffer around a route. This source helps ground population exposure as a data component, while the exact aggregation into the project risk field remains part of the data-preparation documentation.

### Bundesnetzagentur Charging Infrastructure Data

**Reference:** Bundesnetzagentur. Ladesäulenregister: location and power data for public charging infrastructure in Germany. https://www.bundesnetzagentur.de/

**Type:** Official infrastructure data source.

The Bundesnetzagentur charging-station register is relevant for the electric-vehicle part of the project. It provides location and power information for public charging infrastructure, which can be used to identify possible charging nodes or hubs. In the optimization model and heuristic, these data support energy feasibility and charging decisions rather than hazardous-material risk itself.

### Technik+Einkauf (2026)

**Reference:** Technik+Einkauf. (2026). Die größten Raffinerien in Deutschland.

**Type:** Practical background source.

This source is used as practical background for the scenario design, especially the choice of refinery-related depot context. It is not an OR or risk-modeling source, but it helps justify why a refinery location can be a plausible origin for fuel or hazardous-material distribution scenarios.

## Project Implications from the Literature

Together, these sources support the full project workflow, from network and risk data to mathematical modeling, exact optimization, heuristic search, and numerical evaluation.

### Data and regulatory direction

OpenStreetMap, Geofabrik, and OSMnx provide the physical road network, while the Accident Atlas, Zensus population data, and other spatial information can contribute different parts of the transport-risk description during preprocessing. Geographic information retrieval and distance methods support spatial filtering, mapping, and proximity checks. OD-matrix research informs the conversion of network paths into reusable distance, time, risk, and cost relations. The optimization methods receive these prepared relations rather than the raw GIS layers.

ADR has a different role from the academic sources. It provides the regulatory basis for dangerous-goods classes and route restrictions. Legal incompatibility is therefore represented as a hard feasibility condition rather than as a high but avoidable risk score. The Bundesnetzagentur charging register supports the EV-charging data basis, while refinery and scenario-background sources support the construction of plausible depot and customer settings. Vehicle specifications, charging data, prices, and service times still need traceable sources; values without reliable external evidence should be identified as scenario assumptions.

### Risk and objective direction

The risk literature shows that distance alone is not an adequate safety measure. Accident likelihood, exposed population, possible consequences, and proximity to sensitive areas describe different aspects of risk and may lead to different preferred routes. The current heuristic reads a precomputed OD risk signal instead of recalculating these components. The report should therefore state clearly which components are contained in that field and avoid presenting the resulting routing score as a direct estimate of expected damage unless the data support that interpretation.

Risk, cost, and time also use different units. Multi-objective literature supports normalizing them with scales that remain fixed within one instance run before applying a weighted sum. The unweighted components must still be reported separately, and scalar objective values from different weight scenarios should not be compared as if their definitions were unchanged. This makes the trade-off visible and prevents a change in the weighted objective from being mistaken for an actual change in route quality.

### Mathematical model direction

The project problem combines HMVRP, Multi-Trip VRP, and electric-vehicle routing. The literature supports binary routing decisions on a directed graph together with customer-service and flow constraints, vehicle capacity, hazardous-material compatibility, time propagation, driver working limits, battery tracking, charging decisions, and repeated depot visits. The current conservative operating rule keeps one hazardous-material class on a physical vehicle during a planning day because cleaning time, cleaning cost, and class-change conditions are not modeled.

Bula et al. provide the closest HMVRP reference for the MILP perspective. Cattaruzza et al. support the Multi-Trip structure, Schneider et al. and Erdogan and Miller-Hooks cover electric-vehicle resources, and Desrochers and Laporte provide background for time-based subtour prevention. These sources explain the modeling choices without replacing the complete formulation given in the mathematical-model chapter.

### Exact solution and solver direction

The exact solution approach is intended to implement the mathematical formulation, establish feasibility, find an incumbent, and, where possible, report a best bound or optimality gap. The literature provides the formulation principles, but claims about implementation success or optimality must come from the actual solver status rather than from the use of an exact model alone.

Because the combined problem contains customer sequencing, vehicle assignment, repeated trips, legal connections, charging, and time resources, model size and runtime can increase quickly. This motivates testing the exact approach on increasing instance sizes and recording model build time, solution time, termination status, incumbent value, bound, and gap.

### Heuristic direction

The implemented method combines several ideas from the literature without reproducing one paper line by line:

- sequential best insertion is the main construction strategy and builds depot-to-depot trips by evaluating feasible customer, vehicle, trip, and position combinations through the shared normalized objective;
- a bounded repair phase tries to place customers left unserved by the first construction;
- VND examines intra-trip relocate, 2-opt and swap, inter-trip relocate and swap, and complete-trip reassignment;
- Basic VNS follows the general VNS principle of controlled shaking followed by local improvement, adapted here to the HMVRP setting;
- every construction, repair, and improvement move uses the same checks for capacity, compatibility, time, battery, charging, and route permissions.

Alternative `regret_2` and `hardest_first` seed strategies are diagnostic options rather than the main experimental configuration. The heuristic works with legal, static, precomputed origin-destination legs containing distance, travel time, risk, and cost information. It does not process raw GIS data itself or reproduce the time-dependent path-generation algorithms from the literature. Cargo-related HazMat risk is counted on loaded legs; the final empty return still contributes distance, time, energy use, and cost but has no cargo-related risk. Charging is represented through a restricted customer-station-customer side-trip, and charging alternatives and complete vehicle schedules are reevaluated through the shared feasibility logic whenever a customer sequence changes.

### Experiment and reporting direction

The solver and heuristic comparison should use the same customer set, depot, fleet, demand interpretation, OD data, legal restrictions, risk definition, objective weights and scales, costs, time parameters, and feasibility rules. A solution-quality gap is meaningful only when both methods use the same scalar objective and the solver has produced a valid incumbent or bound. The main reported metrics are:

- runtime;
- solver status;
- normalized objective value;
- risk, cost, and time shown separately;
- number of served and unserved customers;
- feasibility of all trips;
- solver gap or best bound, if available;
- heuristic quality relative to the solver solution or bound;
- sensitivity to alternative risk-cost-time weights;
- the contribution of construction, repair, VND, and VNS in an ablation comparison based on separately recorded stage results.
