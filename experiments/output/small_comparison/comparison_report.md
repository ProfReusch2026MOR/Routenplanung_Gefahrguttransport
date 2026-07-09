# Multi-Customer Solver-Heuristic Comparison

## Scope

This report compares solver and heuristic JSON outputs for the multi-customer single-depot instances. If a matching solver JSON is not available yet, the scenario is kept as a heuristic-only row with `comparison_status = solver_missing`.

Expected solver location:

`experiments\data\solver_output_multicustomer/<scenario>/solver_result.json`

The solver JSON should use the same top-level structure as the heuristic result JSON: `status`, `routes`, `metadata`, `objective`, `metrics`, and `runtime_seconds`.

## Scenario Summary

| scenario | comparison_status | dataset_name | risk_weight | cost_weight | time_weight | solver_status | heuristic_status | solver_served_customers | heuristic_served_customers | solver_total_risk | heuristic_total_risk | solver_total_cost | heuristic_total_cost | solver_runtime_total_algorithm_seconds | heuristic_runtime_total_algorithm_seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| small_risk_0.3_cost_0.5_time_0.2 | both_feasible | Small | 0.3 | 0.5 | 0.2 | feasible | feasible | 10 | 10 | 3.2205 | 11.3592 | 2347.4623 | 3741.532 |  | 0.4342 |
| small_risk_0.5_cost_0.3_time_0.2 | both_feasible | Small | 0.5 | 0.3 | 0.2 | feasible | feasible | 10 | 10 | 3.2205 | 16.0303 | 2347.4623 | 2790.8264 |  | 0.5717 |

## Method Summary

| scenario | method | source_file | dataset_name | status | search_status | risk_weight | cost_weight | time_weight | objective_value | served_customers | unserved_customers | excluded_customers | total_risk | total_cost | total_activation_cost | total_road_operating_cost | total_station_charging_cost | total_end_of_day_recharge_cost | total_distance_km | total_time_minutes | makespan_minute | runtime_construction_seconds | runtime_repair_seconds | runtime_vnd_seconds | runtime_vns_seconds | runtime_total_algorithm_seconds | active_vehicles | route_count | single_trip_per_vehicle | route_structure_compatible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| small_risk_0.3_cost_0.5_time_0.2 | heuristic | experiments\data\heuristic_output_multicustomer\small_risk_0.3_cost_0.5_time_0.2\heuristic_result.json | Small | feasible | feasible | 0.3 | 0.5 | 0.2 | 0.4577 | 10 | 0 | 0 | 11.3592 | 3741.532 | 3000.0 | 407.0199 | 160.9874 | 173.5247 | 740.0362 | 1196.909 | 514.9488 | 0.4342 |  |  |  | 0.4342 | 3 | 3 | True | True |
| small_risk_0.3_cost_0.5_time_0.2 | solver | experiments\data\solver_output_multicustomer\small_output_risk0.3_cost0.5_time0.2\solver_result.json | Solver_Instance | feasible | optimal | 0.3 | 0.5 | 0.2 | 0.1679 | 10 | 0 | 0 | 3.2205 | 2347.4623 | 2000.0 | 347.4623 | 0.0 | 0.0 | 631.7497 | 1163.1151 | 780.0 |  |  |  |  |  | 2 | 9 | True |  |
| small_risk_0.5_cost_0.3_time_0.2 | heuristic | experiments\data\heuristic_output_multicustomer\small_risk_0.5_cost_0.3_time_0.2\heuristic_result.json | Small | feasible | feasible | 0.5 | 0.3 | 0.2 | 0.576 | 10 | 0 | 0 | 16.0303 | 2790.8264 | 2000.0 | 383.9686 | 323.0397 | 83.8181 | 698.1248 | 1162.9349 | 594.4936 | 0.5717 |  |  |  | 0.5717 | 2 | 2 | True | True |
| small_risk_0.5_cost_0.3_time_0.2 | solver | experiments\data\solver_output_multicustomer\small_output_risk0.5_cost0.3_time0.2\solver_result.json | Solver_Instance | feasible | optimal | 0.5 | 0.3 | 0.2 | 0.1783 | 10 | 0 | 0 | 3.2205 | 2347.4623 | 2000.0 | 347.4623 | 0.0 | 0.0 | 631.7497 | 1163.1151 | 780.0 |  |  |  |  |  | 2 | 9 | True |  |

