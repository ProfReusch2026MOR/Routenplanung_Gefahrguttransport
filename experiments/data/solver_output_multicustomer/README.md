# Multi-Customer Solver Output Placeholder

Place solver JSON outputs here using the same scenario folder names as the
heuristic snapshots.

Expected structure:

```text
experiments/data/solver_output_multicustomer/
  small_risk_0.5_cost_0.3_time_0.2/
    solver_result.json
  small_risk_0.3_cost_0.5_time_0.2/
    solver_result.json
  medium_risk_0.5_cost_0.3_time_0.2/
    solver_result.json
  medium_risk_0.3_cost_0.5_time_0.2/
    solver_result.json
  large_10_vehicle_extra_volvo_single_trip/
    solver_result.json
```

The comparison script expects the same top-level JSON structure used by the
heuristic output: `status`, `routes`, `metadata`, `objective`, `metrics`, and
`runtime_seconds`.
