# Multi-Customer Hazardous Materials Routing Heuristic

This README documents the heuristic design, implementation modules, input
contract, and solver-comparison output.

## Quick Start

Main modules:

- `multi_customer_heuristic_toy.py` contains the shared multi-customer
  algorithm and its in-memory toy instance. The filename is retained because
  the executable example remains part of the module.
- `precomputed_matrix_adapter.py` loads precomputed Small, Medium, or Large
  customer, vehicle, OD, and charging matrices.
- `multi_customer_small_adapter.py` is a compatibility wrapper for existing
  notebooks and commands. New code should use `precomputed_matrix_adapter`.
- `risk_cost_path_heuristic_toy.py` demonstrates the earlier lower-level OD
  path logic and is not the final multi-customer workflow.

### Expected Data Layout

The adapter expects one coherent instance directory and a vehicle file:

```text
<data-root>/
    vehicles.csv
    <instance-directory>/
        *instanz_*.csv
        od_matrix_<name>.csv
        od_matrix_<name>_charger.csv
```

The exact filenames may differ. Automatic selection works only when the
instance directory contains exactly one matching instance file, one regular
OD matrix, and one charger OD matrix. Otherwise, select all three files
explicitly.

### Basic CLI Usage

Run a matrix-backed Small, Medium, or Large baseline:

```text
python -m heuristics.precomputed_matrix_adapter --data-dir <instance-directory> --vehicles-file <vehicles.csv> --single-trip-per-vehicle --output-json <result.json>
```

When the directory contains ambiguous filenames:

```text
python -m heuristics.precomputed_matrix_adapter --data-dir <instance-directory> --vehicles-file <vehicles.csv> --instance-file <instance.csv> --od-matrix-file <od-matrix.csv> --charger-matrix-file <charger-matrix.csv> --single-trip-per-vehicle --output-json <result.json>
```

Run the cost-oriented Small scenario:

```text
python -m heuristics.precomputed_matrix_adapter --data-dir <instance-directory> --vehicles-file <vehicles.csv> --risk-weight 0.3 --cost-weight 0.5 --time-weight 0.2 --single-trip-per-vehicle --max-charging-branch-evaluations 1000 --output-json <result.json>
```

The adapter excludes a regular OD relation when its loaded safest row is
unreachable or has non-finite distance or time. Such relations are reported in
`illegal_loaded_relations`; the heuristic does not silently replace them with a
finite penalty. A solver comparison must use the same legal relation set.

`--exclude-customer` may be repeated. Excluding a customer changes the
instance and must be documented; solver comparison is valid only when both
methods use the same customer set.

The legacy entry point still forwards to the same implementation:

```text
python -m heuristics.multi_customer_small_adapter --help
```

New scripts should use `heuristics.precomputed_matrix_adapter`.

### CLI Parameters

Input selection:

| Parameter | Required | Default | Meaning |
|---|---:|---|---|
| `--data-dir` | yes | none | Directory containing one coherent instance and its OD matrices. |
| `--vehicles-file` | no | `<data-dir>/../vehicles.csv` | Vehicle fleet CSV. |
| `--instance-file` | no | unique `*instanz_*.csv` | Explicit customer/depot instance CSV. |
| `--od-matrix-file` | no | unique non-charger `od_matrix_*.csv` | Regular customer/depot OD matrix. |
| `--charger-matrix-file` | no | unique charger `od_matrix_*.csv` | Charging-station OD matrix. |
| `--vehicle-hazard-compatibility-file` | no | none | JSON object mapping each vehicle ID to its allowed hazard classes. |
| `--exclude-customer` | no | none | Customer ID removed from the run; repeat the option for several IDs. |
| `--output-json` | no | none | Writes the machine-readable result JSON. Without it, summaries are printed only. |

The optional hazard-compatibility file is a JSON object:

```json
{
  "MAN_eTGX_1": ["3", "8"],
  "Volvo_FH_Electric_1": ["3"]
}
```

Objective configuration:

| Parameter | Default | Meaning |
|---|---:|---|
| `--risk-weight` | `0.5` | Weight of normalized total risk. |
| `--cost-weight` | `0.3` | Weight of normalized total cost. |
| `--time-weight` | `0.2` | Weight of normalized operating time. |

All weights must be non-negative and must sum to `1.0`.

Search configuration:

| Parameter | Default | Meaning |
|---|---:|---|
| `--construction-strategy` | `best_insertion` | New-trip seed rule: `best_insertion`, `regret_2`, or `hardest_first`. Trip extension always uses best insertion. |
| `--single-trip-per-vehicle` | `False` | Enforces the current solver-compatible structure: each physical vehicle may receive at most one depot-to-depot trip. Omit it only for multi-trip extension or sensitivity runs. |
| `--repair-evaluations` | `20000` | Maximum depth-one repair candidate evaluations. |
| `--repair-seconds` | `300` | Depth-one repair time limit in seconds. |
| `--vnd-passes` | `1000` | Maximum deterministic VND neighborhood passes. |
| `--vns-seconds` | `10` | VNS runtime limit in seconds. |
| `--random-seed` | `42` | Reproducible VNS shaking seed. |
| `--max-charging-branch-evaluations` | `100` | Charging-state branch limit for each schedule evaluation. Larger instances may require a larger value such as `1000`. |

The CLI executes:

```text
adapter -> construction -> depth-one repair -> VND -> VNS -> validation -> JSON
```

It does not currently expose the scenario timing parameters or limited
depth-two repair. Use the Python API for experiments that need them.

### Python API for Custom Scenarios

`build_matrix_adapter()` additionally accepts the following scenario
parameters:

| Parameter | Default | Unit / meaning |
|---|---:|---|
| `service_minutes` | `30` | Service duration per customer. |
| `shift_start_minute` | `0` | Vehicle shift start. |
| `shift_end_minute` | `600` | Vehicle shift end. |
| `initial_load_minutes` | `20` | Initial depot loading time. |
| `reload_minutes` | `15` | Reload time before another trip. |
| `max_daily_driving_minutes` | `540` | Maximum daily driving time. |
| `max_daily_working_minutes` | `600` | Maximum daily working time. |
| `continuous_driving_limit_minutes` | `270` | Driving time before a qualifying break. |
| `break_duration_minutes` | `45` | Driver-break duration. |
| `reserve_fraction` | `0.10` | Minimum battery reserve as a fraction of usable battery. |
| `depot_charging_power_kw` | `300` | Depot charging power. |
| `depot_energy_price_per_kwh` | `0.35` | Depot energy price. |
| `charger_power_kw` | `300` | Public-station charging power. |
| `charger_energy_price_per_kwh` | `0.75` | Public-station energy price. |
| `charger_session_fee` | `0` | Fixed public charging-session fee. |

