# Solver vs Heuristic Comparison

## Scenario

- Scenario folder: w1=0.65
- Region: berlin
- Solver run id: 20260624_155347
- Solver network mode: contracted_graph
- Heuristic network mode: solver_cropped
- Risk weight: 0.65
- Cost weight: 0.35
- Energy price: 0.35 EUR/kWh
- Solver status: Optimal

## Main Comparison

| metric | unit | solver | heuristic | heuristic_minus_solver | difference_pct_vs_solver |
| --- | --- | --- | --- | --- | --- |
| feasible_deliveries | count | 3.0 | 3.0 | 0.0 | 0.0 |
| selected_total_length_km | km | 20.352 | 23.7813 | 3.4293 | 16.85 |
| total_risk | risk score | 54.568 | 47.947 | -6.621 | -12.133 |
| total_variable_cost | EUR | 18.0319 | 21.0702 | 3.0383 | 16.85 |
| total_fixed_cost | EUR | 540.0 | 540.0 | 0.0 | 0.0 |
| total_cost | EUR | 558.0319 | 561.0702 | 3.0383 | 0.544 |
| core_runtime | seconds | 245.426 | 14.1331 | -231.2929 | -94.241 |
| total_runtime | seconds | 545.456 | 25.9951 | -519.4609 | -95.234 |

## Runtime Comparison

| stage | solver_seconds | heuristic_seconds |
| --- | --- | --- |
| data_preparation | 168.775 | 2.9833 |
| network_preparation | 130.937 | 2.2658 |
| mapping |  | 3.242 |
| model_build | 34.318 |  |
| solver_runtime | 211.107 |  |
| candidate_generation |  | 0.9321 |
| vehicle_assignment |  | 0.0002 |
| result_processing_or_export | 0.319 | 7.988 |
| core_runtime | 245.426 | 14.1331 |
| total_runtime | 545.456 | 25.9951 |

## Per-Delivery Comparison

| delivery_id | present_in_solver | present_in_heuristic | solver_feasible | heuristic_feasible | heuristic_selected | comparison_status | solver_vehicle | heuristic_vehicle | solver_length_km | heuristic_length_km | length_diff_km | solver_risk | heuristic_risk | risk_diff | solver_variable_cost_eur | heuristic_variable_cost_eur | solver_fixed_cost_eur | heuristic_fixed_cost_eur | solver_total_cost_eur | heuristic_total_cost_eur | total_cost_diff_eur | solver_edge_count | heuristic_edge_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| delivery_1 | True | True | True | True | True | both_feasible | MAN_eTGX | MAN_eTGX | 3.5993 | 3.1712 | -0.4281 | 13.1572 | 12.7252 | -0.432 | 3.189 | 2.8097 | 180.0 | 180.0 | 183.189 | 182.8097 | -0.3793 | 151 | 204 |
| delivery_2 | True | True | True | True | True | both_feasible | MAN_eTGX | MAN_eTGX | 7.8294 | 11.9249 | 4.0955 | 22.4053 | 19.2878 | -3.1175 | 6.9369 | 10.5654 | 180.0 | 180.0 | 186.9369 | 190.5654 | 3.6285 | 118 | 659 |
| delivery_3 | True | True | True | True | True | both_feasible | MAN_eTGX | MAN_eTGX | 8.9233 | 8.6853 | -0.238 | 19.0054 | 15.934 | -3.0714 | 7.9061 | 7.6951 | 180.0 | 180.0 | 187.9061 | 187.6951 | -0.211 | 300 | 471 |

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