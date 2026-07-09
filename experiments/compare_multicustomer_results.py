from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Optional

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_HEURISTIC_DIR = (
    SCRIPT_DIR / "data" / "heuristic_output_multicustomer"
)
DEFAULT_SOLVER_DIR = SCRIPT_DIR / "data" / "solver_output_multicustomer"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output" / "multicustomer_comparison"
RESULT_FILENAMES = ("result.json", "heuristic_result.json", "solver_result.json")
WEIGHT_SCENARIO_PATTERN = re.compile(
    r"^(?P<size>small|medium|large)_risk_?(?P<risk>[0-9.]+)"
    r"_cost_?(?P<cost>[0-9.]+)_time_?(?P<time>[0-9.]+)$",
    re.IGNORECASE,
)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(SCRIPT_DIR.parent.resolve()))
    except ValueError:
        return str(path)


def scenario_directories(root: Path) -> dict[str, Path]:
    if not root.exists():
        return {}
    scenarios: dict[str, Path] = {}
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        key = canonical_scenario_name(path.name)
        if key in scenarios:
            raise ValueError(
                f"Duplicate scenario after name normalization: {path.name} "
                f"and {scenarios[key].name} both map to {key}."
            )
        scenarios[key] = path
    return scenarios


def canonical_scenario_name(name: str) -> str:
    normalized = name.strip().lower().replace("-", "_")
    normalized = normalized.replace("_output_", "_")
    match = WEIGHT_SCENARIO_PATTERN.fullmatch(normalized)
    if not match:
        return normalized
    return (
        f"{match.group('size')}_risk_{match.group('risk')}"
        f"_cost_{match.group('cost')}_time_{match.group('time')}"
    )


def find_result_file(directory: Path, preferred_name: str) -> Optional[Path]:
    preferred = directory / preferred_name
    if preferred.exists():
        return preferred
    for filename in RESULT_FILENAMES:
        candidate = directory / filename
        if candidate.exists():
            return candidate
    json_files = sorted(directory.glob("*.json"))
    if len(json_files) == 1:
        return json_files[0]
    return None