For example, a custom 780-minute scenario can be constructed with:

```python
from pathlib import Path

from heuristics.multi_customer_heuristic_toy import (
    ObjectiveWeights,
    construct_initial_solution,
    repair_partial_solution_depth_one,
    repair_partial_solution_depth_two,
)
from heuristics.precomputed_matrix_adapter import build_matrix_adapter

adapter = build_matrix_adapter(
    Path("<instance-directory>"),
    vehicles_file=Path("<vehicles.csv>"),
    instance_file=Path("<instance.csv>"),
    od_matrix_file=Path("<od-matrix.csv>"),
    charger_matrix_file=Path("<charger-matrix.csv>"),
    shift_end_minute=780.0,
    max_daily_working_minutes=780.0,
    max_charging_branch_evaluations=1000,
    weights=ObjectiveWeights(risk=0.5, cost=0.3, time=0.2),
)

construction = construct_initial_solution(
    adapter.instance,
    single_trip_per_vehicle=True,
)
depth_one = repair_partial_solution_depth_one(
    adapter.instance,
    construction,
    single_trip_per_vehicle=True,
)
depth_two = repair_partial_solution_depth_two(
    adapter.instance,
    depth_one,
    single_trip_per_vehicle=True,
)
```

When `single_trip_per_vehicle` is omitted in repair, VND, or VNS, the
setting is inherited from the incoming run. Passing it explicitly is still
useful in scripts where the route-structure mode should be obvious.

Only pass a repair result to VND when its status and evaluation are feasible.
The complete experiment workflow must record all configured limits, runtime
stages, objective scales, random seed, and stop reasons in the exported
result.

Run the complete test suite:

```text
python -m unittest discover -s heuristics -p "test_*.py"
```

## 1. Scope

This document defines the heuristic for a single-depot hazardous-material vehicle routing problem.

For the final solver comparison, the heuristic is used in the same single-trip setting as the current MILP solver: each physical vehicle performs at most one depot-to-depot customer route. This keeps the heuristic result directly comparable to the solver and usable as a solver-compatible route proposal.

Beyond this common baseline, the heuristic engine also implements a multi-trip extension. In that extension, a vehicle may return to the depot, reload, and start another depot-to-depot trip within the same planning horizon. This is more flexible than the current solver formulation and is treated as a heuristic extension or sensitivity result, not as the direct solver-comparison case.

The solver-compatible single-trip experiments use these assumptions:

- every order starts at the depot and is delivered to one customer;
- every customer order is served exactly once and is not split;
- one trip carries only one compatible hazardous-goods class;
- every trip starts and ends at the depot;
- each physical vehicle performs at most one trip;
- customer service, charging, and driver-break times affect the schedule;
- the final depot return is empty and has transport cost and time but no cargo-related HazMat risk;
- the empty but uncleaned vehicle continues to use the same implemented ADR/tunnel rules as its loaded trip.

In multi-trip runs, depot reload time is active, payload capacity is restored only after the vehicle returns and reloads, and a vehicle may perform several non-overlapping trips during the planning day. Such runs must be clearly labelled as multi-trip and should only be compared with a solver that uses the same route structure.

As a conservative first-version assumption, a physical vehicle cannot change hazardous-goods class during the planning day. A later version may allow a class change after depot cleaning if cleaning time, cost, and legal rules are defined by the team.

The existing one-way OD heuristic remains useful as the lower road-path layer. It is not the complete target algorithm anymore.

## 2. Selected Method and Literature Basis

The selected method is:

> **Sequential route-building insertion with Variable Neighborhood Search improvement.**

Its components are traceable to the project literature:

- Zografos and Androutsopoulos (2004) support a bi-objective route-building heuristic for hazardous-material distribution with time windows.
- Androutsopoulos and Zografos (2012) construct routes sequentially, use a weighted risk-cost objective, and select feasible customer insertions with an insertion metric.
- Bula et al. (2017) use Variable Neighborhood Search and Variable Neighborhood Descent for heterogeneous-fleet HazMat routing.
- Cattaruzza et al. (2014) address incompatible commodities, time windows, and several trips by the same vehicle.
- Schneider et al. (2014) support battery and charging-station feasibility in an electric VRP with time windows.

The implementation is an adaptation rather than an exact reproduction:

- static candidate paths replace the time-dependent label-setting procedure from Androutsopoulos and Zografos (2012);
- the baseline may test every feasible insertion position instead of only the front of the unfinished route;
- VNS neighborhoods are adapted to hazardous-goods compatibility, charging, single-trip routes, and the optional multi-trip extension;
- the risk formula uses the population, accident, nature, class, and vehicle data available in this project.

## 3. Solution Structure

The heuristic has two layers.

### 3.1 Road-Path Layer

This layer maps relevant locations to the road graph and generates rule-feasible path alternatives between:

```text
depot, customers, charging stations, and approved break locations
```

Each path alternative contains:

```text
path_id
from_stop
to_stop
hazard_class
load_state
edge_sequence
distance_km
travel_time_h
risk
variable_cost_by_vehicle
energy_use_by_vehicle
implemented_rules_feasible
```

### 3.2 Route-and-Schedule Layer

This layer builds an ordered solution:

```text
Vehicle
    Trip 1: Depot -> Customer -> Customer -> Depot
    Trip 2: Depot -> Customer -> Charging Station -> Customer -> Depot
```

It decides:

- which physical vehicle performs each trip;
- which customers belong to each trip;
- the order of customers and charging stops;
- the road-path alternative used for every leg;
- trip start, arrival, service, charging, break, and return times;
- when a vehicle becomes available for another trip.

## 4. Input Data

### 4.1 Sets

- `V`: physical vehicles;
- `C`: customer orders;
- `N`: road-network nodes;
- `E`: directed road edges;
- `K`: hazardous-goods classes;
- `H`: charging-station nodes;
- `B`: nodes at which a driver break is allowed.

### 4.2 Customer Data

For every customer order `c`:

- `Demand_c`: delivery mass in one documented unit, preferably kg;
- `Class_c`: hazardous-goods class;
- `Location_c`: customer coordinate or mapped node;
- `ServiceTime_c`: unloading and service duration;
- `Earliest_c`, `Latest_c`: optional service time window. If absent, use the complete planning horizon.

If input quantities are provided in liters, they must be converted to kg before the capacity check. The conversion rule and density must be recorded in the run metadata.

