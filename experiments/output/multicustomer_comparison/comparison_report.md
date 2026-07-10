# Multi-Customer Solver-Heuristic Comparison

## Scope

This report compares solver and heuristic JSON outputs for the multi-customer single-depot instances. If a matching solver JSON is not available yet, the scenario is kept as a heuristic-only row with `comparison_status = solver_missing`.

Expected solver location:

`experiments\data\solver_output_multicustomer/<scenario>/solver_result.json`

The solver JSON should use the same top-level structure as the heuristic result JSON: `status`, `routes`, `metadata`, `objective`, `metrics`, and `runtime_seconds`.

## Scenario Summary

| scenario | comparison_status | dataset_name | risk_weight | cost_weight | time_weight | solver_status | solver_solution_interpretation | heuristic_status | solver_served_customers | heuristic_served_customers | solver_total_risk | heuristic_total_risk | solver_total_cost | heuristic_total_cost | solver_runtime_total_algorithm_seconds | heuristic_runtime_total_algorithm_seconds | solver_cbc_last_progress_seconds | solver_cbc_incumbent | solver_cbc_best_bound | solver_cbc_relative_gap_percent |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| large_10_vehicle_extra_volvo_single_trip | solver_missing | Large | 0.5 | 0.3 | 0.2 | missing | missing | feasible |  | 50 |  | 1715.7787 |  | 17016.8805 |  | 113.1544 |  |  |  |  |
| medium_risk_0.3_cost_0.5_time_0.2 | both_feasible | Medium | 0.3 | 0.5 | 0.2 | feasible | reported_optimality_unverified | feasible | 20 | 20 | 5.1894 | 4.84 | 7982.3085 | 7506.4525 | 17995.816 | 73.6438 |  |  |  |  |
| medium_risk_0.5_cost_0.3_time_0.2 | both_feasible | Medium | 0.5 | 0.3 | 0.2 | feasible | reported_optimality_unverified | feasible | 20 | 20 | 4.7665 | 4.84 | 7154.2002 | 7506.4525 | 17995.8534 | 78.5861 |  |  |  |  |
| small_risk_0.3_cost_0.5_time_0.2 | both_feasible | Small | 0.3 | 0.5 | 0.2 | feasible | optimal | feasible | 10 | 10 | 3.2205 | 3.2697 | 2347.4623 | 2651.6176 | 604.6999 | 14.2726 |  |  |  |  |
| small_risk_0.5_cost_0.3_time_0.2 | both_feasible | Small | 0.5 | 0.3 | 0.2 | feasible | optimal | feasible | 10 | 10 | 3.2205 | 3.2697 | 2347.4623 | 2651.6176 | 225.9708 | 7.1686 |  |  |  |  |

## Method Summary

