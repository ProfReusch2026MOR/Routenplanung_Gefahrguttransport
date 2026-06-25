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
  data/
    solver_output/
      w1=0.65/
      w1=0.999/
    heuristic_output/
      w1=0.65/
      w1=0.999/
  output/
```

The script matches solver and heuristic outputs by scenario folder name. It then
generates per-scenario comparison reports and a top-level comparison index.

## Run

```powershell
py -3.10 experiments\compare_solver_heuristic.py
```

The default output is written to:

```text
experiments/output/
```

Risk, cost, route length, feasibility, and runtime are reported separately.
The internal solver objective value is intentionally not compared directly.