### 4.3 Vehicle Data

For every physical vehicle `v`:

- `VehicleId_v`: unique identifier of one physical vehicle;
- `Type_v`: vehicle type;
- `Cap_v`: payload capacity in kg;
- `UsableBattery_v`: usable battery capacity in kWh;
- `InitialBattery_v`: battery energy at the start of the planning day;
- `MinReserve_v`: minimum permitted battery reserve;
- `EnergyRate_v`: energy consumption in kWh per km;
- `MaxChargingPower_v`: maximum charging power accepted by the vehicle in kW;
- `CompatibleClasses_v`: hazardous-goods classes allowed on the vehicle;
- `ActivationCost_v`: cost charged once if the vehicle is used;
- `TripCost_v`: optional dispatch or reload cost charged per trip;
- `KmCost_v`: non-energy operating cost per km;
- `ShiftStart_v`, `ShiftEnd_v`: vehicle or driver availability;
- `InitialLoadTime_v`: loading time before the first trip;
- `ReloadTime_v`: depot time before the next trip.

Vehicle activation cost and per-trip dispatch cost must remain separate. The heuristic must not silently charge one parameter using the other interpretation.

The real instance must provide one row per physical vehicle or an `available_units` field that is deterministically expanded to physical `VehicleId_v` values. A vehicle-type row alone is not sufficient for activation cost or trip-overlap checks. The first toy instance may deliberately create one or more named physical vehicles from each available type.

### 4.4 Road-Edge Data

For every directed edge `e`:

- `ArcId_e`;
- `From_e`, `To_e`;
- `Len_e`;
- `TravelTime_e` or speed information;
- population risk component;
- accident risk component;
- nature or sensitive-area component;
- road class and tunnel category;
- geometry or coordinates;
- permission under the implemented ADR/tunnel rules by hazardous-goods class.

### 4.5 Charging and Time Data

- charging-node coordinates;
- station charging power in kW;
- station energy price in EUR/kWh;
- optional station or session fee;
- up to three rule-feasible charging-station candidates per customer;
- directed customer-to-station and station-to-customer paths, with separate distance, time, risk, energy, and permission values;
- depot charging power and energy price;
- break-node eligibility;
- planning-horizon start and end;
- maximum continuous driving time;
- required break duration;
- maximum daily driving and working time;
- maximum number of complete charging-candidate branch evaluations.

The driving-time simplification must be shared with the mathematical model before final experiments.

The first-version break set is:

```text
B =
    depot
    union charging stations
    union customer nodes explicitly marked BreakAllowed
```

If no customer break attribute exists, customers are not assumed to be break-eligible.

Every numeric input must be a finite number before construction starts. `NaN`, positive or negative infinity, invalid numeric types, and a non-integer charging-branch limit are reported as `input_data_error`.

### 4.6 Input Selection and Compatibility

Automatic matrix discovery is used only when exactly one regular OD matrix and
one charger matrix are present. If several candidates exist, the caller must
explicitly select each ambiguous input; the adapter does not silently prefer
a Small-instance filename.

A vehicle compatibility file describes the complete capability of every
physical vehicle. It may therefore contain project-supported classes that are
not used by the selected instance. The current supported set is:

```text
1.1D, 2, 2 (TOC), 3, 6, 8, 9
```

Every vehicle in the selected fleet must have an entry, and every class used
by the instance must be supported by at least one vehicle.

## 5. Risk, Cost, and Time Evaluation

Risk, cost, and time are stored separately even when a weighted score is used.

### 5.1 Risk

The baseline first converts every component to a rate and then normalizes it on the same shared preprocessing graph before SCC selection or route-corridor cropping.

```text
PopulationRateRaw_e =
    pop_per_meter
    or population / LenMeter_e

AccidentRateRaw_e =
    acc_rate
    or accidents / LenKm_e
    or a verified rate field such as weighted_score or score

NatureRateRaw_e =
    nature_score, if already defined as a rate
    or an inverse transformation of dist_to_nature_m
```

For zero-length edges, all derived rates are set to zero. A field is used directly only when its data definition confirms that it is a rate.

If only a semantically unverified field such as `accident_score` is available, preprocessing stops with a clear data-definition error instead of guessing a transformation.

Each component is min-max normalized once:

```text
PopulationRateNorm_e = normalize(PopulationRateRaw_e)
AccidentRateNorm_e   = normalize(AccidentRateRaw_e)
NatureRateNorm_e     = normalize(NatureRateRaw_e)
```

The additive edge-risk equation is:

```text
BaseRiskRate_e =
    0.40 * PopulationRateNorm_e
    + 0.40 * AccidentRateNorm_e
    + 0.20 * NatureRateNorm_e

RiskRate_{e,k} =
    BaseRiskRate_e * HazardFactor_k

Risk_{e,k} =
    RiskRate_{e,k} * LenKm_e
```

This makes path risk invariant when a road with unchanged rates is split into several edges. The implementation must test this property after edge contraction and expansion.

The run metadata records for every component:

```text
source_field
source_unit
rate_transformation
normalization_min
normalization_max
normalization_population
```

The same transformations and constants must be reused by the solver. The population-and-accident structure is consistent with the practical fuel-distribution risk direction in Cuneo et al. (2018).

The current matrix-backed workflow does not recompute these edge components.
For each reachable loaded `safest` OD row, it interprets the supplied
`risk_total` value as a per-kilometre rate. The schedule evaluator therefore
uses `risk_total * distance_km * HazardFactor` for a loaded leg. This convention
is recorded in `metadata.risk_source` and must be matched explicitly by the
solver before raw risk values or objective gaps are compared.

For a loaded leg:

```text
leg_risk(k, p) =
    sum Risk_{e,k} for all edges e in path p
```

The first multi-customer version may keep this risk load-independent. Remaining load is still tracked so that a later version can apply a load factor without changing the route representation.

The final empty return has:

```text
cargo_related_hazmat_risk = 0
```

but its distance, time, energy use, and cost remain part of the solution. Residual tank risk is outside the first-version risk model. Until cleaning is explicitly modeled, the return continues to use the implemented ADR/tunnel rules for the trip class.

### 5.2 Battery, Charging, and Cost

Battery energy is the canonical electric resource:

```text
EnergyUse_{v,e} =
    LenKm_e * EnergyRate_v

BatteryAfterLeg =
    BatteryBeforeLeg - EnergyUse_{v,e}

ChargedEnergy =
    UsableBattery_v - BatteryBeforeCharge

BatteryAfterCharge =
    min(UsableBattery_v, BatteryBeforeCharge + ChargedEnergy)

EffectiveChargingPower =
    min(StationPower, MaxChargingPower_v)

ChargingDuration =
    ChargedEnergy / EffectiveChargingPower

ChargingCost =
    ChargedEnergy * StationEnergyPrice
    + optional SessionFee
```

