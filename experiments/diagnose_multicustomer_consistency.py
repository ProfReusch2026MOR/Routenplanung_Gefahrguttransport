"""Create a reproducible consistency audit for paired solver/heuristic JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

try:  # pragma: no cover - package execution
    from .compare_multicustomer_results import (
        canonical_scenario_name,
        find_result_file,
        scenario_directories,
    )
except ImportError:  # pragma: no cover - direct script execution
    from compare_multicustomer_results import (
        canonical_scenario_name,
        find_result_file,
        scenario_directories,
    )


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_HEURISTIC_DIR = (
    SCRIPT_DIR / "data" / "heuristic_output_multicustomer"
)
DEFAULT_SOLVER_DIR = SCRIPT_DIR / "data" / "solver_output_multicustomer"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output" / "multicustomer_consistency"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def active_routes(payload: Mapping[str, Any]) -> dict[str, list[Any]]:
    routes = payload.get("routes", {})
    if not isinstance(routes, dict):
        return {}
    return {
        str(vehicle): route
        for vehicle, route in routes.items()
        if isinstance(route, list) and route
    }


def objective_recomputation(payload: Mapping[str, Any]) -> float:
    objective = payload.get("objective", {})
    metrics = payload.get("metrics", {})
    weights = objective.get("weights", {})
    scales = objective.get("scales", {})
    risk_scale = number(scales.get("risk"), 1.0)
    cost_scale = number(scales.get("cost"), 1.0)
    time_scale = number(scales.get("time"), 1.0)
    risk_term = 0.0
    if scales.get("risk_active", True):
        risk_term = number(weights.get("risk")) * number(
            metrics.get("total_risk")
        ) / risk_scale
    return (
        risk_term
        + number(weights.get("cost")) * number(metrics.get("total_cost"))
        / cost_scale
        + number(weights.get("time"))
        * number(metrics.get("total_time_minutes"))
        / time_scale
    )


def result_row(
    scenario: str,
    method: str,
    source_file: Path,
    payload: Mapping[str, Any],
) -> dict[str, object]:
    objective = payload.get("objective", {})
    metrics = payload.get("metrics", {})
    metadata = payload.get("metadata", {})
    weights = objective.get("weights", {})
    scales = objective.get("scales", {})
    recomputed = objective_recomputation(payload)
    exported = number(objective.get("value"))
    served = metadata.get("served_customers", [])
    return {
        "scenario": scenario,
        "method": method,
        "source_file": str(source_file),
        "status": payload.get("status", ""),
        "risk_weight": number(weights.get("risk")),
        "cost_weight": number(weights.get("cost")),
        "time_weight": number(weights.get("time")),
        "risk_scale": number(scales.get("risk")),
        "cost_scale": number(scales.get("cost")),
        "time_scale": number(scales.get("time")),
        "objective_exported": exported,
        "objective_recomputed": recomputed,
        "objective_delta": exported - recomputed,
        "served_customers": len(served) if isinstance(served, list) else 0,
        "total_risk": number(metrics.get("total_risk")),
        "total_activation_cost": number(
            metrics.get("total_activation_cost")
        ),
        "total_road_operating_cost": number(
            metrics.get("total_road_operating_cost")
        ),
        "total_station_charging_cost": number(
            metrics.get("total_station_charging_cost")
        ),
        "total_cost": number(metrics.get("total_cost")),
        "total_distance_km": number(metrics.get("total_distance_km")),
        "total_travel_minutes": number(
            metrics.get("total_travel_minutes")
        ),
        "total_service_minutes": number(
            metrics.get("total_service_minutes")
        ),
        "total_charging_minutes": number(
            metrics.get("total_charging_minutes")
        ),
        "total_break_minutes": number(
            metrics.get("total_break_minutes")
        ),
        "total_time_minutes": number(metrics.get("total_time_minutes")),
        "total_charging_events": number(
            metrics.get("total_charging_events")
        ),
        "active_vehicles": len(active_routes(payload)),
        "has_schedule_details": bool(payload.get("schedule_details")),
    }


def heuristic_vehicle_rows(
    scenario: str,
    payload: Mapping[str, Any],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    details = payload.get("schedule_details", {})
    if not isinstance(details, dict):
        return rows
    for vehicle_id, detail in details.items():
        if not isinstance(detail, dict) or not detail.get("trips"):
            continue
        trips = detail["trips"]
        technical_routes = [
            " -> ".join(str(stop) for stop in trip.get("stop_sequence", []))
            for trip in trips
        ]
        travel = number(detail.get("total_travel_minutes"))
        operating = number(detail.get("operating_minutes"))
        final_battery = number(detail.get("final_battery_kwh"))
        max_continuous_drive = 0.0
        for trip in trips:
            continuous_drive = 0.0
            visits = trip.get("visits", [])
            for leg_index, leg in enumerate(trip.get("legs", [])):
                continuous_drive += number(leg.get("travel_minutes"))
                max_continuous_drive = max(
                    max_continuous_drive,
                    continuous_drive,
                )
                if leg_index + 1 >= len(visits):
                    continue
                next_visit = visits[leg_index + 1]
                qualifying_pause = (
                    number(next_visit.get("charging_minutes"))
                    + number(next_visit.get("break_minutes"))
                )
                if qualifying_pause >= 45.0 - 1e-9:
                    continuous_drive = 0.0
        rows.append(
            {
                "scenario": scenario,
                "method": "heuristic",
                "vehicle": detail.get("solver_name", vehicle_id),
                "trip_count": len(trips),
                "technical_route": " | ".join(technical_routes),
                "distance_km": number(detail.get("total_distance_km")),
                "travel_minutes": travel,
                "max_continuous_drive_minutes": max_continuous_drive,
                "operating_minutes": operating,
                "charging_minutes": number(
                    detail.get("total_charging_minutes")
                ),
                "break_minutes": number(detail.get("total_break_minutes")),
                "final_battery_kwh": final_battery,
                "single_trip_check": len(trips) <= 1,
                "daily_driving_check": travel <= 540.0 + 1e-9,
                "continuous_driving_check": (
                    max_continuous_drive <= 270.0 + 1e-9
                ),
                "shift_check": operating <= 780.0 + 1e-9,
                "battery_check": final_battery >= -1e-9,
            }
        )
    return rows


def solver_vehicle_rows(
    scenario: str,
    payload: Mapping[str, Any],
) -> list[dict[str, object]]:
    return [
        {
            "scenario": scenario,
            "method": "solver",
            "vehicle": vehicle,
            "route": " -> ".join(str(stop) for stop in route),
            "schedule_details_available": False,
        }
        for vehicle, route in active_routes(payload).items()
    ]


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame.loc[:, columns].to_dict("records"):
        lines.append(
            "| "
            + " | ".join(str(row.get(column, "")) for column in columns)
            + " |"
        )
    return "\n".join(lines)


def diagnose(
    heuristic_dir: Path,
    solver_dir: Path,
    output_dir: Path,
    instance: str,
) -> None:
    heuristic = scenario_directories(heuristic_dir)
    solver = scenario_directories(solver_dir)
    scenarios = sorted(
        name
        for name in set(heuristic) & set(solver)
        if name.startswith(f"{instance}_")
    )
    if not scenarios:
        raise FileNotFoundError(f"No paired {instance} scenarios were found.")

    result_rows: list[dict[str, object]] = []
    vehicle_rows: list[dict[str, object]] = []
    for scenario in scenarios:
        heuristic_path = find_result_file(
            heuristic[scenario],
            "heuristic_result.json",
        )
        solver_path = find_result_file(solver[scenario], "solver_result.json")
        if heuristic_path is None or solver_path is None:
            continue
        heuristic_payload = read_json(heuristic_path)
        solver_payload = read_json(solver_path)
        result_rows.append(
            result_row(scenario, "heuristic", heuristic_path, heuristic_payload)
        )
        result_rows.append(
            result_row(scenario, "solver", solver_path, solver_payload)
        )
        vehicle_rows.extend(heuristic_vehicle_rows(scenario, heuristic_payload))
        vehicle_rows.extend(solver_vehicle_rows(scenario, solver_payload))

    result_frame = pd.DataFrame(result_rows)
    vehicle_frame = pd.DataFrame(vehicle_rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_frame.to_csv(output_dir / "result_component_audit.csv", index=False)
    vehicle_frame.to_csv(output_dir / "vehicle_constraint_audit.csv", index=False)

    objective_ok = bool(
        (result_frame["objective_delta"].abs() <= 1e-8).all()
    )
    heuristic_rows = vehicle_frame[vehicle_frame["method"] == "heuristic"]
    resource_checks_ok = bool(
        heuristic_rows[
            [
                "single_trip_check",
                "daily_driving_check",
                "continuous_driving_check",
                "shift_check",
                "battery_check",
            ]
        ]
        .eq(True)
        .all()
        .all()
    )
    compact_columns = [
        "scenario",
        "method",
        "objective_exported",
        "objective_recomputed",
        "objective_delta",
        "total_risk",
        "total_activation_cost",
        "total_road_operating_cost",
        "total_station_charging_cost",
        "total_cost",
        "total_time_minutes",
        "active_vehicles",
        "total_charging_events",
    ]
    report = [
        "# Multi-Customer Consistency Diagnostic",
        "",
        f"## Instance: {instance.title()}",
        "",
        "## Findings",
        "",
        f"- Exported objectives recompute exactly: `{objective_ok}`.",
        (
            "- All checked heuristic vehicle resource constraints pass: "
            f"`{resource_checks_ok}`."
        ),
        (
            "- Solver JSON includes aggregated runtime, but no per-vehicle "
            "schedule details or battery states; its resource checks cannot "
            "be replayed from the export."
        ),
        (
            "- A heuristic value below a solver result labelled optimal is a "
            "consistency investigation, not evidence of heuristic superiority."
        ),
        "",
        "## Result Components",
        "",
        markdown_table(result_frame, compact_columns),
        "",
        "## Required Solver Diagnostics",
        "",
        "- a matching CBC final-termination record with bound and gap",
        "- active vehicle IDs and activation-cost contribution per vehicle",
        "- route-level distance, travel, service, charging, and break time",
        "- charging side trips with station IDs and costs",
        "- battery/range state and payload state along every route",
    ]
    (output_dir / "consistency_report.md").write_text(
        "\n".join(report),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit paired multi-customer solver/heuristic outputs."
    )
    parser.add_argument(
        "--heuristic-dir", type=Path, default=DEFAULT_HEURISTIC_DIR
    )
    parser.add_argument("--solver-dir", type=Path, default=DEFAULT_SOLVER_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--instance",
        choices=["small", "medium", "large"],
        default="medium",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    diagnose(
        args.heuristic_dir,
        args.solver_dir,
        args.output_dir,
        args.instance,
    )
    print(f"Wrote consistency diagnostic to {args.output_dir}")


if __name__ == "__main__":
    main()
