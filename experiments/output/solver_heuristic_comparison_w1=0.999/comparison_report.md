# Solver vs Heuristic Comparison

## Scenario

- Scenario folder: w1=0.999
- Region: berlin
- Solver run id: 20260624_173211
- Solver network mode: contracted_graph
- Heuristic network mode: solver_cropped
- Risk weight: 0.999
- Cost weight: 0.001
- Energy price: 0.35 EUR/kWh
- Solver status: Optimal

## Main Comparison

| metric | unit | solver | heuristic | heuristic_minus_solver | difference_pct_vs_solver |
| --- | --- | --- | --- | --- | --- |
| feasible_deliveries | count | 3.0 | 3.0 | 0.0 | 0.0 |
| selected_total_length_km | km | 18.009 | 23.7813 | 5.7723 | 32.052 |
| total_risk | risk score | 54.6334 | 47.947 | -6.6864 | -12.239 |
| total_variable_cost | EUR | 18.7871 | 21.0702 | 2.2831 | 12.153 |
| total_fixed_cost | EUR | 640.0 | 540.0 | -100.0 | -15.625 |
| total_cost | EUR | 658.7871 | 561.0702 | -97.7169 | -14.833 |
| core_runtime | seconds | 245.306 | 14.8834 | -230.4226 | -93.933 |
| total_runtime | seconds | 721.557 | 18.0733 | -703.4837 | -97.495 |

## Runtime Comparison

| stage | solver_seconds | heuristic_seconds |
| --- | --- | --- |
| data_preparation | 290.32 | 3.175 |
| network_preparation | 185.712 | 2.5581 |
| mapping |  | 3.3326 |
| model_build | 41.078 |  |
| solver_runtime | 204.228 |  |
| candidate_generation |  | 1.0757 |
| vehicle_assignment |  | 0.0004 |
| result_processing_or_export | 0.22 | 0.0149 |
| core_runtime | 245.306 | 14.8834 |
| total_runtime | 721.557 | 18.0733 |

## Per-Delivery Comparison

| delivery_id | present_in_solver | present_in_heuristic | solver_feasible | heuristic_feasible | heuristic_selected | comparison_status | solver_vehicle | heuristic_vehicle | solver_length_km | heuristic_length_km | length_diff_km | solver_risk | heuristic_risk | risk_diff | solver_variable_cost_eur | heuristic_variable_cost_eur | solver_fixed_cost_eur | heuristic_fixed_cost_eur | solver_total_cost_eur | heuristic_total_cost_eur | total_cost_diff_eur | solver_edge_count | heuristic_edge_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| delivery_1 | True | True | True | True | True | both_feasible | Mercedes_eActros_600 | MAN_eTGX | 3.1849 | 3.1712 | -0.0137 | 13.4249 | 12.7252 | -0.6997 | 3.4078 | 2.8097 | 220.0 | 180.0 | 223.4078 | 182.8097 | -40.5981 | 138 | 204 |
| delivery_2 | True | True | True | True | True | both_feasible | Mercedes_eActros_600 | MAN_eTGX | 7.6754 | 11.9249 | 4.2495 | 20.5433 | 19.2878 | -1.2555 | 8.2127 | 10.5654 | 220.0 | 180.0 | 228.2127 | 190.5654 | -37.6473 | 68 | 659 |
| delivery_3 | True | True | True | True | True | both_feasible | Volvo_FH_Electric | MAN_eTGX | 7.1487 | 8.6853 | 1.5366 | 20.6652 | 15.934 | -4.7312 | 7.1666 | 7.6951 | 200.0 | 180.0 | 207.1666 | 187.6951 | -19.4715 | 161 | 471 |

## Comparison Status Counts

| comparison_status | count |
| --- | --- |
| both_feasible | 3 |

## Notes

- Risk and cost are compared separately because these are the practical project indicators.
- Per-delivery differences are only computed when both methods produced feasible routes.
- Edge counts can differ because the solver output uses a contracted graph while the heuristic keeps original arc IDs.
- Vehicle labels are treated as vehicle model/type labels in this comparison, not necessarily unique physical trucks.
- Fixed costs are compared at delivery/trip level to match the current solver output snapshot.
- Route plausibility should still be checked with the map outputs.
- Heuristic risk components: population=0.4, accident=0.4, nature=0.2