The matrix adapter currently supplies one default station power and energy
price because the charger matrix contains no station-specific values. Its high
default station-power cap does not make charging instantaneous or fix it at 45
minutes: effective power is still limited by the assigned vehicle, so charging
duration remains energy-based.

The first version assumes 100% charging efficiency and a constant `EnergyRate_v`. It does not model effects from payload, speed, gradient, weather, or temperature.

The first version requires:

```text
MinReserve_v <= InitialBattery_v <= UsableBattery_v
BatteryAfterLeg >= MinReserve_v
```

It starts each vehicle at `InitialBattery_v` and uses full charging. `InitialBattery_v` is the state after overnight depot charging; the heuristic does not add another charging activity before the first trip. It should normally equal `UsableBattery_v` unless the input scenario deliberately specifies a lower morning state. Partial charging is not used until both methods support it.

Energy already stored in the initial battery is not free. After the final trip of each used vehicle:

```text
EndOfDayRecharge_v =
    max(0, InitialBattery_v - FinalBattery_v)

EndOfDayRechargeCost_v =
    EndOfDayRecharge_v * DepotEnergyPrice
```

Station charging during the day and end-of-day depot restoration are both paid. This balances the energy consumed over the planning day without forcing an unnecessary final charging stop.

In the first version, end-of-day recharge takes place outside the planning horizon. Its cost is included, but its duration does not affect shift feasibility or `total_time`. Depot charging between trips remains inside the planning horizon and uses:

```text
EffectiveDepotChargingPower_v =
    min(DepotChargingPower, MaxChargingPower_v)
```

`KmCost_v` excludes electricity. The road operating cost is:

```text
RoadOperatingCost_{v,e} =
    LenKm_e * KmCost_v
```

This avoids charging the same electricity once on the edge and again at the station. Total cost separates:

```text
vehicle activation cost
trip dispatch or reload cost
non-energy road operating cost
station charging cost
end-of-day depot recharge cost
```

The exact identity is:

```text
total_cost =
    total_activation_cost
    + total_trip_cost
    + total_road_operating_cost
    + total_station_charging_cost
    + total_end_of_day_recharge_cost
```

`total_station_charging_cost` includes charging at public stations and depot charging between trips. It excludes only the separately reported end-of-day restoration cost.

### 5.3 Time

Trip duration includes:

```text
initial loading time before the first trip
travel time
customer service time
charging time
driver break time
depot reload time between trips
```

For one used vehicle:

```text
FirstActivityStart_v =
    start of loading before the first trip

VehicleOperatingTime_v =
    last_trip_return_v - FirstActivityStart_v
```

This includes waiting, reload, charging, and breaks between its first departure and final return. The objective time is:

```text
total_time =
    sum VehicleOperatingTime_v for all used vehicles
```

The latest vehicle return, or makespan, is exported separately and is not used as `total_time`.

### 5.4 Combined Score

The heuristic evaluates a solution with:

```text
objective =
    w_risk * total_risk / fixed_risk_scale
    + w_cost * total_cost / fixed_cost_scale
    + w_time * total_time / fixed_time_scale
```

All scales are calculated once for an instance and remain fixed during construction and VNS.

For every customer `c`, first generate the set `SingleTrip_c` of feasible single-customer reference trips:

```text
Depot -> c -> Depot
```

These trips use compatible physical vehicles, rule-feasible paths, required charging, loading, service time, and the same evaluator as the heuristic. First calculate:

```text
epsilon = 1e-9

reference_risk =
    sum min_risk(t) for t in SingleTrip_c over all c

reference_cost =
    sum min_cost(t) for t in SingleTrip_c over all c

reference_time =
    sum min_duration(t) for t in SingleTrip_c over all c

fixed_risk_scale =
    reference_risk if reference_risk > epsilon else 1.0

fixed_cost_scale =
    reference_cost if reference_cost > epsilon else 1.0

fixed_time_scale =
    reference_time if reference_time > epsilon else 1.0
```

Each minimum is calculated independently. The reference cost includes road operating, charging, trip, and one activation cost for its selected vehicle. The scales are reference magnitudes, not bounds. Their values are exported for reproducibility. They may be used for an objective-gap comparison only if the solver explicitly uses the same scale construction.

If `reference_risk <= epsilon`, risk is inactive for that instance and this fact is recorded in metadata. The fallback value prevents division by zero; it does not replace a positive risk scale below 1.

If `SingleTrip_c` is empty, customer `c` is individually infeasible and construction does not start until the reason is reported.

The default experiment uses:

```text
w_risk = 0.50
w_cost = 0.30
w_time = 0.20
```

The Small and Medium instances additionally use `(0.30, 0.50, 0.20)` to
examine the risk-cost trade-off while keeping the time weight fixed. Large uses
the default weights for the scalability experiment.

## 6. Road-Path Preprocessing

### 6.1 Mapping

Map the depot, customers, charging stations, and approved break nodes to eligible road-network nodes.

The maximum mapping distance is:

```text
max_mapping_distance_m = 1000
```

A location outside this hard threshold is reported as:

```text
mapping_infeasible
```

KDTree mapping may be used for performance, but nearest-node lookup does not replace the threshold check.

### 6.2 Apply Implemented Road Rules First

For each hazardous-goods class:

1. remove forbidden tunnel and ADR edges;
2. apply the agreed highway preference or penalty;
3. build the class-specific permitted graph;
4. generate path alternatives on that graph.

An ordinary shortest-path corridor must not be cropped first and restricted afterward. That order can remove the only permitted detour.

In this document, "legal" means feasible under the implemented ADR/tunnel and project rules. It is not a claim of complete legal compliance with every substance-, quantity-, vehicle-, and exemption-specific ADR provision.

### 6.3 Pairwise Candidate Paths

Generate paths for all required ordered stop pairs:

```text
depot -> customer
customer -> customer
customer -> depot
customer -> candidate charging station
candidate charging station -> the same customer
```

For every matrix-backed instance, each customer keeps at most its three nearest charging stations by rule-feasible road distance. Straight-line distance may shortlist stations, but it does not determine final feasibility or rank. The two charging paths are stored separately because one-way roads and direction-specific restrictions can make them different.

Candidate profiles may include:

- shortest or lowest-cost path;
- lowest-risk path;
- weighted risk-cost path;
- one or more rule-feasible alternatives.