def as_list(value: object) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def number(value: object, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def maybe_number(value: object) -> Optional[float]:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def rounded(value: Optional[float], digits: int = 4) -> object:
    if value is None:
        return ""
    return round(float(value), digits)


def difference(candidate: Optional[float], reference: Optional[float]) -> object:
    if candidate is None or reference is None:
        return ""
    return rounded(candidate - reference)


def percent_difference(
    candidate: Optional[float],
    reference: Optional[float],
) -> object:
    if candidate is None or reference in (None, 0):
        return ""
    return rounded((candidate - reference) / reference * 100, 3)


def active_vehicle_count(routes: Mapping[str, object]) -> int:
    return sum(1 for route in routes.values() if as_list(route))


def route_customer_count(route: object) -> int:
    return sum(1 for stop in as_list(route) if str(stop) != "DEPOT")


def extract_result(
    scenario: str,
    method: str,
    path: Path,
) -> dict[str, Any]:
    payload = read_json(path)
    metadata = payload.get("metadata", {})
    metrics = payload.get("metrics", {})
    objective = payload.get("objective", {})
    weights = objective.get("weights", {})
    runtimes = payload.get("runtime_seconds", {})
    routes = payload.get("routes", {})
    served_customers = as_list(metadata.get("served_customers"))
    unserved_customers = as_list(metadata.get("unserved_customers"))
    excluded_customers = as_list(metadata.get("excluded_customers"))
    route_values = list(routes.values()) if isinstance(routes, dict) else []
    return {
        "scenario": scenario,
        "method": method,
        "source_file": display_path(path),
        "schema_version": payload.get("schema_version", ""),
        "dataset_name": metadata.get("dataset_name", scenario),
        "status": payload.get("status", ""),
        "search_status": payload.get("search_status", ""),
        "risk_weight": maybe_number(weights.get("risk")),
        "cost_weight": maybe_number(weights.get("cost")),
        "time_weight": maybe_number(weights.get("time")),
        "objective_value": maybe_number(objective.get("value")),
        "served_customers": len(served_customers),
        "unserved_customers": len(unserved_customers),
        "excluded_customers": len(excluded_customers),
        "total_risk": maybe_number(
            metrics["total_risk_solver_compatible"]
            if "total_risk_solver_compatible" in metrics
            else metrics.get("total_risk")
        ),
        "total_cost": maybe_number(metrics.get("total_cost")),
        "total_activation_cost": maybe_number(
            metrics.get("total_activation_cost")
        ),
        "total_road_operating_cost": maybe_number(
            metrics.get("total_road_operating_cost")
        ),
        "total_station_charging_cost": maybe_number(
            metrics.get("total_station_charging_cost")
        ),
        "total_end_of_day_recharge_cost": maybe_number(
            metrics.get("total_end_of_day_recharge_cost")
        ),
        "total_distance_km": maybe_number(metrics.get("total_distance_km")),
        "total_time_minutes": maybe_number(
            metrics.get("total_time_minutes")
        ),
        "makespan_minute": maybe_number(metrics.get("makespan_minute")),
        "runtime_construction_seconds": maybe_number(
            runtimes.get("construction")
        ),
        "runtime_repair_seconds": maybe_number(runtimes.get("repair")),
        "runtime_vnd_seconds": maybe_number(runtimes.get("vnd")),
        "runtime_vns_seconds": maybe_number(runtimes.get("vns")),
        "runtime_total_algorithm_seconds": maybe_number(
            runtimes.get("total_algorithm")
        ),
        "active_vehicles": (
            active_vehicle_count(routes)
            if isinstance(routes, dict)
            else len(route_values)
        ),
        "route_count": len(route_values),
        "single_trip_per_vehicle": metadata.get("single_trip_per_vehicle", ""),
        "route_structure_compatible": metadata.get(
            "route_structure_compatible",
            "",
        ),
        "routes": routes if isinstance(routes, dict) else {},
    }


def missing_result(scenario: str, method: str) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "method": method,
        "source_file": "",
        "schema_version": "",
        "dataset_name": scenario,
        "status": "missing",
        "search_status": "missing",
        "risk_weight": None,
        "cost_weight": None,
        "time_weight": None,
        "objective_value": None,
        "served_customers": None,
        "unserved_customers": None,
        "excluded_customers": None,
        "total_risk": None,
        "total_cost": None,
        "total_activation_cost": None,
        "total_road_operating_cost": None,
        "total_station_charging_cost": None,
        "total_end_of_day_recharge_cost": None,
        "total_distance_km": None,
        "total_time_minutes": None,
        "makespan_minute": None,
        "runtime_construction_seconds": None,
        "runtime_repair_seconds": None,
        "runtime_vnd_seconds": None,
        "runtime_vns_seconds": None,
        "runtime_total_algorithm_seconds": None,
        "active_vehicles": None,
        "route_count": None,
        "single_trip_per_vehicle": "",
        "route_structure_compatible": "",
        "routes": {},
    }


def comparison_status(
    heuristic: Mapping[str, Any],
    solver: Mapping[str, Any],
) -> str:
    if solver["status"] == "missing":
        return "solver_missing"
    if heuristic["status"] == "missing":
        return "heuristic_missing"
    if solver["status"] != "feasible" and heuristic["status"] != "feasible":
        return "both_infeasible"
    if solver["status"] != "feasible":
        return "solver_infeasible"
    if heuristic["status"] != "feasible":
        return "heuristic_infeasible"
    if solver.get("served_customers") != heuristic.get("served_customers"):
        return "different_customer_set"
    return "both_feasible"


