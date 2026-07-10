from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Iterable, Mapping, Optional

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SOLVER_DIR = SCRIPT_DIR / "data" / "solver_output"
DEFAULT_HEURISTIC_DIR = SCRIPT_DIR / "data" / "heuristic_output"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
DELIVERY_ID_PATTERN = re.compile(r"^(?:delivery_)?(\d+)$", re.IGNORECASE)
TRUTHY = {"1", "true", "t", "yes", "y"}
FALSY = {"0", "false", "f", "no", "n"}


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def solver_run_ids(directory: Path, prefix: str, suffix: str) -> set[str]:
    run_ids = set()
    for path in directory.glob(f"{prefix}*{suffix}"):
        name = path.name
        if name.startswith(prefix) and name.endswith(suffix):
            run_id = name[len(prefix) : -len(suffix)]
            if run_id:
                run_ids.add(run_id)
    return run_ids


def has_complete_solver_run(directory: Path) -> bool:
    summary_ids = solver_run_ids(directory, "solver_summary_", ".json")
    selected_ids = solver_run_ids(directory, "solver_selected_paths_", ".csv")
    return bool(summary_ids & selected_ids)


def has_heuristic_output(directory: Path) -> bool:
    return (
        (directory / "heuristic_summary.json").exists()
        and (directory / "heuristic_selected_paths.csv").exists()
    )


def safe_scenario_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.=-]+", "_", name).strip("_") or "scenario"


def discover_solver_scenarios(solver_dir: Path) -> list[tuple[str, Path]]:
    if has_complete_solver_run(solver_dir):
        return [(safe_scenario_name(solver_dir.name), solver_dir)]

    scenarios = [
        (safe_scenario_name(path.name), path)
        for path in sorted(solver_dir.iterdir())
        if path.is_dir() and has_complete_solver_run(path)
    ]
    if not scenarios:
        raise FileNotFoundError(
            "No complete solver scenario found. Expected solver files directly in "
            f"{solver_dir} or in scenario subdirectories."
        )
    return scenarios


def heuristic_scenario_dir(heuristic_dir: Path, scenario_name: str) -> Path:
    if has_heuristic_output(heuristic_dir):
        return heuristic_dir

    candidate = heuristic_dir / scenario_name
    if has_heuristic_output(candidate):
        return candidate

    fallback = heuristic_dir / "normal"
    if scenario_name == "w1=0.65" and has_heuristic_output(fallback):
        return fallback

    raise FileNotFoundError(
        "No matching heuristic output found for scenario "
        f"{scenario_name!r}. Expected {candidate}."
    )


def scenario_output_dir(output_dir: Path, scenario_name: str, multiple: bool) -> Path:
    if multiple:
        return output_dir / f"solver_heuristic_comparison_{safe_scenario_name(scenario_name)}"
    return output_dir / "solver_heuristic_comparison"


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(SCRIPT_DIR.parent.resolve()))
    except ValueError:
        return str(path)


def newest_complete_solver_run(solver_dir: Path) -> tuple[str, Path, Path, Optional[Path]]:
    summary_ids = solver_run_ids(solver_dir, "solver_summary_", ".json")
    selected_ids = solver_run_ids(solver_dir, "solver_selected_paths_", ".csv")
    complete_ids = sorted(summary_ids & selected_ids)
    if not complete_ids:
        raise FileNotFoundError(
            "No complete solver run found. Expected matching "
            "solver_summary_<run_id>.json and solver_selected_paths_<run_id>.csv."
        )
    run_id = complete_ids[-1]
    summary_path = solver_dir / f"solver_summary_{run_id}.json"
    selected_path = solver_dir / f"solver_selected_paths_{run_id}.csv"
    edges_path = solver_dir / f"solver_edges_used_{run_id}.csv"
    return run_id, summary_path, selected_path, edges_path if edges_path.exists() else None