Loaded paths use class-specific restrictions and risk. The final empty return uses the same implemented class restrictions in the first version, but its cargo-related risk is zero.

### 6.4 Network Reduction

Large-network preprocessing may use:

- chunked edge loading;
- a depot-containing reachable component;
- degree-chain contraction;
- rule-feasible path corridors;
- path caching.

Before component filtering, verify for each mapped customer that:

- the customer is reachable from the depot on its class-specific graph;
- the depot is reachable from the customer under the first-version return rules.

If either check fails, report `no_legal_path`. Do not silently remap the customer to another node to keep it in a selected component.

Only after these checks may a depot-containing component be retained. Charging and break nodes are kept only when they are reachable and useful for at least one required relation.

Contraction must preserve direction, original arc IDs, geometry, length, time, risk, energy, and implemented permission. Depot, customer, charging, and break nodes must be protected before contraction.

If no path satisfying the implemented rules exists after successful mapping, report:

```text
no_legal_path
```

Do not create a selectable dummy arc with an artificial large distance.

## 7. Sequential Route Construction

### 7.1 State

For every vehicle:

```text
current_location
available_time
completed_trips
current_hazard_class
daily_driving_time
daily_working_time
```

For every trip:

```text
vehicle_id
trip_id
hazard_class
stop_sequence
start_time
return_time
initial_load
remaining_load_at_each_stop
battery_at_each_stop
arrival_and_departure_times
selected_path_for_each_leg
risk
cost
time
```

### 7.2 Initial Trips

Start with no active trip and all customers in `unserved_customers`.

Select an available vehicle and create:

```text
[Depot, Depot]
```

The vehicle and trip hazardous-goods class are determined by the first accepted customer.

Before the first departure, add `InitialLoadTime_v`. If no separate value is available, the first version sets:

```text
InitialLoadTime_v = ReloadTime_v
```

### 7.3 Candidate Insertion

For each unserved customer and compatible vehicle-trip:

1. test the allowed insertion positions;
2. select rule-feasible path alternatives for the two affected legs;
3. update initial and remaining payload;
4. simulate arrival, service, charging, break, and return times;
5. simulate battery consumption;
6. calculate the change in risk, cost, and time;
7. reject any infeasible insertion.

The insertion metric is:

```text
insertion_score =
    w_risk * delta_risk / fixed_risk_scale
    + w_cost * delta_cost / fixed_cost_scale
    + w_time * delta_time / fixed_time_scale
```

Within the current trip, choose the feasible insertion with the lowest score.
When a new trip is seeded, the optional `regret_2` variant first groups the
vehicle candidates by customer. A customer with only one feasible vehicle
candidate has highest priority. Otherwise:

```text
regret_2(c) =
    second_best_insertion_score(c)
    - best_insertion_score(c)
```

The customer with the largest regret seeds the new trip using its best
vehicle candidate. This reserves scarce vehicle, time, and compatibility
options before easier customers consume them. Once that trip is open, ordinary
best insertion extends it; the number of feasible positions inside one trip is
not treated as vehicle scarcity.

Candidate ties are resolved deterministically by:

```text
insertion_score
-> delta_risk
-> delta_cost
-> delta_time
-> vehicle_id
-> trip_id
-> customer_id
-> insertion_position
-> path_id
```

The optional `hardest_first` seed rule selects the customer whose best
feasible new-trip candidate has the largest incremental operating time. It is
useful when long-distance customers would otherwise remain until the fleet
has too little time for them. Trip extension still uses the ordinary minimum
insertion score.

### 7.4 Closing a Trip

When no further customer can be inserted:

1. close the trip with a feasible return to the depot;
2. record its return time;
3. add any required depot charging time;
4. update the vehicle schedule.

In the solver-compatible single-trip mode, a new trip can only use a physical vehicle that has not yet been assigned a route. This enforces one `DEPOT -> customers -> DEPOT` route per used vehicle.

In the multi-trip extension, the heuristic additionally allows a vehicle whose previous trip has already finished to start another trip after depot reload and charging, if the shift and daily limits still allow it. If no feasible option exists, report the customer and the exact infeasibility reason.

For an insertion into an existing trip, `delta_cost` includes the changed trip costs and the resulting change in end-of-day recharge cost. For a new trip, it also includes `TripCost_v`; `ActivationCost_v` is added only when the physical vehicle has not been used earlier in the solution.

### 7.5 Bounded Ejection Repair

If construction leaves customers unserved, apply a deterministic depth-one
repair before VND:

1. temporarily remove one served customer;
2. insert one unserved customer into any feasible trip position or new trip;
3. reinsert the removed customer into any feasible position or new trip;
4. accept the exchange only if both customers are served and the total number
   of served customers increases by one.

The search uses the same schedule evaluator and fixed objective scales as
construction. Candidate and time limits are reported explicitly. A limit
result is `search_limit_reached`, not proof that no feasible repair exists.
Each repair result also stores the configured limits and one stop reason:
`completed`, `candidate_limit`, `time_limit`,
`charging_search_incomplete`, or `initial_solution_infeasible`. These fields
are included in the text summary and result metadata so experiment runs
can be reproduced.

### 7.6 Limited Depth-Two Repair

If depth-one repair cannot complete a nearly feasible solution, a bounded
depth-two step may temporarily remove two served customers. The unserved
customer replaces one of their positions, after which both removed customers
are reinserted in both possible orders. Only a fixed number of the best
primary candidates is continued, and the same candidate and time limits
remain active. This optional repair is skipped when construction or
depth-one repair already serves every customer; it was required for the
complete Large-instance heuristic result.

Within the active limits, feasible completions from both reinsertion orders
are compared by objective, risk, cost, time, and the deterministic schedule
key. Invalid construction or depth-one input is preserved as
`initial_solution_infeasible` and is never reinterpreted as a repairable
partial schedule.

## 8. Charging and Schedule Feasibility

### 8.1 Charging Repair

Charging repair is tested when the next leg would violate either the battery reserve or the continuous-driving limit. It is also tested proactively by propagating feasible battery, time, and driving states over all remaining ordered stops. Dominated states with no more battery and no better time resources are removed. The shared first-version charging model uses a restricted side-trip:

```text
Customer i
-> Charging station h
-> Customer i
-> next stop j
```

The vehicle must return to the customer from which the charging detour started. It cannot continue directly from the station to the next customer. This restriction reduces the charging matrix but may exclude a better unrestricted EV route.

For each repair:

