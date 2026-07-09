# Solver-Heuristic Comparison

This folder contains the comparison script, the small input snapshots used for
the current Berlin comparison, and generated comparison outputs.

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
multi-customer JSON outputs. It can already summarize heuristic snapshots. When
matching solver JSON files are added, the same script also computes
solver-minus-heuristic gaps for risk, cost, time, and runtime.

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

Matching solver outputs should be placed under:

```text
experiments/data/solver_output_multicustomer/<same-scenario-name>/solver_result.json
```

Until a solver file is available for a scenario, the report keeps the row with
`comparison_status = solver_missing`. This is intentional: it shows which
heuristic result is ready and what exact solver result is still needed.