def canonical_delivery_id(value: object) -> str:
    if pd.isna(value):
        raise ValueError("Delivery id is missing.")
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    else:
        text = str(value).strip()
    match = DELIVERY_ID_PATTERN.fullmatch(text)
    if not match:
        raise ValueError(
            f"Unsupported delivery id {value!r}. Expected values like 1 or delivery_1."
        )
    return f"delivery_{int(match.group(1))}"


def add_delivery_key(
    table: pd.DataFrame,
    source_name: str,
    allow_duplicates: bool = False,
) -> pd.DataFrame:
    if "delivery_id" not in table.columns:
        raise ValueError(f"{source_name} output is missing a delivery_id column.")
    result = table.copy()
    result["delivery_key"] = result["delivery_id"].map(canonical_delivery_id)
    duplicates = result.loc[result["delivery_key"].duplicated(), "delivery_key"].tolist()
    if duplicates and not allow_duplicates:
        raise ValueError(
            f"{source_name} output contains duplicate delivery ids after normalization: "
            f"{sorted(set(duplicates))}"
        )
    return result


def keep_most_relevant_heuristic_row(table: pd.DataFrame) -> pd.DataFrame:
    if "delivery_key" not in table.columns:
        raise ValueError("Heuristic output must have delivery_key before row reduction.")
    reduced = table.copy()
    reduced["_selected_rank"] = reduced["selected_bool"].map(lambda value: 0 if value else 1)
    reduced["_feasible_rank"] = reduced["heuristic_feasible_bool"].map(
        lambda value: 0 if value else 1
    )
    reduced = reduced.sort_values(
        [
            "delivery_key",
            "_selected_rank",
            "_feasible_rank",
        ],
        kind="stable",
    )
    return reduced.drop_duplicates("delivery_key", keep="first").drop(
        columns=["_selected_rank", "_feasible_rank"],
    )


def parse_bool(value: object, column: str) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        raise ValueError(f"Missing boolean value in {column}.")
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(int(value))
    text = str(value).strip().lower()
    if text in TRUTHY:
        return True
    if text in FALSY:
        return False
    raise ValueError(f"Unsupported boolean value {value!r} in {column}.")


def bool_column(
    table: pd.DataFrame,
    column: str,
    default: bool,
    source_name: str,
) -> pd.Series:
    if column not in table.columns:
        return pd.Series([default] * len(table), index=table.index)
    return table[column].map(lambda value: parse_bool(value, f"{source_name}.{column}"))


def optional_number(value: object) -> Optional[float]:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def number(value: object, default: float = 0.0) -> float:
    parsed = optional_number(value)
    return default if parsed is None else parsed


def percent_difference(candidate: float, reference: float) -> Optional[float]:
    if reference == 0:
        return None
    return (candidate - reference) / reference * 100


def rounded(value: Optional[float], digits: int = 4) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


def compact_list(value: object) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}={item}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value)
    return str(value)


def load_solver_outputs(solver_dir: Path) -> tuple[str, dict, pd.DataFrame]:
    run_id, summary_path, selected_path, _edges_path = newest_complete_solver_run(
        solver_dir
    )
    selected = pd.read_csv(selected_path)
    selected = add_delivery_key(selected, "solver")
    selected["solver_feasible_bool"] = bool_column(
        selected,
        "feasible",
        default=True,
        source_name="solver",
    )
    return run_id, read_json(summary_path), selected


def load_heuristic_outputs(heuristic_dir: Path) -> tuple[dict, pd.DataFrame]:
    summary = read_json(heuristic_dir / "heuristic_summary.json")
    selected = pd.read_csv(heuristic_dir / "heuristic_selected_paths.csv")
    selected["selected_bool"] = bool_column(
        selected,
        "selected",
        default=True,
        source_name="heuristic",
    )
    selected = add_delivery_key(selected, "heuristic", allow_duplicates=True)
    selected["heuristic_feasible_bool"] = bool_column(
        selected,
        "feasible",
        default=True,
        source_name="heuristic",
    )
    selected = keep_most_relevant_heuristic_row(selected)
    selected["heuristic_total_cost"] = (
        selected.get("variable_cost", 0).map(number)
        + selected.get("activation_cost", 0).map(number)
    )
    return summary, selected