def build_summary_row(
    scenario: str,
    heuristic: Mapping[str, Any],
    solver: Mapping[str, Any],
) -> dict[str, object]:
    status = comparison_status(heuristic, solver)
    comparable = status == "both_feasible"
    return {
        "scenario": scenario,
        "comparison_status": status,
        "dataset_name": heuristic.get("dataset_name")
        or solver.get("dataset_name"),
        "risk_weight": rounded(
            heuristic.get("risk_weight") or solver.get("risk_weight")
        ),
        "cost_weight": rounded(
            heuristic.get("cost_weight") or solver.get("cost_weight")
        ),
        "time_weight": rounded(
            heuristic.get("time_weight") or solver.get("time_weight")
        ),
        "solver_status": solver.get("status", "missing"),
        "heuristic_status": heuristic.get("status", "missing"),
        "solver_served_customers": solver.get("served_customers") or "",
        "heuristic_served_customers": heuristic.get("served_customers") or "",
        "solver_total_risk": rounded(solver.get("total_risk")),
        "heuristic_total_risk": rounded(heuristic.get("total_risk")),
        "risk_diff_heuristic_minus_solver": difference(
            heuristic.get("total_risk"),
            solver.get("total_risk"),
        )
        if comparable
        else "",
        "risk_diff_pct_vs_solver": percent_difference(
            heuristic.get("total_risk"),
            solver.get("total_risk"),
        )
        if comparable
        else "",
        "solver_total_cost": rounded(solver.get("total_cost")),
        "heuristic_total_cost": rounded(heuristic.get("total_cost")),
        "cost_diff_heuristic_minus_solver": difference(
            heuristic.get("total_cost"),
            solver.get("total_cost"),
        )
        if comparable
        else "",
        "cost_diff_pct_vs_solver": percent_difference(
            heuristic.get("total_cost"),
            solver.get("total_cost"),
        )
        if comparable
        else "",
        "solver_total_time_minutes": rounded(
            solver.get("total_time_minutes")
        ),
        "heuristic_total_time_minutes": rounded(
            heuristic.get("total_time_minutes")
        ),
        "solver_runtime_total_algorithm_seconds": rounded(
            solver.get("runtime_total_algorithm_seconds")
        ),
        "heuristic_runtime_total_algorithm_seconds": rounded(
            heuristic.get("runtime_total_algorithm_seconds")
        ),
        "solver_active_vehicles": solver.get("active_vehicles") or "",
        "heuristic_active_vehicles": heuristic.get("active_vehicles") or "",
        "heuristic_single_trip_per_vehicle": heuristic.get(
            "single_trip_per_vehicle",
        ),
        "heuristic_route_structure_compatible": heuristic.get(
            "route_structure_compatible",
        ),
    }