## Route Overview

| scenario | method | vehicle_name | route | stop_count | customer_count |
| --- | --- | --- | --- | --- | --- |
| small_risk_0.3_cost_0.5_time_0.2 | heuristic | MAN_eTGX_1 | DEPOT -> C4 -> C3 -> C10 -> C6 -> C5 -> DEPOT | 7 | 5 |
| small_risk_0.3_cost_0.5_time_0.2 | heuristic | MAN_eTGX_2 | DEPOT -> C9 -> C2 -> C1 -> C7 -> DEPOT | 6 | 4 |
| small_risk_0.3_cost_0.5_time_0.2 | heuristic | MAN_eTGX_3 | DEPOT -> C8 -> DEPOT | 3 | 1 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | MAN_eTGX_1 | DEPOT -> C2 -> C7 -> C1 -> C8 -> DEPOT | 6 | 4 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | MAN_eTGX_2 | DEPOT -> C9 -> C4 -> C3 -> C10 -> C6 -> C5 -> DEPOT | 8 | 6 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | MAN_eTGX_3 |  | 0 | 0 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | MAN_eTGX_4 |  | 0 | 0 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | Mercedes_eActros_600_1 |  | 0 | 0 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | Mercedes_eActros_600_2 |  | 0 | 0 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | Volvo_FH_Electric_1 |  | 0 | 0 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | Volvo_FH_Electric_2 |  | 0 | 0 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | Volvo_FH_Electric_3 |  | 0 | 0 |
| small_risk_0.5_cost_0.3_time_0.2 | heuristic | MAN_eTGX_1 | DEPOT -> C4 -> C9 -> C2 -> C1 -> C7 -> DEPOT | 7 | 5 |
| small_risk_0.5_cost_0.3_time_0.2 | heuristic | MAN_eTGX_2 | DEPOT -> C3 -> C10 -> C5 -> C6 -> C8 -> DEPOT | 7 | 5 |
| small_risk_0.5_cost_0.3_time_0.2 | solver | MAN_eTGX_1 | DEPOT -> C2 -> C7 -> C1 -> C8 -> DEPOT | 6 | 4 |
| small_risk_0.5_cost_0.3_time_0.2 | solver | MAN_eTGX_2 | DEPOT -> C9 -> C4 -> C3 -> C10 -> C6 -> C5 -> DEPOT | 8 | 6 |
| small_risk_0.5_cost_0.3_time_0.2 | solver | MAN_eTGX_3 |  | 0 | 0 |
| small_risk_0.5_cost_0.3_time_0.2 | solver | MAN_eTGX_4 |  | 0 | 0 |
| small_risk_0.5_cost_0.3_time_0.2 | solver | Mercedes_eActros_600_1 |  | 0 | 0 |
| small_risk_0.5_cost_0.3_time_0.2 | solver | Mercedes_eActros_600_2 |  | 0 | 0 |
| small_risk_0.5_cost_0.3_time_0.2 | solver | Volvo_FH_Electric_1 |  | 0 | 0 |
| small_risk_0.5_cost_0.3_time_0.2 | solver | Volvo_FH_Electric_2 |  | 0 | 0 |
| small_risk_0.5_cost_0.3_time_0.2 | solver | Volvo_FH_Electric_3 |  | 0 | 0 |

## Notes

- Direct quality gaps are only meaningful for rows with `comparison_status = both_feasible`.
- The current heuristic snapshots are single-trip compatible results.
- Risk, cost, time, and runtime are kept as separate columns because the project report should discuss these trade-offs separately.