def comparable_difference(
    solver_value: Optional[float],
    heuristic_value: Optional[float],
    comparison_status: str,
) -> object:
    if (
        comparison_status == "both_feasible"
        and solver_value is not None
        and heuristic_value is not None
    ):
        return rounded(heuristic_value - solver_value)
    return ""


def comparable_cell(value: Optional[float]) -> object:
    return "" if value is None else rounded(value)


def integer_cell(value: Optional[float]) -> object:
    return "" if value is None else int(value)


def delivery_sort_value(delivery_key: str) -> int:
    return int(delivery_key.rsplit("_", 1)[1])


def comparison_status(
    present_in_solver: bool,
    present_in_heuristic: bool,
    solver_feasible: bool,
    heuristic_feasible: bool,
    heuristic_selected: bool,
) -> str:
    if present_in_solver and not present_in_heuristic:
        return "solver_only"
    if present_in_heuristic and not present_in_solver:
        return "heuristic_only"
    if not present_in_solver and not present_in_heuristic:
        return "missing_on_both_sides"
    if not solver_feasible and not heuristic_feasible:
        return "both_infeasible"
    if not solver_feasible:
        return "solver_infeasible"
    if not heuristic_feasible:
        return "heuristic_infeasible"
    if not heuristic_selected:
        return "heuristic_not_selected"
    return "both_feasible"


def compare_per_delivery(
    solver_selected: pd.DataFrame,
    heuristic_selected: pd.DataFrame,
) -> pd.DataFrame:
    merged = solver_selected.merge(
        heuristic_selected,
        on="delivery_key",
        suffixes=("_solver", "_heuristic"),
        how="outer",
    )
    rows = []
    merged["delivery_sort"] = merged["delivery_key"].map(delivery_sort_value)
    for _, row in merged.sort_values("delivery_sort").iterrows():
        present_in_solver = not pd.isna(row.get("delivery_id_solver"))
        present_in_heuristic = not pd.isna(row.get("delivery_id_heuristic"))
        solver_feasible = (
            bool(row.get("solver_feasible_bool"))
            if present_in_solver and not pd.isna(row.get("solver_feasible_bool"))
            else False
        )
        heuristic_feasible = (
            bool(row.get("heuristic_feasible_bool"))
            if present_in_heuristic and not pd.isna(row.get("heuristic_feasible_bool"))
            else False
        )
        heuristic_selected = (
            bool(row.get("selected_bool"))
            if present_in_heuristic and not pd.isna(row.get("selected_bool"))
            else False
        )
        status = comparison_status(
            present_in_solver,
            present_in_heuristic,
            solver_feasible,
            heuristic_feasible,
            heuristic_selected,
        )
        solver_length = optional_number(row.get("path_length_km_solver"))
        heuristic_length = optional_number(row.get("path_length_km_heuristic"))
        solver_risk = optional_number(row.get("path_risk_solver"))
        heuristic_risk = optional_number(row.get("path_risk_heuristic"))
        solver_cost = optional_number(row.get("total_cost"))
        heuristic_cost = optional_number(row.get("heuristic_total_cost"))
        rows.append(
            {
                "delivery_id": row["delivery_key"],
                "present_in_solver": present_in_solver,
                "present_in_heuristic": present_in_heuristic,
                "solver_feasible": solver_feasible if present_in_solver else "",
                "heuristic_feasible": heuristic_feasible if present_in_heuristic else "",
                "heuristic_selected": (
                    heuristic_selected if present_in_heuristic else ""
                ),
                "comparison_status": status,
                "solver_vehicle": row.get("vehicle_id_solver", ""),
                "heuristic_vehicle": row.get("vehicle_id_heuristic", ""),
                "solver_length_km": comparable_cell(solver_length),
                "heuristic_length_km": comparable_cell(heuristic_length),
                "length_diff_km": comparable_difference(
                    solver_length,
                    heuristic_length,
                    status,
                ),
                "solver_risk": comparable_cell(solver_risk),
                "heuristic_risk": comparable_cell(heuristic_risk),
                "risk_diff": comparable_difference(solver_risk, heuristic_risk, status),
                "solver_variable_cost_eur": comparable_cell(
                    optional_number(row.get("variable_cost_solver"))
                ),
                "heuristic_variable_cost_eur": comparable_cell(
                    optional_number(row.get("variable_cost_heuristic"))
                ),
                "solver_fixed_cost_eur": comparable_cell(
                    optional_number(row.get("fixed_cost"))
                ),
                "heuristic_fixed_cost_eur": comparable_cell(
                    optional_number(row.get("activation_cost"))
                ),
                "solver_total_cost_eur": comparable_cell(solver_cost),
                "heuristic_total_cost_eur": comparable_cell(heuristic_cost),
                "total_cost_diff_eur": comparable_difference(
                    solver_cost,
                    heuristic_cost,
                    status,
                ),
                "solver_edge_count": integer_cell(optional_number(row.get("num_edges"))),
                "heuristic_edge_count": integer_cell(
                    optional_number(row.get("edge_count"))
                ),
            }
        )
    return pd.DataFrame(rows)