| scenario | method | source_file | dataset_name | status | search_status | solution_interpretation | risk_weight | cost_weight | time_weight | objective_value | served_customers | unserved_customers | excluded_customers | total_risk | total_cost | total_activation_cost | total_road_operating_cost | total_station_charging_cost | total_end_of_day_recharge_cost | total_distance_km | total_time_minutes | makespan_minute | runtime_construction_seconds | runtime_repair_seconds | runtime_vnd_seconds | runtime_vns_seconds | runtime_total_algorithm_seconds | active_vehicles | route_count | single_trip_per_vehicle | route_structure_compatible | cbc_log_file | cbc_log_has_final_termination | cbc_log_last_progress_seconds | cbc_log_nodes | cbc_log_incumbent | cbc_log_best_bound | cbc_log_relative_gap_percent |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| large_10_vehicle_extra_volvo_single_trip | heuristic | experiments\data\heuristic_output_multicustomer\large_10_vehicle_extra_volvo_single_trip\heuristic_result.json | Large | feasible | feasible | feasible | 0.5 | 0.3 | 0.2 | 0.4724 | 50.0 | 0.0 | 0.0 | 1715.7787 | 17016.8805 | 11800.0 | 2533.8231 | 1942.2836 | 740.7738 | 4217.5204 | 5940.1179 | 768.5703 | 113.1544 |  |  |  | 113.1544 | 10.0 | 10.0 | True | True |  |  |  |  |  |  |  |
| large_10_vehicle_extra_volvo_single_trip | solver |  | large_10_vehicle_extra_volvo_single_trip | missing | missing | missing |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| medium_risk_0.3_cost_0.5_time_0.2 | heuristic | experiments\data\heuristic_output_multicustomer\medium_risk_0.3_cost_0.5_time_0.2\heuristic_result.json | Medium | feasible | time_limit_reached | time_limit_reached | 0.3 | 0.5 | 0.2 | 0.283 | 20.0 | 0.0 | 0.0 | 4.84 | 7506.4525 | 5200.0 | 1093.9609 | 1212.4916 | 0.0 | 1982.743 | 2933.4751 | 746.4297 | 4.1424 | 0.0144 | 59.4868 | 10.0002 | 73.6438 | 5.0 | 5.0 | True | True |  |  |  |  |  |  |  |
| medium_risk_0.3_cost_0.5_time_0.2 | solver | experiments\data\solver_output_multicustomer\medium_output_risk0.3_cost0.5_time02\solver_medium_output.json | Solver_Instance | feasible | optimal | reported_optimality_unverified | 0.3 | 0.5 | 0.2 | 0.3062 | 20.0 | 0.0 | 0.0 | 5.1894 | 7982.3085 | 6400.0 | 1278.0561 | 304.2524 | 0.0 | 2257.5278 | 3287.022 | 780.0 |  |  |  |  | 17995.816 | 6.0 | 6.0 | True |  |  |  |  |  |  |  |  |
| medium_risk_0.5_cost_0.3_time_0.2 | heuristic | experiments\data\heuristic_output_multicustomer\medium_risk_0.5_cost_0.3_time_0.2\heuristic_result.json | Medium | feasible | time_limit_reached | time_limit_reached | 0.5 | 0.3 | 0.2 | 0.2583 | 20.0 | 0.0 | 0.0 | 4.84 | 7506.4525 | 5200.0 | 1093.9609 | 1212.4916 | 0.0 | 1982.743 | 2933.4751 | 746.4297 | 6.4013 | 0.0284 | 62.1548 | 10.0017 | 78.5861 | 5.0 | 5.0 | True | True |  |  |  |  |  |  |  |
| medium_risk_0.5_cost_0.3_time_0.2 | solver | experiments\data\solver_output_multicustomer\medium_output_risk0.5_cost0.3_time02\solver_medium_output.json | Solver_Instance | feasible | optimal | reported_optimality_unverified | 0.5 | 0.3 | 0.2 | 0.2603 | 20.0 | 0.0 | 0.0 | 4.7665 | 7154.2002 | 5600.0 | 1252.8168 | 301.3834 | 0.0 | 2162.3472 | 3195.7023 | 780.0 |  |  |  |  | 17995.8534 | 5.0 | 5.0 | True |  |  |  |  |  |  |  |  |
| small_risk_0.3_cost_0.5_time_0.2 | heuristic | experiments\data\heuristic_output_multicustomer\small_risk_0.3_cost_0.5_time_0.2\heuristic_result.json | Small | feasible | time_limit_reached | time_limit_reached | 0.3 | 0.5 | 0.2 | 0.1777 | 10.0 | 0.0 | 0.0 | 3.2697 | 2651.6176 | 2000.0 | 346.174 | 305.4437 | 0.0 | 639.3048 | 1133.0968 | 668.2819 | 0.2486 | 0.0053 | 4.0039 | 10.0149 | 14.2726 | 2.0 | 2.0 | True | True |  |  |  |  |  |  |  |
| small_risk_0.3_cost_0.5_time_0.2 | solver | experiments\data\solver_output_multicustomer\small_output_risk0.3_cost0.5_time0.2\solver_result.json | Solver_Instance | feasible | optimal | optimal | 0.3 | 0.5 | 0.2 | 0.1679 | 10.0 | 0.0 | 0.0 | 3.2205 | 2347.4623 | 2000.0 | 347.4623 | 0.0 | 0.0 | 631.7497 | 1163.1151 | 780.0 |  |  |  |  | 604.6999 | 2.0 | 2.0 | True |  |  |  |  |  |  |  |  |
| small_risk_0.5_cost_0.3_time_0.2 | heuristic | experiments\data\heuristic_output_multicustomer\small_risk_0.5_cost_0.3_time_0.2\heuristic_result.json | Small | feasible | neighborhoods_exhausted | neighborhoods_exhausted | 0.5 | 0.3 | 0.2 | 0.1848 | 10.0 | 0.0 | 0.0 | 3.2697 | 2651.6176 | 2000.0 | 346.174 | 305.4437 | 0.0 | 639.3048 | 1133.0968 | 668.2819 | 0.4348 | 0.0107 | 4.1355 | 2.5876 | 7.1686 | 2.0 | 2.0 | True | True |  |  |  |  |  |  |  |
| small_risk_0.5_cost_0.3_time_0.2 | solver | experiments\data\solver_output_multicustomer\small_output_risk0.5_cost0.3_time0.2\solver_result.json | Solver_Instance | feasible | optimal | optimal | 0.5 | 0.3 | 0.2 | 0.1783 | 10.0 | 0.0 | 0.0 | 3.2205 | 2347.4623 | 2000.0 | 347.4623 | 0.0 | 0.0 | 631.7497 | 1163.1151 | 780.0 |  |  |  |  | 225.9708 | 2.0 | 2.0 | True |  |  |  |  |  |  |  |  |

