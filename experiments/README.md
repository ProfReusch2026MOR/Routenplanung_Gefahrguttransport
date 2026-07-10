# Solver-Heuristic Comparison

This folder contains the earlier Berlin comparison, the current
multi-customer Small/Medium solver-heuristic comparison, and generated reports.

## Requirements

- Python 3.10
- pandas

On the current local setup, use:

```powershell
py -3.10 experiments\compare_solver_heuristic.py
```

Avoid relying on plain `python` unless that interpreter has pandas installed.

## Structure

```text
experiments/
  compare_solver_heuristic.py
  compare_multicustomer_results.py
  data/
    solver_output/
      w1=0.65/
      w1=0.999/
    heuristic_output/
      w1=0.65/
      w1=0.999/
    solver_output_multicustomer/
    heuristic_output_multicustomer/
  output/
```

`compare_solver_heuristic.py` keeps the earlier Berlin CSV/summary comparison.
It matches solver and heuristic outputs by scenario folder name and generates
per-scenario comparison reports plus a top-level comparison index.

`compare_multicustomer_results.py` compares the newer Small, Medium, and Large
multi-customer JSON outputs. It pairs scenarios by instance and objective
weights, then computes heuristic-minus-solver gaps for risk and cost.
It also accepts the solver's compact folder spelling such as `time02` as the
same scenario as `time_0.2`.

## Run Berlin CSV Comparison

```powershell
py -3.10 experiments\compare_solver_heuristic.py
```

The default output is written to:

```text
experiments/output/
```

Risk, cost, route length, feasibility, and runtime are reported separately.
The internal solver objective value is intentionally not compared directly.

## Run Multi-Customer JSON Comparison

```powershell
py -3.10 experiments\compare_multicustomer_results.py
```

The default output is written to:

```text
experiments/output/multicustomer_comparison/
```

Current heuristic snapshots are stored in:

```text
experiments/data/heuristic_output_multicustomer/
```

Matching solver outputs should normally be placed under:

```text
experiments/data/solver_output_multicustomer/<same-scenario-name>/solver_result.json
```

The folder name may also follow the solver export convention, for example:

```text
medium_output_risk0.5_cost0.3_time02/
```

The comparison script normalizes both spellings before matching.

## Current Multi-Customer Benchmark

The current comparison uses the updated precomputed OD matrices and these four
single-trip scenarios:

| Instance | Risk | Cost | Time |
|---|---:|---:|---:|
| Small | 0.5 | 0.3 | 0.2 |
| Small | 0.3 | 0.5 | 0.2 |
| Medium | 0.5 | 0.3 | 0.2 |
| Medium | 0.3 | 0.5 | 0.2 |

For all four pairs, the current JSON files have matching customer sets,
objective weights, objective scales, and a single-trip route structure. The
generated artifacts are:

```text
experiments/output/multicustomer_comparison/
  scenario_summary.csv
  scenario_summary.json
  method_summary.csv
  routes.csv
  comparison_report.md
```

`Large` remains a heuristic-only extension row because no matching
single-trip solver JSON is available.

The Medium solver JSON files include aggregated runtime fields. The comparison
maps `runtime_seconds.total` to the shared total-runtime column, while the
heuristic uses `runtime_seconds.total_algorithm`.

Neither Medium JSON has a matching CBC final-termination record. Therefore,
their JSON field `search_status = optimal` is reported as
`reported_optimality_unverified` in the comparison output. This is more
conservative than claiming a proven optimum from the JSON field alone.

A separate 11-hour CBC progress log for the Medium risk-oriented setting is
stored under `experiments/data/solver_logs/`. Its elapsed time and objective do
not match the current solver JSON, so it is documented as a supplementary run
and is not attached to the JSON comparison. The Medium results are not used as
proof that the heuristic outperforms a proven optimal solver solution.

## Run the Consistency Diagnostic

```powershell
py -3.10 experiments\diagnose_multicustomer_consistency.py --instance medium
```

This creates a component audit and a vehicle-level heuristic constraint audit
under:

```text
experiments/output/multicustomer_consistency/
  result_component_audit.csv
  vehicle_constraint_audit.csv
  consistency_report.md
```

The diagnostic recomputes each exported objective and checks the heuristic's
single-trip, daily-driving, continuous-driving, shift, and final-battery
states. It cannot replay equivalent solver checks until the solver exports
per-vehicle schedule and battery information.