def summary_rows(
    solver_summary: Mapping[str, object],
    solver_selected: pd.DataFrame,
    heuristic_summary: Mapping[str, object],
) -> pd.DataFrame:
    solver_results = solver_summary.get("results", {})
    solver_timing = solver_summary.get("timing_s", {})
    solver_feasible = solver_selected["solver_feasible_bool"]
    heuristic_length = number(heuristic_summary.get("selected_total_length_km"))
    metrics = [
        (
            "feasible_deliveries",
            int(solver_feasible.sum()),
            heuristic_summary.get("feasible_deliveries"),
            "count",
        ),
        (
            "selected_total_length_km",
            solver_selected.loc[solver_feasible, "path_length_km"].map(number).sum(),
            heuristic_length,
            "km",
        ),
        (
            "total_risk",
            solver_results.get("total_risk"),
            heuristic_summary.get("total_risk"),
            "risk score",
        ),
        (
            "total_variable_cost",
            solver_results.get("total_variable_cost_eur"),
            heuristic_summary.get("total_variable_cost"),
            "EUR",
        ),
        (
            "total_fixed_cost",
            solver_results.get("total_fixed_cost_eur"),
            heuristic_summary.get("total_fixed_cost"),
            "EUR",
        ),
        (
            "total_cost",
            solver_results.get("total_cost_eur"),
            heuristic_summary.get("total_cost"),
            "EUR",
        ),
        (
            "core_runtime",
            solver_timing.get("core_runtime"),
            heuristic_summary.get("runtime_seconds"),
            "seconds",
        ),
        (
            "total_runtime",
            solver_timing.get("total_runtime"),
            heuristic_summary.get("end_to_end_runtime_seconds"),
            "seconds",
        ),
    ]
    rows = []
    for metric, solver_value, heuristic_value, unit in metrics:
        solver_number = number(solver_value)
        heuristic_number = number(heuristic_value)
        rows.append(
            {
                "metric": metric,
                "unit": unit,
                "solver": rounded(solver_number),
                "heuristic": rounded(heuristic_number),
                "heuristic_minus_solver": rounded(heuristic_number - solver_number),
                "difference_pct_vs_solver": rounded(
                    percent_difference(heuristic_number, solver_number),
                    3,
                ),
            }
        )
    return pd.DataFrame(rows)


