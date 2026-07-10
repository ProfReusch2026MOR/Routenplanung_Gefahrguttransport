# Multi-Customer Consistency Diagnostic

## Instance: Medium

## Findings

- Exported objectives recompute exactly: `True`.
- All checked heuristic vehicle resource constraints pass: `True`.
- Solver JSON includes aggregated runtime, but no per-vehicle schedule details or battery states; its resource checks cannot be replayed from the export.
- A heuristic value below a solver result labelled optimal is a consistency investigation, not evidence of heuristic superiority.

## Result Components

| scenario | method | objective_exported | objective_recomputed | objective_delta | total_risk | total_activation_cost | total_road_operating_cost | total_station_charging_cost | total_cost | total_time_minutes | active_vehicles | total_charging_events |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| medium_risk_0.3_cost_0.5_time_0.2 | heuristic | 0.28304494241249106 | 0.28304494241249106 | 0.0 | 4.84 | 5200.0 | 1093.9609 | 1212.49162 | 7506.45252 | 2933.4750999999997 | 5 | 4.0 |
| medium_risk_0.3_cost_0.5_time_0.2 | solver | 0.30621630698589924 | 0.3062163069858992 | 5.551115123125783e-17 | 5.189399999999999 | 6400.0 | 1278.0561399999997 | 304.25238 | 7982.3085200000005 | 3287.022 | 6 | 1.0 |
| medium_risk_0.5_cost_0.3_time_0.2 | heuristic | 0.2582815015082365 | 0.2582815015082365 | 0.0 | 4.84 | 5200.0 | 1093.9609 | 1212.49162 | 7506.45252 | 2933.4750999999997 | 5 | 4.0 |
| medium_risk_0.5_cost_0.3_time_0.2 | solver | 0.2602829028370663 | 0.26028290283706623 | 5.551115123125783e-17 | 4.7665 | 5600.0 | 1252.81685 | 301.38336 | 7154.200209999998 | 3195.7022999999995 | 5 | 1.0 |

## Required Solver Diagnostics

- a matching CBC final-termination record with bound and gap
- active vehicle IDs and activation-cost contribution per vehicle
- route-level distance, travel, service, charging, and break time
- charging side trips with station IDs and costs
- battery/range state and payload state along every route