1. identify the customer before the infeasible leg;
2. test all available candidates among that customer's three stations;
3. evaluate both directed paths of the side-trip;
4. add charging time, cost, and any qualifying driver break;
5. return to the same customer without repeating delivery or service;
6. rebuild the rest of the schedule;
7. choose the feasible station with the smallest objective increase.

The initial version charges to `UsableBattery_v`. Duration and cost are calculated from charged energy, station power, and station price as defined in Section 5.2. Partial charging is a later extension unless the solver adopts it as well.

If undelivered cargo remains after service at `Customer i`, both side-trip legs remain loaded and receive cargo-related HazMat risk. If no cargo remains, both legs are empty. Returning to the customer is a technical revisit: it does not reset capacity, reload the vehicle, repeat service, or increase the served-customer count.

The same departure transition checks driver-break feasibility for ordinary travel, departure to a station, and departure after the technical revisit. Charging search is bounded separately for each top-level schedule evaluation by `MaxChargingBranchEvaluations`; rejected construction proposals do not consume the budget of later proposals. If untested station states remain when the limit is reached, the result is `charging_search_incomplete`, not ordinary route infeasibility. The final-schedule branch count is exported with the result.

State propagation preserves the complete set of failure causes across the non-dominated frontier. If any state still has a battery or break failure, the previous customer receives a proactive charging test even when another state fails for time or shift. Only after those repair options fail is the best unavoidable structural, time-window, shift, or daily-limit reason reported. Adding an unused legal charging candidate must therefore not turn a feasible route into an infeasible route.

### 8.2 Schedule Simulation

A single schedule evaluator must be used during construction and VNS. It updates:

```text
arrival time
waiting time
service time
departure time
continuous driving time
break time
battery
remaining payload
trip return time
daily driving and working time
```

Breaks may only occur at a stop that the trip actually visits and that is allowed for a break.

When a charging stop is also break-eligible and the break is long enough to qualify:

```text
stop_duration =
    max(charging_duration, qualifying_break_duration)
```

The first version therefore allows charging and a driver break to overlap. Customer service, loading, and reloading do not overlap with a driver break.

## 9. Variable Neighborhood Descent and Search

The construction phase provides an incumbent solution. The implemented
pipeline then applies deterministic best-improvement VND followed by
reproducible Basic VNS shaking and nested VND.

### Relocate

Move one customer to another position in the same trip or to a compatible trip.

### Swap

Exchange two customers in the same trip or between two compatible trips.

### 2-opt

Reverse a customer subsequence within one trip and rebuild its path and schedule.

### Trip Reassignment

Assign a complete trip to another compatible vehicle.

### Path Change

Replace one leg path with another rule-feasible candidate path.

### Charging-Stop Change

Insert, remove, or replace a charging station.

Every move is evaluated by the same feasibility and objective functions used during construction.

The toy schedule explicitly stores customer sequences and trips. It therefore implements six schedule neighborhoods. A path change is not yet a separate move because the toy has one leg per OD pair. Charging choices are rebuilt automatically by the schedule evaluator for every candidate, so charging alternatives are already reconsidered without storing a charging stop in the move itself. Explicit path and charging-stop neighborhoods become useful when the real-data representation exposes several alternatives.

Inter-trip relocate inserts a customer only into an existing trip. It does not create a new single-customer trip or activate an unused vehicle. The current toy can activate an unused vehicle only by reassigning a complete trip. This restricted neighborhood keeps the first VND small but can exclude improvements that require splitting a trip.

### Reproducible VND Configuration

The implemented VND uses:

```text
acceptance = strict improvement greater than 1e-9
local_search = best-improvement VND
equal_solution_acceptance = false
max_neighborhood_passes = 1000
```

The fixed VND neighborhood order is:

```text
1. intra-trip relocate
2. intra-trip 2-opt
3. intra-trip swap
4. inter-trip relocate
5. inter-trip swap
6. trip reassignment
```

Each neighborhood evaluates all unique candidate schedules and selects its deterministic best strict improvement. Ties are resolved by objective, risk, cost, time, complete schedule, and move description. After an improving move, VND restarts at neighborhood 1.

VND stops when a complete neighborhood cycle finds no improvement or the neighborhood-pass limit is reached. A candidate rejected with `charging_search_incomplete` is not treated as proven infeasible. If a complete cycle contains such a candidate and accepts no later improvement, the final status is `search_limit_reached`, while the feasible incumbent is retained. Accepting a move clears incomplete-search evidence from the previous cycle because the incumbent and its neighborhoods have changed.

When VND is nested inside VNS, it receives the same absolute monotonic deadline. VND checks it before every candidate evaluation and between neighborhood passes. A candidate evaluation that has already started may finish, but no further candidate is started after expiry. The best accepted feasible incumbent is returned with `time_limit_reached`.

The result reports the initial and final objective, accepted moves, evaluated candidate count, unresolved incomplete candidate count and neighborhoods, neighborhood passes, and runtime.

### Reproducible VNS Shaking

The implemented Basic VNS starts from the VND result. It selects one unique schedule move at random from the current neighborhood, rebuilds charging and the complete schedule through the shared evaluator, and runs VND from every feasible shaken solution. A locally improved shaken solution replaces the incumbent only when its objective is better by more than `1e-9`; the search then restarts at the first neighborhood. Otherwise it continues with the next neighborhood.

The configuration is:

```text
random_seed = 42
max_vns_iterations = 1000
max_vns_seconds = 60
max_vnd_neighborhood_passes = 1000
```

VNS computes one absolute monotonic deadline at startup. It checks that deadline after candidate generation, immediately after the atomic shake evaluation, and after nested VND. The same deadline is passed into VND. VNS therefore never starts nested local search after the shared budget has expired, although an atomic evaluation already in progress may finish.

VNS stops after a complete neighborhood cycle without an accepted basin improvement, or when the iteration or runtime limit is reached. `neighborhoods_exhausted` does not claim global optimality. Search-incomplete shake evaluations and bounded VND runs are retained for the current incumbent. This includes an initial VND ending with a charging-search, iteration, or time limit; when it has no specific neighborhood diagnosis, the result records `initial_vnd`. If the final completed cycle contains unresolved evidence, the status is `search_limit_reached`. Accepting a fully searched new incumbent clears evidence from the previous cycle.

Seed 42 is used for deterministic debugging and the standard demonstration. Final stochastic experiments use at least:

```text
experiment_seeds = [11, 23, 42, 67, 89]
```

Ten fixed seeds are preferred when runtime permits. Report best objective, mean objective, objective standard deviation, mean runtime, and number of feasible runs. Solver-gap comparison uses the best feasible heuristic result, while mean and standard deviation describe robustness.