def runtime_rows(
    solver_summary: Mapping[str, object],
    heuristic_summary: Mapping[str, object],
) -> pd.DataFrame:
    solver_timing = solver_summary.get("timing_s", {})
    rows = [
        ("data_preparation", solver_timing.get("data_preparation"), heuristic_summary.get("data_preparation_seconds")),
        ("network_preparation", solver_timing.get("network_preparation"), heuristic_summary.get("network_preprocessing_seconds")),
        ("mapping", None, heuristic_summary.get("mapping_seconds")),
        ("model_build", solver_timing.get("model_build"), None),
        ("solver_runtime", solver_timing.get("solver_runtime"), None),
        ("candidate_generation", None, heuristic_summary.get("candidate_generation_seconds")),
        ("vehicle_assignment", None, heuristic_summary.get("vehicle_assignment_seconds")),
        ("result_processing_or_export", solver_timing.get("result_processing"), heuristic_summary.get("export_seconds")),
        ("core_runtime", solver_timing.get("core_runtime"), heuristic_summary.get("runtime_seconds")),
        ("total_runtime", solver_timing.get("total_runtime"), heuristic_summary.get("end_to_end_runtime_seconds")),
    ]
    return pd.DataFrame(
        [
            {
                "stage": stage,
                "solver_seconds": rounded(number(solver_value)) if solver_value is not None else "",
                "heuristic_seconds": rounded(number(heuristic_value)) if heuristic_value is not None else "",
            }
            for stage, solver_value, heuristic_value in rows
        ]
    )


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
    scenario_name: str,
    solver_run_id: str,
    solver_summary: Mapping[str, object],
    heuristic_summary: Mapping[str, object],
    summary: pd.DataFrame,
    per_delivery: pd.DataFrame,
    runtime: pd.DataFrame,
) -> None:
    solver_meta = solver_summary.get("meta", {})
    solver_weights = solver_summary.get("weights", {})
    heuristic_metadata = heuristic_summary.get("metadata", {})
    lines = [
        "# Solver vs Heuristic Comparison",
        "",
        "## Scenario",
        "",
        f"- Scenario folder: {scenario_name}",
        f"- Region: {heuristic_summary.get('region', 'unknown')}",
        f"- Solver run id: {solver_run_id}",
        f"- Solver network mode: {solver_meta.get('network_mode', 'unknown')}",
        f"- Heuristic network mode: {heuristic_summary.get('network_mode', 'unknown')}",
        f"- Risk weight: {heuristic_summary.get('risk_weight', solver_weights.get('w1_risk', 'unknown'))}",
        f"- Cost weight: {heuristic_summary.get('cost_weight', solver_weights.get('w2_cost', 'unknown'))}",
        f"- Energy price: {heuristic_summary.get('energy_price_eur_per_kwh', solver_meta.get('strompreis_eur_kwh', 'unknown'))} EUR/kWh",
        f"- Solver status: {solver_summary.get('solver_status', {}).get('status', 'unknown')}",
        "",
        "## Main Comparison",
        "",
        markdown_table(summary.to_dict("records"), list(summary.columns)),
        "",
        "## Runtime Comparison",
        "",
        markdown_table(runtime.to_dict("records"), list(runtime.columns)),
        "",
        "## Per-Delivery Comparison",
        "",
        markdown_table(per_delivery.to_dict("records"), list(per_delivery.columns)),
        "",
        "## Comparison Status Counts",
        "",
        markdown_table(
            per_delivery["comparison_status"]
            .value_counts()
            .rename_axis("comparison_status")
            .reset_index(name="count")
            .to_dict("records"),
            ["comparison_status", "count"],
        ),
        "",
        "## Notes",
        "",
        "- Risk and cost are compared separately because these are the practical project indicators.",
        "- Per-delivery differences are only computed when both methods produced feasible routes.",
        "- Edge counts can differ because the solver output uses a contracted graph while the heuristic keeps original arc IDs.",
        "- Vehicle labels are treated as vehicle model/type labels in this comparison, not necessarily unique physical trucks.",
        "- Fixed costs are compared at delivery/trip level to match the current solver output snapshot.",
        "- Route plausibility should still be checked with the map outputs.",
        f"- Heuristic risk components: {compact_list(heuristic_metadata.get('risk_component_weights', {}))}",
    ]
    (output_dir / "comparison_report.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare solver and heuristic outputs for the same scenario.",
    )
    parser.add_argument(
        "--solver-dir",
        type=Path,
        default=DEFAULT_SOLVER_DIR,
        help=(
            "Directory with solver output files, or a directory containing solver "
            f"scenario subdirectories (default: {DEFAULT_SOLVER_DIR})."
        ),
    )
    parser.add_argument(
        "--heuristic-dir",
        type=Path,
        default=DEFAULT_HEURISTIC_DIR,
        help=(
            "Directory with heuristic output files, or a directory containing heuristic "
            f"scenario subdirectories (default: {DEFAULT_HEURISTIC_DIR})."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for comparison outputs (default: {DEFAULT_OUTPUT_DIR}).",
    )
    return parser.parse_args()


def compare_scenario(
    scenario_name: str,
    solver_dir: Path,
    heuristic_dir: Path,
    output_dir: Path,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    solver_run_id, solver_summary, solver_selected = load_solver_outputs(solver_dir)
    heuristic_summary, heuristic_selected = load_heuristic_outputs(heuristic_dir)

    per_delivery = compare_per_delivery(solver_selected, heuristic_selected)
    summary = summary_rows(solver_summary, solver_selected, heuristic_summary)
    runtime = runtime_rows(solver_summary, heuristic_summary)

    per_delivery.to_csv(output_dir / "per_delivery_comparison.csv", index=False)
    summary.to_csv(output_dir / "summary_comparison.csv", index=False)
    runtime.to_csv(output_dir / "runtime_comparison.csv", index=False)
    write_report(
        output_dir,
        scenario_name,
        solver_run_id,
        solver_summary,
        heuristic_summary,
        summary,
        per_delivery,
        runtime,
    )

    summary_lookup = summary.set_index("metric")
    return {
        "scenario": scenario_name,
        "solver_run_id": solver_run_id,
        "solver_dir": display_path(solver_dir),
        "heuristic_dir": display_path(heuristic_dir),
        "output_dir": display_path(output_dir),
        "feasible_deliveries_solver": summary_lookup.loc[
            "feasible_deliveries",
            "solver",
        ],
        "feasible_deliveries_heuristic": summary_lookup.loc[
            "feasible_deliveries",
            "heuristic",
        ],
        "total_risk_solver": summary_lookup.loc["total_risk", "solver"],
        "total_risk_heuristic": summary_lookup.loc["total_risk", "heuristic"],
        "total_cost_solver": summary_lookup.loc["total_cost", "solver"],
        "total_cost_heuristic": summary_lookup.loc["total_cost", "heuristic"],
        "core_runtime_solver": summary_lookup.loc["core_runtime", "solver"],
        "core_runtime_heuristic": summary_lookup.loc["core_runtime", "heuristic"],
    }


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    solver_scenarios = discover_solver_scenarios(args.solver_dir)
    multiple = len(solver_scenarios) > 1
    index_rows = []
    for scenario_name, solver_dir in solver_scenarios:
        heuristic_dir = heuristic_scenario_dir(args.heuristic_dir, scenario_name)
        out_dir = scenario_output_dir(args.output_dir, scenario_name, multiple)
        index_rows.append(
            compare_scenario(
                scenario_name,
                solver_dir,
                heuristic_dir,
                out_dir,
            )
        )

    index = pd.DataFrame(index_rows)
    index.to_csv(args.output_dir / "comparison_index.csv", index=False)
    with (args.output_dir / "comparison_index.json").open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(index_rows, file, indent=2, ensure_ascii=False)
    print(f"Wrote comparison outputs to {args.output_dir}")


if __name__ == "__main__":
    main()