def build_method_rows(results: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    rows = []
    scalar_keys = [
        "scenario",
        "method",
        "source_file",
        "dataset_name",
        "status",
        "search_status",
        "risk_weight",
        "cost_weight",
        "time_weight",
        "objective_value",
        "served_customers",
        "unserved_customers",
        "excluded_customers",
        "total_risk",
        "total_cost",
        "total_activation_cost",
        "total_road_operating_cost",
        "total_station_charging_cost",
        "total_end_of_day_recharge_cost",
        "total_distance_km",
        "total_time_minutes",
        "makespan_minute",
        "runtime_construction_seconds",
        "runtime_repair_seconds",
        "runtime_vnd_seconds",
        "runtime_vns_seconds",
        "runtime_total_algorithm_seconds",
        "active_vehicles",
        "route_count",
        "single_trip_per_vehicle",
        "route_structure_compatible",
    ]
    for result in results:
        rows.append(
            {
                key: rounded(result.get(key))
                if isinstance(result.get(key), float)
                else result.get(key, "")
                for key in scalar_keys
            }
        )
    return pd.DataFrame(rows)


def build_route_rows(results: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    rows = []
    for result in results:
        routes = result.get("routes", {})
        if not isinstance(routes, dict):
            continue
        for vehicle_name, route in sorted(routes.items()):
            stops = [str(stop) for stop in as_list(route)]
            rows.append(
                {
                    "scenario": result["scenario"],
                    "method": result["method"],
                    "vehicle_name": vehicle_name,
                    "route": " -> ".join(stops),
                    "stop_count": len(stops),
                    "customer_count": route_customer_count(stops),
                }
            )
    return pd.DataFrame(rows)


def markdown_table(rows: Iterable[Mapping[str, object]], columns: list[str]) -> str:
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(str(row.get(column, "")) for column in columns)
            + " |"
        )
    return "\n".join(lines)


def write_report(
    output_dir: Path,
    summary: pd.DataFrame,
    method_summary: pd.DataFrame,
    route_rows: pd.DataFrame,
    solver_dir: Path,
) -> None:
    visible_summary_columns = [
        "scenario",
        "comparison_status",
        "dataset_name",
        "risk_weight",
        "cost_weight",
        "time_weight",
        "solver_status",
        "heuristic_status",
        "solver_served_customers",
        "heuristic_served_customers",
        "solver_total_risk",
        "heuristic_total_risk",
        "solver_total_cost",
        "heuristic_total_cost",
        "solver_runtime_total_algorithm_seconds",
        "heuristic_runtime_total_algorithm_seconds",
    ]
    lines = [
        "# Multi-Customer Solver-Heuristic Comparison",
        "",
        "## Scope",
        "",
        "This report compares solver and heuristic JSON outputs for the "
        "multi-customer single-depot instances. If a matching solver JSON is "
        "not available yet, the scenario is kept as a heuristic-only row with "
        "`comparison_status = solver_missing`.",
        "",
        "Expected solver location:",
        "",
        f"`{display_path(solver_dir)}/<scenario>/solver_result.json`",
        "",
        "The solver JSON should use the same top-level structure as the "
        "heuristic result JSON: `status`, `routes`, `metadata`, `objective`, "
        "`metrics`, and `runtime_seconds`.",
        "",
        "## Scenario Summary",
        "",
        markdown_table(
            summary.to_dict("records"),
            visible_summary_columns,
        ),
        "",
        "## Method Summary",
        "",
        markdown_table(
            method_summary.to_dict("records"),
            list(method_summary.columns),
        ),
        "",
        "## Route Overview",
        "",
        markdown_table(
            route_rows.to_dict("records"),
            list(route_rows.columns),
        ),
        "",
        "## Notes",
        "",
        "- Direct quality gaps are only meaningful for rows with "
        "`comparison_status = both_feasible`.",
        "- The current heuristic snapshots are single-trip compatible results.",
        "- Risk, cost, time, and runtime are kept as separate columns because "
        "the project report should discuss these trade-offs separately.",
    ]
    (output_dir / "comparison_report.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def compare(
    heuristic_dir: Path,
    solver_dir: Path,
    output_dir: Path,
    *,
    instance: Optional[str] = None,
) -> None:
    heuristic_scenarios = scenario_directories(heuristic_dir)
    solver_scenarios = scenario_directories(solver_dir)
    scenario_names = sorted(set(heuristic_scenarios) | set(solver_scenarios))
    if instance is not None:
        scenario_names = [
            name for name in scenario_names
            if name.startswith(instance) or name.startswith(f"{instance}_")
        ]
    if not scenario_names:
        raise FileNotFoundError(
            "No multi-customer scenarios found in heuristic or solver input "
            "directories."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    all_results = []
    summary_rows = []
    for scenario in scenario_names:
        heuristic_result = missing_result(scenario, "heuristic")
        solver_result = missing_result(scenario, "solver")

        heuristic_path = None
        if scenario in heuristic_scenarios:
            heuristic_path = find_result_file(
                heuristic_scenarios[scenario],
                "heuristic_result.json",
            )
        if heuristic_path is not None:
            heuristic_result = extract_result(
                scenario,
                "heuristic",
                heuristic_path,
            )

        solver_path = None
        if scenario in solver_scenarios:
            solver_path = find_result_file(
                solver_scenarios[scenario],
                "solver_result.json",
            )
        if solver_path is not None:
            solver_result = extract_result(scenario, "solver", solver_path)

        all_results.extend([heuristic_result, solver_result])
        summary_rows.append(
            build_summary_row(scenario, heuristic_result, solver_result)
        )

    summary = pd.DataFrame(summary_rows).fillna("")
    method_summary = build_method_rows(all_results).fillna("")
    route_rows = build_route_rows(all_results).fillna("")

    summary.to_csv(output_dir / "scenario_summary.csv", index=False)
    method_summary.to_csv(output_dir / "method_summary.csv", index=False)
    route_rows.to_csv(output_dir / "routes.csv", index=False)
    write_json(output_dir / "scenario_summary.json", summary.to_dict("records"))
    write_report(output_dir, summary, method_summary, route_rows, solver_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare multi-customer solver and heuristic JSON outputs."
        ),
    )
    parser.add_argument(
        "--heuristic-dir",
        type=Path,
        default=DEFAULT_HEURISTIC_DIR,
        help=f"Default: {DEFAULT_HEURISTIC_DIR}",
    )
    parser.add_argument(
        "--solver-dir",
        type=Path,
        default=DEFAULT_SOLVER_DIR,
        help=f"Default: {DEFAULT_SOLVER_DIR}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--instance",
        choices=["small", "medium", "large"],
        default=None,
        help="Only compare scenarios for this instance size (e.g. --instance small).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    compare(
        args.heuristic_dir,
        args.solver_dir,
        args.output_dir,
        instance=args.instance,
    )
    label = f" ({args.instance})" if args.instance else ""
    print(f"Wrote multi-customer comparison{label} to {args.output_dir}")


if __name__ == "__main__":
    main()