## 10. Feasibility Checks

A solution is feasible only if:

- every customer order is served exactly once;
- every active trip starts and ends at the depot;
- every selected road path is connected and feasible under the implemented ADR/tunnel rules;
- no trip mixes incompatible hazardous goods;
- the assigned physical vehicle is compatible with the trip class;
- total trip demand does not exceed vehicle capacity;
- payload decreases after each delivery and resets only at the depot;
- customer time windows and service times are respected;
- battery never falls below `MinReserve_v` after any edge or leg, on arrival at a charging station, or on the final depot return;
- charging occurs only at visited charging nodes;
- trips assigned to one vehicle do not overlap;
- reload, charging, and break times are included;
- shift, daily driving, and daily working limits are respected;
- risk, cost, and time totals equal the selected trips and paths.

Infeasibility should be reported with a specific status:

```text
mapping_infeasible
no_legal_path
capacity_infeasible
commodity_incompatible
charging_infeasible
charging_search_incomplete
time_window_infeasible
shift_infeasible
input_data_error
```

The overall run status is one of:

```text
feasible
infeasible
partial_infeasible
search_limit_reached
input_data_error
```

`partial_infeasible` means that construction produced trips but left at least one customer unserved. It must never be reported or compared as a feasible solution.

For every unserved customer, the result keeps distinct rejection reasons from both new-trip seed tests and all insertion positions. Stale insertion diagnostics are cleared as soon as any feasible insertion or new-trip seed candidate is found for that customer, even if a different candidate is selected in that round, and again when the customer is served. If any still-relevant rejection contains `charging_search_incomplete`, the run status is `search_limit_reached` rather than `partial_infeasible`. Completed trips retain their matching metrics, including end-of-day energy restoration.

`input_data_error` means that preprocessing cannot safely interpret a required field, unit, transformation, or parameter. It is not a routing infeasibility.

`search_limit_reached` means that the bounded heuristic did not inspect every required charging continuation. It must not be interpreted as proof that no feasible route exists.

## 11. Output

The primary output is one machine-readable JSON document. Derived comparison
tables, maps, or text summaries may be generated from the same payload.
`metadata.repair`, `metadata.depth_two_repair`, `metadata.vnd`, and
`metadata.vns` preserve the configuration, status, stop reason, and search
diagnostics of the stages that were actually executed. `schedule_details`
contains each vehicle's trips, visits, legs, timing, load, battery, charging,
break, risk, and cost state. The export rejects a final evaluation, status, or
objective scale that does not match the supplied VND/VNS run.
Newly generated payloads use `metadata.scenario_parameters` to record the
service, loading, shift, driving, break, charging, price, session-fee, and
battery-reserve settings used to build the instance. Older committed snapshots
that predate this field remain identifiable through their stage metadata.

### Run Summary

```text
status
objective_weights_and_scales
normalized_objective_value
total_risk
total_activation_cost
total_trip_cost
total_road_operating_cost
total_station_charging_cost
total_end_of_day_recharge_cost
total_cost
total_distance
total_travel_time
total_service_time
total_charging_time
total_waiting_time
total_break_time
total_time
makespan
final_battery_by_vehicle
end_of_day_recharge_by_vehicle
vehicles_used
trips_used
served_and_unserved_customers
normalization_and_risk_metadata
scenario_parameters
construction_strategy_from_the_actual_run
runtime_breakdown
charging_branch_evaluations
vnd_initial_and_final_objective
vnd_accepted_moves
vnd_evaluated_candidates
vnd_incomplete_candidates_and_neighborhoods
vnd_neighborhood_passes
vns_random_seed_and_status
vns_iterations_and_accepted_improvements
vns_shake_and_nested_vnd_statistics
vns_incomplete_search_diagnostics
repair_status_moves_candidates_and_runtime
repair_limits_and_stop_reason
```

### Selected Trips and Stops

```text
vehicle_id
trip_id
hazard_class
stop_sequence
stop_type
arrival_time
departure_time
delivered_quantity
remaining_load
battery_before_and_after
charging_or_break_duration
trip_start_and_return_time
final_vehicle_battery
```

`stop_sequence` preserves charging stations and technical customer revisits, for example `Customer i -> Station h -> Customer i`. A customer-order-only sequence is insufficient for checking battery, time, risk, and cost.

### Solver-Compatible Route View

The JSON contains a compact solver-facing route view:

```python
heuristic_routes = {
    "MAN_eTGX": ["DEPOT", "C1", "C2", "DEPOT"],
}
```

Its key is the solver's unique physical-vehicle name (`solver_name`, falling back to vehicle type). Its list contains only customers and depot nodes. In solver-compatible single-trip outputs, each used vehicle has exactly one route list. In multi-trip extension outputs, several trips by one vehicle are flattened with an intermediate `DEPOT` for exchange and diagnostics only. Charging stations and technical revisits remain in the full selected-stop output and are not discarded from heuristic evaluation. This is an exchange representation; it becomes a warm start only after a solver importer validates and applies it.

For the current single-trip solver, a route proposal is solver-compatible only
when the exported metadata reports:

```text
single_trip_per_vehicle = True
route_structure_compatible = True
```

In that case every active vehicle has exactly one `DEPOT -> customers -> DEPOT`
route and no intermediate depot node. A flattened route containing an
intermediate `DEPOT` represents a multi-trip solution. It is valid for the
heuristic extension but must not be imported as a warm start for the current
single-trip solver.

### Selected Legs or Edges

```text
vehicle_id
trip_id
from_stop
to_stop
path_id
edge_or_arc_sequence
distance
time
risk
cost
energy
implemented_rules_feasible
load_state
```

The map is a presentation layer derived from these outputs, not a separate source of result values.

## 12. Solver Comparison

The final direct comparison is based on the single-trip route structure used by
the solver. Therefore, only heuristic outputs with `single_trip_per_vehicle =
True` and `route_structure_compatible = True` are used for solver comparison or
warm-start exchange. Multi-trip heuristic outputs remain useful as an extension
showing more flexible fleet utilization, but they are not direct objective-gap
benchmarks for the current MILP solver.

Solver and heuristic results are comparable only when they use:

- the same physical vehicles and customer orders;
- the same quantity conversion;
- the same road paths or pairwise path table;
- the same risk fields, normalization, and hazardous-goods factors;
- the same fixed, trip, variable, energy, and charging costs;
- the same time, battery, compatibility, and charging rules;
- the same objective weights and scales.

Compare:

- feasibility and unserved customers;
- total risk;
- total cost and its components;
- total distance and time;
- vehicles and routes used;
- trips used, with trips equal to active vehicles in the current single-trip comparison;
- charging decisions;
- algorithm runtime;
- end-to-end runtime;
- solver objective, best bound, and gap when available.

If the solver proves optimality under the same evaluator:

```text
heuristic_gap_percent =
    (heuristic_objective - solver_objective)
    / solver_objective
    * 100
```

Results generated with a different route structure, for example multi-trip
heuristic runs against a single-trip solver, are not valid quality benchmarks.

## 13. Pseudocode

```text
Input:
    physical vehicles V
    customer orders C
    depot, charging stations, road graph
    risk, permission, cost, time, and energy data
    objective weights
    route-structure mode: single-trip for solver comparison,
        optional multi-trip extension for sensitivity runs

Validate input:
    verify required fields, units, source semantics, and physical fleet
    if a required definition is missing or ambiguous:
        return input_data_error

Preprocess:
    map all relevant locations with a hard distance threshold
    for each hazardous-goods class:
        remove forbidden road edges
        generate rule-feasible pairwise path alternatives
    generate empty-return alternatives
    generate feasible single-customer reference trips
    calculate fixed risk, cost, and time scales once

Initialize:
    unserved_customers = C
    solution = no trips
    initialize each vehicle at the depot and shift start
    schedule initial loading before the first trip of a used vehicle

Construct:
    while unserved_customers is not empty:
        seed_candidates = []

        for each vehicle that can start a trip:
            if single-trip mode and the vehicle already has a trip:
                skip this vehicle
            for each compatible unserved customer:
                create a temporary depot-to-customer-to-depot trip
                simulate load, battery, time, breaks, and depot return
                if feasible:
                    calculate insertion score
                    add seed candidate

        if seed_candidates is empty:
            return partial solution with explicit infeasibility reasons

        select a seed by best insertion or regret-2
        current_trip = selected depot-to-customer-to-depot trip
        remove its customer from unserved_customers

        repeat:
            insertion_candidates = []

            for each compatible unserved customer:
                for each allowed position in current_trip:
                    rebuild affected paths
                    simulate load, battery, time, breaks, and depot return
                    if feasible:
                        calculate insertion score
                        add insertion candidate

            if insertion_candidates is empty:
                break

            accept the deterministic minimum insertion candidate
            update current_trip
            remove its customer from unserved_customers

        finalize current_trip
        append it to the selected vehicle
        update vehicle availability and daily resource use
        in single-trip mode, mark the vehicle unavailable for further trips
        in multi-trip extension mode, allow another trip only if depot
            reload, charging, shift, and daily limits remain feasible

Improve with VND:
    current_solution = constructed solution
    neighborhood = first schedule neighborhood

    while a neighborhood remains and the pass limit is not reached:
        generate all unique schedules in the current neighborhood
        evaluate each schedule with the shared feasibility function
        keep the deterministic best strict improvement

        if an improvement exists:
            accept it
            restart at the first neighborhood
        else:
            continue with the next neighborhood

Improve with VNS:
    best_solution = VND result
    neighborhood = first schedule neighborhood
    initialize a private random generator with the experiment seed

    while a neighborhood remains and no limit is reached:
        select one unique random shake from the current neighborhood
        rebuild charging and evaluate the complete shaken schedule
        stop before VND if the shared deadline has expired

        if the shaken schedule is feasible:
            run VND from the shaken schedule with the same deadline

            if the local result strictly improves best_solution:
                accept it
                restart at the first neighborhood
                continue

        record any incomplete search evidence
        continue with the next neighborhood

Validate and export:
    calculate final battery for every used vehicle
    calculate end-of-day recharge energy and cost
    validate every customer, trip, vehicle, path, resource, and total
    export summary, trips/stops, legs/edges, runtimes, and metadata
```

## 14. Implementation Status and Next Steps

The shared engine covers data structures, schedule evaluation, sequential
insertion, bounded repair, charging repair, deterministic VND, reproducible
Basic VNS, and multi-trip reuse as an extension. The reported
solver-comparison experiments should use single-trip outputs. The committed
`Result` snapshots document different search stages: Small and Medium contain
construction results, while the 47-customer Large snapshot contains
construction plus bounded repair. A final experiment must regenerate and
export the complete configured pipeline instead of assuming that every stored
snapshot already contains VND and VNS. The earlier 9-vehicle Large result
remains a multi-trip heuristic extension result. The CLI and Python API expose
the route-structure choice through `--single-trip-per-vehicle` /
`single_trip_per_vehicle=True`.

The remaining steps are:

1. compare heuristic and solver JSON results for identical inputs, objective
   definitions, scales, runtime boundaries, and the single-trip route
   structure;
2. expose explicit path and charging-stop moves if a future data
   representation provides several alternatives per OD relation;
3. report risk, cost, time, feasibility, and runtime separately.

## 15. References Used for the Heuristic

- Zografos, K. G., and Androutsopoulos, K. N. (2004). "A heuristic algorithm for solving hazardous materials distribution problems." European Journal of Operational Research, 152(2), 507-519. https://doi.org/10.1016/S0377-2217(03)00041-9
- Androutsopoulos, K. N., and Zografos, K. G. (2012). "A bi-objective time-dependent vehicle routing and scheduling problem for hazardous materials distribution." EURO Journal on Transportation and Logistics, 1, 157-183. https://doi.org/10.1007/s13676-012-0004-y
- Bula, G. A., Prodhon, C., Gonzalez, F. A., Afsar, H. M., and Velasco, N. (2017). "Variable neighborhood search to solve the vehicle routing problem for hazardous materials transportation." Journal of Hazardous Materials, 324, 472-480. https://doi.org/10.1016/j.jhazmat.2016.11.015
- Cattaruzza, D., Absi, N., Feillet, D., and Vigo, D. (2014). "An iterated local search for the multi-commodity multi-trip vehicle routing problem with time windows." Computers & Operations Research, 51, 257-267. https://doi.org/10.1016/j.cor.2014.06.006
- Schneider, M., Stenger, A., and Goeke, D. (2014). "The Electric Vehicle-Routing Problem with Time Windows and Recharging Stations." Transportation Science, 48(4), 500-520. https://doi.org/10.1287/trsc.2013.0490
- Cuneo, V., Nigro, M., Carrese, S., Ardito, C. F., and Corman, F. (2018). "Risk based, multi objective vehicle routing problem for hazardous materials: A test case in downstream fuel logistics." Transportation Research Procedia, 30, 43-52. https://doi.org/10.1016/j.trpro.2018.09.006