## Route Overview

| scenario | method | vehicle_name | route | stop_count | customer_count |
| --- | --- | --- | --- | --- | --- |
| large_10_vehicle_extra_volvo_single_trip | heuristic | MAN_eTGX_1 | DEPOT -> C21 -> C2 -> C23 -> C22 -> DEPOT | 6 | 4 |
| large_10_vehicle_extra_volvo_single_trip | heuristic | MAN_eTGX_2 | DEPOT -> C1 -> C25 -> C26 -> C27 -> C28 -> DEPOT | 7 | 5 |
| large_10_vehicle_extra_volvo_single_trip | heuristic | MAN_eTGX_3 | DEPOT -> C35 -> C36 -> C16 -> C43 -> C5 -> DEPOT | 7 | 5 |
| large_10_vehicle_extra_volvo_single_trip | heuristic | MAN_eTGX_4 | DEPOT -> C20 -> C8 -> C6 -> C7 -> C45 -> DEPOT | 7 | 5 |
| large_10_vehicle_extra_volvo_single_trip | heuristic | Mercedes_eActros_600_1 | DEPOT -> C46 -> C47 -> C44 -> DEPOT | 5 | 3 |
| large_10_vehicle_extra_volvo_single_trip | heuristic | Mercedes_eActros_600_2 | DEPOT -> C50 -> C48 -> C49 -> DEPOT | 5 | 3 |
| large_10_vehicle_extra_volvo_single_trip | heuristic | Volvo_FH_Electric_1 | DEPOT -> C18 -> C10 -> C39 -> C17 -> C42 -> C37 -> C38 -> C11 -> C24 -> DEPOT | 11 | 9 |
| large_10_vehicle_extra_volvo_single_trip | heuristic | Volvo_FH_Electric_2 | DEPOT -> C19 -> C9 -> C40 -> C41 -> DEPOT | 6 | 4 |
| large_10_vehicle_extra_volvo_single_trip | heuristic | Volvo_FH_Electric_3 | DEPOT -> C29 -> C3 -> C31 -> C4 -> C13 -> C14 -> C15 -> DEPOT | 9 | 7 |
| large_10_vehicle_extra_volvo_single_trip | heuristic | Volvo_FH_Electric_4 | DEPOT -> C30 -> C34 -> C12 -> C33 -> C32 -> DEPOT | 7 | 5 |
| medium_risk_0.3_cost_0.5_time_0.2 | heuristic | MAN_eTGX_1 | DEPOT -> C11 -> C10 -> C18 -> DEPOT | 5 | 3 |
| medium_risk_0.3_cost_0.5_time_0.2 | heuristic | MAN_eTGX_2 | DEPOT -> C8 -> C4 -> C13 -> C14 -> C15 -> DEPOT | 7 | 5 |
| medium_risk_0.3_cost_0.5_time_0.2 | heuristic | MAN_eTGX_3 | DEPOT -> C20 -> C6 -> C7 -> C5 -> C16 -> DEPOT | 7 | 5 |
| medium_risk_0.3_cost_0.5_time_0.2 | heuristic | MAN_eTGX_4 | DEPOT -> C3 -> C12 -> C19 -> C1 -> DEPOT | 6 | 4 |
| medium_risk_0.3_cost_0.5_time_0.2 | heuristic | Volvo_FH_Electric_2 | DEPOT -> C2 -> C17 -> C9 -> DEPOT | 5 | 3 |
| medium_risk_0.3_cost_0.5_time_0.2 | solver | MAN_eTGX_1 | DEPOT -> C20 -> DEPOT | 3 | 1 |
| medium_risk_0.3_cost_0.5_time_0.2 | solver | MAN_eTGX_2 | DEPOT -> C11 -> C19 -> DEPOT | 4 | 2 |
| medium_risk_0.3_cost_0.5_time_0.2 | solver | MAN_eTGX_3 | DEPOT -> C4 -> C13 -> C15 -> C14 -> DEPOT | 6 | 4 |
| medium_risk_0.3_cost_0.5_time_0.2 | solver | MAN_eTGX_4 | DEPOT -> C12 -> L239 -> C12 -> C3 -> C1 -> DEPOT | 7 | 4 |
| medium_risk_0.3_cost_0.5_time_0.2 | solver | Mercedes_eActros_600_1 |  | 0 | 0 |
| medium_risk_0.3_cost_0.5_time_0.2 | solver | Mercedes_eActros_600_2 |  | 0 | 0 |
| medium_risk_0.3_cost_0.5_time_0.2 | solver | Volvo_FH_Electric_1 | DEPOT -> C8 -> C6 -> C7 -> C5 -> C16 -> DEPOT | 7 | 5 |
| medium_risk_0.3_cost_0.5_time_0.2 | solver | Volvo_FH_Electric_2 | DEPOT -> C2 -> C10 -> C18 -> C17 -> C9 -> DEPOT | 7 | 5 |
| medium_risk_0.3_cost_0.5_time_0.2 | solver | Volvo_FH_Electric_3 |  | 0 | 0 |
| medium_risk_0.5_cost_0.3_time_0.2 | heuristic | MAN_eTGX_1 | DEPOT -> C3 -> C12 -> C19 -> C1 -> DEPOT | 6 | 4 |
| medium_risk_0.5_cost_0.3_time_0.2 | heuristic | MAN_eTGX_2 | DEPOT -> C20 -> C6 -> C7 -> C5 -> C16 -> DEPOT | 7 | 5 |
| medium_risk_0.5_cost_0.3_time_0.2 | heuristic | MAN_eTGX_3 | DEPOT -> C11 -> C10 -> C18 -> DEPOT | 5 | 3 |
| medium_risk_0.5_cost_0.3_time_0.2 | heuristic | MAN_eTGX_4 | DEPOT -> C8 -> C4 -> C13 -> C14 -> C15 -> DEPOT | 7 | 5 |
| medium_risk_0.5_cost_0.3_time_0.2 | heuristic | Volvo_FH_Electric_1 | DEPOT -> C2 -> C17 -> C9 -> DEPOT | 5 | 3 |
| medium_risk_0.5_cost_0.3_time_0.2 | solver | MAN_eTGX_1 | DEPOT -> C11 -> C17 -> C9 -> DEPOT | 5 | 3 |
| medium_risk_0.5_cost_0.3_time_0.2 | solver | MAN_eTGX_2 | DEPOT -> C15 -> C14 -> C13 -> C4 -> DEPOT | 6 | 4 |
| medium_risk_0.5_cost_0.3_time_0.2 | solver | MAN_eTGX_3 |  | 0 | 0 |
| medium_risk_0.5_cost_0.3_time_0.2 | solver | MAN_eTGX_4 |  | 0 | 0 |
| medium_risk_0.5_cost_0.3_time_0.2 | solver | Mercedes_eActros_600_1 |  | 0 | 0 |
| medium_risk_0.5_cost_0.3_time_0.2 | solver | Mercedes_eActros_600_2 |  | 0 | 0 |
| medium_risk_0.5_cost_0.3_time_0.2 | solver | Volvo_FH_Electric_1 | DEPOT -> C10 -> C18 -> C19 -> C20 -> DEPOT | 6 | 4 |
| medium_risk_0.5_cost_0.3_time_0.2 | solver | Volvo_FH_Electric_2 | DEPOT -> C8 -> C6 -> C7 -> C5 -> C16 -> DEPOT | 7 | 5 |
| medium_risk_0.5_cost_0.3_time_0.2 | solver | Volvo_FH_Electric_3 | DEPOT -> C2 -> C1 -> C3 -> C12 -> L146 -> C12 -> DEPOT | 8 | 5 |
| small_risk_0.3_cost_0.5_time_0.2 | heuristic | MAN_eTGX_1 | DEPOT -> C9 -> C2 -> C7 -> C1 -> C8 -> DEPOT | 7 | 5 |
| small_risk_0.3_cost_0.5_time_0.2 | heuristic | MAN_eTGX_2 | DEPOT -> C4 -> C3 -> C10 -> C6 -> C5 -> DEPOT | 7 | 5 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | MAN_eTGX_1 | DEPOT -> C9 -> C4 -> C3 -> C10 -> C6 -> C5 -> DEPOT | 8 | 6 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | MAN_eTGX_2 | DEPOT -> C2 -> C7 -> C1 -> C8 -> DEPOT | 6 | 4 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | MAN_eTGX_3 |  | 0 | 0 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | MAN_eTGX_4 |  | 0 | 0 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | Mercedes_eActros_600_1 |  | 0 | 0 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | Mercedes_eActros_600_2 |  | 0 | 0 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | Volvo_FH_Electric_1 |  | 0 | 0 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | Volvo_FH_Electric_2 |  | 0 | 0 |
| small_risk_0.3_cost_0.5_time_0.2 | solver | Volvo_FH_Electric_3 |  | 0 | 0 |
| small_risk_0.5_cost_0.3_time_0.2 | heuristic | MAN_eTGX_1 | DEPOT -> C9 -> C2 -> C7 -> C1 -> C8 -> DEPOT | 7 | 5 |
| small_risk_0.5_cost_0.3_time_0.2 | heuristic | MAN_eTGX_2 | DEPOT -> C4 -> C3 -> C10 -> C6 -> C5 -> DEPOT | 7 | 5 |
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
- CBC log values describe the final recorded progress line, not a completed solver runtime, unless `solver_cbc_log_has_final_termination` is true.
- The current heuristic snapshots are single-trip compatible results.
- Risk, cost, time, and runtime are kept as separate columns because the project report should discuss these trade-offs separately.