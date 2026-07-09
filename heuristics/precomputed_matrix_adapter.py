"""Adapt precomputed Small, Medium, or Large CSV data to the heuristic.

The adapter deliberately uses the precomputed OD matrices instead of loading
the large road graph. It selects the safest loaded path for every regular
stop pair and conservatively uses that path for both loaded and empty travel.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
from pprint import pformat
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

if __package__:
    from .multi_customer_heuristic_toy import (
        CONSTRUCTION_STRATEGIES,
        DEPOT,
        ChargingStation,
        Customer,
        DepthTwoRepairRun,
        HeuristicRun,
        InputDataError,
        Leg,
        ObjectiveScales,
        ObjectiveWeights,
        RepairRun,
        SolutionEvaluation,
        ToyInstance,
        VNDRun,
        VNSRun,
        Vehicle,
        build_heuristic_routes,
        construct_initial_solution,
        improve_solution_vnd,
        improve_solution_vns,
        repair_partial_solution_depth_one,
        summarize_repair_run,
        summarize_run,
        summarize_vnd_run,
        summarize_vns_run,
        validate_instance,
    )
else:  # pragma: no cover - direct script execution
    from multi_customer_heuristic_toy import (
        CONSTRUCTION_STRATEGIES,
        DEPOT,
        ChargingStation,
        Customer,
        DepthTwoRepairRun,
        HeuristicRun,
        InputDataError,
        Leg,
        ObjectiveScales,
        ObjectiveWeights,
        RepairRun,
        SolutionEvaluation,
        ToyInstance,
        VNDRun,
        VNSRun,
        Vehicle,
        build_heuristic_routes,
        construct_initial_solution,
        improve_solution_vnd,
        improve_solution_vns,
        repair_partial_solution_depth_one,
        summarize_repair_run,
        summarize_run,
        summarize_vnd_run,
        summarize_vns_run,
        validate_instance,
    )


INSTANCE_FILE_PATTERN = "*instanz_*Timo.csv"
PROJECT_HAZARD_CLASSES = frozenset(
    {"1.1D", "2", "2 (TOC)", "3", "6", "8", "9"}
)
DEFAULT_SERVICE_MINUTES = 30.0
DEFAULT_SHIFT_END_MINUTES = 600.0
DEFAULT_DEPOT_ENERGY_PRICE = 0.35
DEFAULT_CHARGER_ENERGY_PRICE = 0.75
DEFAULT_CHARGER_POWER_KW = 300.0

INSTANCE_COLUMNS = {
    "id",
    "destination_name",
    "danger_class",
    "quantity",
    "unit",
}
VEHICLE_COLUMNS = {
    "type",
    "battery_kwh",
    "range_km",
    "energy_kwh_per_km",
    "variable_cost_per_km",
    "charging_power_kw",
    "fuel_capacity_l",
    "fixcost",
}
OD_COLUMNS = {
    "from",
    "to",
    "profile",
    "load_state",
    "dist_km",
    "cost",
    "time_min",
    "reachable",
    "tunnel_used",
}
CHARGER_COLUMNS = {
    "from",
    "to",
    "profile",
    "tunnel_used",
    "from_type",
    "to_type",
    "dist_km",
    "time_min",
    "risk",
}


@dataclass(frozen=True)
class MatrixAdapterResult:
    instance: ToyInstance
    dataset_name: str
    source_files: Mapping[str, str]
    customer_names: Mapping[str, str]
    vehicle_hazard_compatibility: Mapping[str, Tuple[str, ...]]
    vehicle_hazard_compatibility_source: str
    included_customers: Tuple[str, ...]
    excluded_customers: Tuple[str, ...]
    illegal_loaded_relations: Tuple[Tuple[str, str], ...]
    risk_source: str
    warnings: Tuple[str, ...]


def _read_csv(
    path: Path,
    required_columns: Iterable[str],
    *,
    select_required_columns: bool = False,
) -> pd.DataFrame:
    if not path.is_file():
        raise InputDataError(f"Required input file not found: {path}")
    try:
        header = pd.read_csv(path, nrows=0)
    except Exception as error:
        raise InputDataError(f"Could not read CSV file {path}: {error}") from error

    required = set(required_columns)
    missing = sorted(required - set(header.columns))
    if missing:
        raise InputDataError(
            f"{path.name} is missing required columns: {', '.join(missing)}"
        )
    try:
        return pd.read_csv(
            path,
            usecols=sorted(required) if select_required_columns else None,
        )
    except Exception as error:
        raise InputDataError(f"Could not read CSV file {path}: {error}") from error


def _find_instance_file(
    data_dir: Path,
    instance_file: Optional[Path],
) -> Path:
    if instance_file is not None:
        return instance_file.expanduser().resolve()

    matches = sorted(data_dir.glob(INSTANCE_FILE_PATTERN))
    if not matches:
        raise InputDataError(
            f"No instance file matching {INSTANCE_FILE_PATTERN!r} "
            f"was found in {data_dir}."
        )
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise InputDataError(
            "Several Timo instance files were found. Select one with "
            f"--instance-file: {names}"
        )
    return matches[0]


def _find_matrix_file(
    data_dir: Path,
    explicit_file: Optional[Path],
    *,
    charger_matrix: bool,
) -> Path:
    if explicit_file is not None:
        return explicit_file.expanduser().resolve()

    candidates = sorted(
        path
        for path in data_dir.glob("od_matrix_*.csv")
        if ("charger" in path.stem.lower()) == charger_matrix
    )
    matrix_label = "charger matrix" if charger_matrix else "OD matrix"
    if not candidates:
        raise InputDataError(
            f"No {matrix_label} CSV was found in {data_dir}."
        )
    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)
        argument = (
            "--charger-matrix-file"
            if charger_matrix
            else "--od-matrix-file"
        )
        raise InputDataError(
            f"Several {matrix_label} CSV files were found. "
            f"Select one with {argument}: {names}"
        )
    return candidates[0].resolve()


def _as_bool(value: object, label: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise InputDataError(f"{label} must be a boolean value, got {value!r}.")


def _finite_nonnegative(value: object, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise InputDataError(f"{label} must be numeric, got {value!r}.") from error
    if not pd.notna(number) or number == float("inf") or number == float("-inf"):
        raise InputDataError(f"{label} must be finite, got {value!r}.")
    if number < 0:
        raise InputDataError(f"{label} cannot be negative, got {number}.")
    return number


def _risk_rate(total_risk: object, distance_km: float, label: str) -> float:
    risk = _finite_nonnegative(total_risk, label)
    if distance_km == 0:
        if risk != 0:
            raise InputDataError(
                f"{label} is positive although the path distance is zero."
            )
        return 0.0
    return risk / distance_km


def _customer_sort_key(customer_id: str) -> Tuple[str, int, str]:
    prefix = customer_id.rstrip("0123456789")
    suffix = customer_id[len(prefix):]
    return prefix, int(suffix) if suffix else -1, customer_id


def _read_vehicle_hazard_compatibility_file(
    path: Path,
) -> Mapping[str, Iterable[str]]:
    if not path.is_file():
        raise InputDataError(
            f"Vehicle-hazard compatibility file not found: {path}"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InputDataError(
            f"Could not read vehicle-hazard compatibility JSON {path}: "
            f"{error}"
        ) from error
    if not isinstance(data, dict):
        raise InputDataError(
            "Vehicle-hazard compatibility JSON must contain an object "
            "mapping vehicle IDs to hazard-class lists."
        )
    return data


def _normalize_vehicle_hazard_compatibility(
    vehicle_ids: Sequence[str],
    hazard_classes: Sequence[str],
    compatibility: Optional[Mapping[str, Iterable[str]]],
) -> Tuple[Dict[str, Tuple[str, ...]], str]:
    instance_classes = set(hazard_classes)
    unsupported_instance_classes = sorted(
        instance_classes - PROJECT_HAZARD_CLASSES
    )
    if unsupported_instance_classes:
        raise InputDataError(
            "Instance contains unsupported hazard classes: "
            + ", ".join(unsupported_instance_classes)
        )
    if compatibility is None:
        all_classes = tuple(sorted(instance_classes))
        return (
            {
                vehicle_id: all_classes
                for vehicle_id in vehicle_ids
            },
            "assumption_all_vehicles_support_all_instance_classes",
        )

    normalized: Dict[str, Tuple[str, ...]] = {}
    for raw_vehicle_id, raw_classes in compatibility.items():
        vehicle_id = str(raw_vehicle_id).strip()
        if not vehicle_id:
            raise InputDataError(
                "Vehicle-hazard compatibility contains an empty vehicle ID."
            )
        if vehicle_id in normalized:
            raise InputDataError(
                "Vehicle-hazard compatibility contains duplicate normalized "
                f"vehicle ID {vehicle_id}."
            )
        if isinstance(raw_classes, (str, bytes)):
            raise InputDataError(
                f"{vehicle_id}: compatible hazard classes must be a list."
            )
        try:
            classes = tuple(
                sorted(
                    {
                        str(hazard_class).strip()
                        for hazard_class in raw_classes
                        if str(hazard_class).strip()
                    }
                )
            )
        except TypeError as error:
            raise InputDataError(
                f"{vehicle_id}: compatible hazard classes must be iterable."
            ) from error
        unknown_classes = sorted(set(classes) - PROJECT_HAZARD_CLASSES)
        if unknown_classes:
            raise InputDataError(
                f"{vehicle_id}: compatibility contains unsupported hazard "
                "classes: "
                + ", ".join(unknown_classes)
            )
        normalized[vehicle_id] = classes

    expected_ids = set(vehicle_ids)
    provided_ids = set(normalized)
    missing = sorted(expected_ids - provided_ids)
    unknown = sorted(provided_ids - expected_ids)
    if missing:
        raise InputDataError(
            "Vehicle-hazard compatibility is missing vehicles: "
            + ", ".join(missing)
        )
    if unknown:
        raise InputDataError(
            "Vehicle-hazard compatibility contains unknown vehicles: "
            + ", ".join(unknown)
        )
    unserved_classes = sorted(
        hazard_class
        for hazard_class in instance_classes
        if not any(
            hazard_class in classes
            for classes in normalized.values()
        )
    )
    if unserved_classes:
        raise InputDataError(
            "No vehicle supports instance hazard classes: "
            + ", ".join(unserved_classes)
        )
    return normalized, "explicit_mapping"


def _load_customers(
    frame: pd.DataFrame,
    excluded_customers: Iterable[str],
    service_minutes: float,
    shift_start_minute: float,
    shift_end_minute: float,
) -> Tuple[
    Dict[str, Customer],
    Dict[str, str],
    Tuple[str, ...],
    Tuple[str, ...],
]:
    normalized = frame.copy()
    normalized["id"] = normalized["id"].astype(str).str.strip()
    if normalized["id"].duplicated().any():
        duplicates = sorted(
            normalized.loc[normalized["id"].duplicated(False), "id"].unique()
        )
        raise InputDataError(
            "Instance contains duplicate stop IDs: " + ", ".join(duplicates)
        )
    if (normalized["id"] == DEPOT).sum() != 1:
        raise InputDataError("Instance must contain exactly one DEPOT row.")

    available_ids = set(normalized["id"]) - {DEPOT}
    excluded = tuple(
        sorted(
            {str(customer_id).strip() for customer_id in excluded_customers},
            key=_customer_sort_key,
        )
    )
    unknown = sorted(set(excluded) - available_ids, key=_customer_sort_key)
    if unknown:
        raise InputDataError(
            "Unknown excluded customer IDs: " + ", ".join(unknown)
        )

    customers: Dict[str, Customer] = {}
    customer_names: Dict[str, str] = {}
    customer_rows = normalized[normalized["id"] != DEPOT]
    for row in customer_rows.itertuples(index=False):
        customer_id = str(row.id).strip()
        if customer_id in excluded:
            continue
        unit = str(row.unit).strip().lower()
        if unit not in {"liter", "litre"}:
            raise InputDataError(
                f"{customer_id}: expected demand unit Liter, got {row.unit!r}."
            )
        demand_kg = _finite_nonnegative(
            row.quantity,
            f"{customer_id}.quantity",
        )
        if demand_kg <= 0:
            raise InputDataError(f"{customer_id}: demand must be positive.")
        hazard_class = str(row.danger_class).strip()
        if not hazard_class or hazard_class == "-":
            raise InputDataError(
                f"{customer_id}: danger_class must be provided."
            )
        customers[customer_id] = Customer(
            customer_id=customer_id,
            hazard_class=hazard_class,
            demand_kg=demand_kg,
            service_minutes=service_minutes,
            earliest_minute=shift_start_minute,
            latest_minute=shift_end_minute,
        )
        customer_names[customer_id] = str(row.destination_name).strip()

    if not customers:
        raise InputDataError("No customers remain after exclusions.")
    included = tuple(sorted(customers, key=_customer_sort_key))
    return customers, customer_names, included, excluded


def _load_vehicles(
    frame: pd.DataFrame,
    hazard_classes: Sequence[str],
    vehicle_hazard_compatibility: Optional[
        Mapping[str, Iterable[str]]
    ],
    shift_start_minute: float,
    shift_end_minute: float,
    initial_load_minutes: float,
    reload_minutes: float,
    max_daily_driving_minutes: float,
    max_daily_working_minutes: float,
    reserve_fraction: float,
) -> Tuple[
    Dict[str, Vehicle],
    Dict[str, Tuple[str, ...]],
    str,
]:
    vehicles: Dict[str, Vehicle] = {}
    vehicle_ids = [str(value).strip() for value in frame["type"]]
    if any(not vehicle_id for vehicle_id in vehicle_ids):
        raise InputDataError("Vehicle type cannot be empty.")
    if len(vehicle_ids) != len(set(vehicle_ids)):
        duplicates = sorted(
            {
                vehicle_id
                for vehicle_id in vehicle_ids
                if vehicle_ids.count(vehicle_id) > 1
            }
        )
        raise InputDataError(
            "Duplicate physical vehicle IDs: " + ", ".join(duplicates)
        )
    compatibility, compatibility_source = (
        _normalize_vehicle_hazard_compatibility(
            vehicle_ids,
            hazard_classes,
            vehicle_hazard_compatibility,
        )
    )
    for row in frame.itertuples(index=False):
        vehicle_id = str(row.type).strip()

        battery_kwh = _finite_nonnegative(
            row.battery_kwh,
            f"{vehicle_id}.battery_kwh",
        )
        range_km = _finite_nonnegative(
            row.range_km,
            f"{vehicle_id}.range_km",
        )
        energy_rate = _finite_nonnegative(
            row.energy_kwh_per_km,
            f"{vehicle_id}.energy_kwh_per_km",
        )
        usable_battery = min(battery_kwh, range_km * energy_rate)
        if usable_battery <= 0:
            raise InputDataError(
                f"{vehicle_id}: usable battery must be positive."
            )

        capacity_kg = _finite_nonnegative(
            row.fuel_capacity_l,
            f"{vehicle_id}.fuel_capacity_l",
        )
        if capacity_kg <= 0:
            raise InputDataError(
                f"{vehicle_id}: fuel capacity must be positive."
            )
        vehicles[vehicle_id] = Vehicle(
            vehicle_id=vehicle_id,
            vehicle_type=vehicle_id,
            capacity_kg=capacity_kg,
            usable_battery_kwh=usable_battery,
            initial_battery_kwh=usable_battery,
            min_reserve_kwh=usable_battery * reserve_fraction,
            energy_kwh_per_km=energy_rate,
            max_charging_power_kw=_finite_nonnegative(
                row.charging_power_kw,
                f"{vehicle_id}.charging_power_kw",
            ),
            compatible_classes=compatibility[vehicle_id],
            activation_cost=_finite_nonnegative(
                row.fixcost,
                f"{vehicle_id}.fixcost",
            ),
            trip_cost=0.0,
            road_cost_per_km=_finite_nonnegative(
                row.variable_cost_per_km,
                f"{vehicle_id}.variable_cost_per_km",
            ),
            shift_start_minute=shift_start_minute,
            shift_end_minute=shift_end_minute,
            initial_load_minutes=initial_load_minutes,
            reload_minutes=reload_minutes,
            max_daily_driving_minutes=max_daily_driving_minutes,
            max_daily_working_minutes=max_daily_working_minutes,
            solver_name=vehicle_id,
        )
    if not vehicles:
        raise InputDataError("Vehicle file contains no vehicles.")
    return vehicles, compatibility, compatibility_source


def _load_regular_legs(
    frame: pd.DataFrame,
    regular_stops: Sequence[str],
    hazard_classes: Sequence[str],
) -> Tuple[Dict[Tuple[str, str], Leg], Tuple[Tuple[str, str], ...]]:
    normalized = frame.copy()
    normalized["from"] = normalized["from"].astype(str).str.strip()
    normalized["to"] = normalized["to"].astype(str).str.strip()
    safest_loaded = normalized[
        (
            normalized["profile"].astype(str).str.strip().str.lower()
            == "safest"
        )
        & (
            normalized["load_state"].astype(str).str.strip().str.lower()
            == "loaded"
        )
    ].rename(columns={"from": "from_stop", "to": "to_stop"})
    if safest_loaded.empty:
        raise InputDataError(
            "OD matrix contains no profile=safest, load_state=loaded rows."
        )
    duplicates = safest_loaded.duplicated(
        ["from_stop", "to_stop"],
        keep=False,
    )
    if duplicates.any():
        pairs = sorted(
            {
                f"{row['from_stop']}->{row['to_stop']}"
                for _, row in safest_loaded.loc[duplicates].iterrows()
            }
        )
        raise InputDataError(
            "OD matrix contains duplicate safest loaded pairs: "
            + ", ".join(pairs)
        )

    stop_set = set(regular_stops)
    allowed_classes = tuple(sorted(set(hazard_classes)))
    legs: Dict[Tuple[str, str], Leg] = {}
    illegal: List[Tuple[str, str]] = []
    for row in safest_loaded.itertuples(index=False):
        from_stop = str(row.from_stop).strip()
        to_stop = str(row.to_stop).strip()
        if from_stop not in stop_set or to_stop not in stop_set:
            continue
        relation = (from_stop, to_stop)
        reachable = _as_bool(
            row.reachable,
            f"{from_stop}->{to_stop}.reachable",
        )
        tunnel_used = _as_bool(
            row.tunnel_used,
            f"{from_stop}->{to_stop}.tunnel_used",
        )
        numeric = pd.to_numeric(
            pd.Series([row.dist_km, row.time_min, row.cost]),
            errors="coerce",
        )
        metrics_are_finite = all(
            pd.notna(value) and math.isfinite(float(value))
            for value in numeric
        )
        if (
            not reachable
            or tunnel_used
            or not metrics_are_finite
        ):
            illegal.append(relation)
            continue

        distance_km = _finite_nonnegative(
            row.dist_km,
            f"{from_stop}->{to_stop}.dist_km",
        )
        legs[relation] = Leg(
            from_stop=from_stop,
            to_stop=to_stop,
            distance_km=distance_km,
            travel_minutes=_finite_nonnegative(
                row.time_min,
                f"{from_stop}->{to_stop}.time_min",
            ),
            base_risk_rate_per_km=_risk_rate(
                row.cost,
                distance_km,
                f"{from_stop}->{to_stop}.cost",
            ),
            allowed_classes=allowed_classes,
        )
    return legs, tuple(sorted(set(illegal)))


def _load_charger_legs(
    frame: pd.DataFrame,
    regular_stops: Sequence[str],
    hazard_classes: Sequence[str],
    charger_power_kw: float,
    charger_energy_price_per_kwh: float,
    charger_session_fee: float,
) -> Tuple[
    Dict[Tuple[str, str], Leg],
    Dict[str, ChargingStation],
    Dict[str, Tuple[str, ...]],
]:
    normalized = frame.copy()
    normalized["from"] = normalized["from"].astype(str).str.strip()
    normalized["to"] = normalized["to"].astype(str).str.strip()
    safest = normalized[
        normalized["profile"].astype(str).str.strip().str.lower()
        == "safest"
    ].rename(columns={"from": "from_stop", "to": "to_stop"})
    if safest.empty:
        raise InputDataError("Charger matrix contains no profile=safest rows.")
    duplicates = safest.duplicated(["from_stop", "to_stop"], keep=False)
    if duplicates.any():
        raise InputDataError(
            "Charger matrix contains duplicate safest rows for a stop pair."
        )

    stop_set = set(regular_stops)
    allowed_classes = tuple(sorted(set(hazard_classes)))
    legs: Dict[Tuple[str, str], Leg] = {}
    station_ids = set()
    for row in safest.itertuples(index=False):
        from_stop = str(row.from_stop).strip()
        to_stop = str(row.to_stop).strip()
        from_type = str(row.from_type).strip().lower()
        to_type = str(row.to_type).strip().lower()
        if from_type == "charger" and to_type in {"customer", "depot"}:
            station_id, regular_stop = from_stop, to_stop
        elif to_type == "charger" and from_type in {"customer", "depot"}:
            station_id, regular_stop = to_stop, from_stop
        else:
            raise InputDataError(
                f"Unexpected charger relation types for {from_stop}->{to_stop}: "
                f"{from_type}->{to_type}."
            )
        if regular_stop not in stop_set:
            continue
        if _as_bool(
            row.tunnel_used,
            f"{from_stop}->{to_stop}.tunnel_used",
        ):
            continue

        distance_km = _finite_nonnegative(
            row.dist_km,
            f"{from_stop}->{to_stop}.dist_km",
        )
        legs[(from_stop, to_stop)] = Leg(
            from_stop=from_stop,
            to_stop=to_stop,
            distance_km=distance_km,
            travel_minutes=_finite_nonnegative(
                row.time_min,
                f"{from_stop}->{to_stop}.time_min",
            ),
            base_risk_rate_per_km=_risk_rate(
                row.risk,
                distance_km,
                f"{from_stop}->{to_stop}.risk",
            ),
            allowed_classes=allowed_classes,
        )
        station_ids.add(station_id)

    chargers = {
        station_id: ChargingStation(
            station_id=station_id,
            power_kw=charger_power_kw,
            energy_price_per_kwh=charger_energy_price_per_kwh,
            session_fee=charger_session_fee,
        )
        for station_id in sorted(station_ids)
    }
    candidates: Dict[str, Tuple[str, ...]] = {}
    for regular_stop in sorted(stop_set, key=_customer_sort_key):
        if regular_stop == DEPOT:
            continue
        ranked = []
        for station_id in chargers:
            outward = legs.get((regular_stop, station_id))
            return_leg = legs.get((station_id, regular_stop))
            if outward is None or return_leg is None:
                continue
            ranked.append(
                (
                    outward.distance_km + return_leg.distance_km,
                    station_id,
                )
            )
        candidates[regular_stop] = tuple(
            station_id
            for _, station_id in sorted(ranked)[:3]
        )
    return legs, chargers, candidates


def build_matrix_adapter(
    data_dir: Path,
    *,
    vehicles_file: Optional[Path] = None,
    instance_file: Optional[Path] = None,
    od_matrix_file: Optional[Path] = None,
    charger_matrix_file: Optional[Path] = None,
    vehicle_hazard_compatibility: Optional[
        Mapping[str, Iterable[str]]
    ] = None,
    vehicle_hazard_compatibility_file: Optional[Path] = None,
    excluded_customers: Iterable[str] = (),
    service_minutes: float = DEFAULT_SERVICE_MINUTES,
    shift_start_minute: float = 0.0,
    shift_end_minute: float = DEFAULT_SHIFT_END_MINUTES,
    initial_load_minutes: float = 20.0,
    reload_minutes: float = 15.0,
    max_daily_driving_minutes: float = 540.0,
    max_daily_working_minutes: float = 600.0,
    continuous_driving_limit_minutes: float = 270.0,
    break_duration_minutes: float = 45.0,
    reserve_fraction: float = 0.10,
    depot_charging_power_kw: float = DEFAULT_CHARGER_POWER_KW,
    depot_energy_price_per_kwh: float = DEFAULT_DEPOT_ENERGY_PRICE,
    charger_power_kw: float = DEFAULT_CHARGER_POWER_KW,
    charger_energy_price_per_kwh: float = DEFAULT_CHARGER_ENERGY_PRICE,
    charger_session_fee: float = 0.0,
    max_charging_branch_evaluations: int = 100,
    weights: ObjectiveWeights = ObjectiveWeights(),
) -> MatrixAdapterResult:
    """Load a coherent precomputed-matrix data set into a ``ToyInstance``."""
    data_dir = data_dir.expanduser().resolve()
    if not data_dir.is_dir():
        raise InputDataError(f"Data directory not found: {data_dir}")

    resolved_instance_file = _find_instance_file(data_dir, instance_file)
    resolved_vehicles_file = (
        vehicles_file.expanduser().resolve()
        if vehicles_file is not None
        else (data_dir.parent / "vehicles.csv").resolve()
    )
    resolved_od_file = _find_matrix_file(
        data_dir,
        od_matrix_file,
        charger_matrix=False,
    )
    resolved_charger_file = _find_matrix_file(
        data_dir,
        charger_matrix_file,
        charger_matrix=True,
    )
    if (
        vehicle_hazard_compatibility is not None
        and vehicle_hazard_compatibility_file is not None
    ):
        raise InputDataError(
            "Provide vehicle_hazard_compatibility or "
            "vehicle_hazard_compatibility_file, not both."
        )
    resolved_compatibility_file = (
        vehicle_hazard_compatibility_file.expanduser().resolve()
        if vehicle_hazard_compatibility_file is not None
        else None
    )
    if resolved_compatibility_file is not None:
        vehicle_hazard_compatibility = (
            _read_vehicle_hazard_compatibility_file(
                resolved_compatibility_file
            )
        )
    instance_frame = _read_csv(resolved_instance_file, INSTANCE_COLUMNS)
    vehicle_frame = _read_csv(resolved_vehicles_file, VEHICLE_COLUMNS)
    od_frame = _read_csv(
        resolved_od_file,
        OD_COLUMNS,
        select_required_columns=True,
    )
    charger_frame = _read_csv(
        resolved_charger_file,
        CHARGER_COLUMNS,
        select_required_columns=True,
    )

    scalar_parameters = {
        "service_minutes": service_minutes,
        "shift_start_minute": shift_start_minute,
        "shift_end_minute": shift_end_minute,
        "initial_load_minutes": initial_load_minutes,
        "reload_minutes": reload_minutes,
        "max_daily_driving_minutes": max_daily_driving_minutes,
        "max_daily_working_minutes": max_daily_working_minutes,
        "continuous_driving_limit_minutes": continuous_driving_limit_minutes,
        "break_duration_minutes": break_duration_minutes,
        "depot_charging_power_kw": depot_charging_power_kw,
        "depot_energy_price_per_kwh": depot_energy_price_per_kwh,
        "charger_power_kw": charger_power_kw,
        "charger_energy_price_per_kwh": charger_energy_price_per_kwh,
        "charger_session_fee": charger_session_fee,
    }
    for label, value in scalar_parameters.items():
        _finite_nonnegative(value, label)
    for label, value in (
        ("depot_charging_power_kw", depot_charging_power_kw),
        ("charger_power_kw", charger_power_kw),
        (
            "continuous_driving_limit_minutes",
            continuous_driving_limit_minutes,
        ),
        ("break_duration_minutes", break_duration_minutes),
        ("max_daily_driving_minutes", max_daily_driving_minutes),
        ("max_daily_working_minutes", max_daily_working_minutes),
    ):
        if value <= 0:
            raise InputDataError(f"{label} must be positive.")
    if not 0 <= reserve_fraction < 1:
        raise InputDataError("reserve_fraction must be in [0, 1).")
    if shift_start_minute >= shift_end_minute:
        raise InputDataError(
            "shift_start_minute must be earlier than shift_end_minute."
        )

    customers, customer_names, included, excluded = _load_customers(
        instance_frame,
        excluded_customers,
        service_minutes,
        shift_start_minute,
        shift_end_minute,
    )
    hazard_classes = tuple(
        sorted({customer.hazard_class for customer in customers.values()})
    )
    (
        vehicles,
        normalized_compatibility,
        compatibility_source,
    ) = _load_vehicles(
        vehicle_frame,
        hazard_classes,
        vehicle_hazard_compatibility,
        shift_start_minute,
        shift_end_minute,
        initial_load_minutes,
        reload_minutes,
        max_daily_driving_minutes,
        max_daily_working_minutes,
        reserve_fraction,
    )
    unserviceable = sorted(
        customer_id
        for customer_id, customer in customers.items()
        if all(
            customer.demand_kg > vehicle.capacity_kg
            or customer.hazard_class not in vehicle.compatible_classes
            for vehicle in vehicles.values()
        )
    )
    if unserviceable:
        raise InputDataError(
            "No capacity-compatible vehicle accepts the hazard class for: "
            + ", ".join(unserviceable)
        )

    regular_stops = (DEPOT, *included)
    regular_legs, illegal_relations = _load_regular_legs(
        od_frame,
        regular_stops,
        hazard_classes,
    )
    charger_legs, chargers, charger_candidates = _load_charger_legs(
        charger_frame,
        regular_stops,
        hazard_classes,
        charger_power_kw,
        charger_energy_price_per_kwh,
        charger_session_fee,
    )
    legs = {**regular_legs, **charger_legs}
    instance = ToyInstance(
        customers=customers,
        vehicles=vehicles,
        chargers=chargers,
        customer_charger_candidates=charger_candidates,
        legs=legs,
        break_nodes=(DEPOT, *sorted(chargers)),
        depot_charging_power_kw=depot_charging_power_kw,
        depot_energy_price_per_kwh=depot_energy_price_per_kwh,
        continuous_driving_limit_minutes=continuous_driving_limit_minutes,
        break_duration_minutes=break_duration_minutes,
        max_charging_branch_evaluations=max_charging_branch_evaluations,
        weights=weights,
    )
    validate_instance(instance)

    warnings = [
        "Customer quantities in Liter are converted with 1 Liter = 1 kg.",
        (
            "The safest loaded OD cost is provisionally treated as total "
            "path risk and divided by path distance."
        ),
        (
            "The loaded HazMat-safe OD path is conservatively reused for "
            "empty travel because the upper-level Leg has no load-state field."
        ),
        (
            "Charging-station power and energy price use adapter defaults; "
            "the charger CSV contains no station-specific values."
        ),
        (
            "Vehicle payload uses fuel_capacity_l and activation cost uses "
            "fixcost to match the current solver assumptions."
        ),
        (
            "Service, loading, shift, driving, and break times are adapter "
            "scenario settings because the supplied CSVs do not contain them."
        ),
    ]
    if compatibility_source.startswith("assumption_"):
        warnings.append(
            "Vehicle-hazard compatibility is an explicit adapter assumption: "
            "all vehicles support all hazard classes present in this instance."
        )
    if excluded:
        warnings.append(
            "Customers excluded explicitly for this run: " + ", ".join(excluded)
        )
    if illegal_relations:
        warnings.append(
            f"{len(illegal_relations)} loaded safest OD relations were "
            "excluded because they are unreachable, non-finite, or use a tunnel."
        )

    source_files = {
        "instance": str(resolved_instance_file),
        "vehicles": str(resolved_vehicles_file),
        "od_matrix": str(resolved_od_file),
        "charger_matrix": str(resolved_charger_file),
    }
    if resolved_compatibility_file is not None:
        source_files["vehicle_hazard_compatibility"] = str(
            resolved_compatibility_file
        )

    return MatrixAdapterResult(
        instance=instance,
        dataset_name=data_dir.name,
        source_files=source_files,
        customer_names=customer_names,
        vehicle_hazard_compatibility=normalized_compatibility,
        vehicle_hazard_compatibility_source=compatibility_source,
        included_customers=included,
        excluded_customers=excluded,
        illegal_loaded_relations=illegal_relations,
        risk_source="safest.loaded.cost / dist_km",
        warnings=tuple(warnings),
    )


# Compatibility aliases for existing notebooks and scripts.
SmallAdapterResult = MatrixAdapterResult
build_small_adapter = build_matrix_adapter


def summarize_adapter(result: MatrixAdapterResult) -> str:
    lines = [
        "Matrix-based multi-customer data adapter",
        "-" * 40,
        f"dataset_name={result.dataset_name}",
        f"included_customers={','.join(result.included_customers)}",
        (
            "excluded_customers="
            + (
                ",".join(result.excluded_customers)
                if result.excluded_customers
                else "none"
            )
        ),
        f"vehicles={','.join(result.instance.vehicles)}",
        f"chargers={len(result.instance.chargers)}",
        f"legs={len(result.instance.legs)}",
        f"risk_source={result.risk_source}",
        (
            "vehicle_hazard_compatibility_source="
            f"{result.vehicle_hazard_compatibility_source}"
        ),
    ]
    if result.illegal_loaded_relations:
        lines.append(
            "illegal_loaded_relations="
            + ",".join(
                f"{from_stop}->{to_stop}"
                for from_stop, to_stop in result.illegal_loaded_relations
            )
        )
    for customer_id in result.included_customers:
        lines.append(
            f"customer_name[{customer_id}]="
            f"{result.customer_names[customer_id]}"
        )
    for warning in result.warnings:
        lines.append(f"warning={warning}")
    return "\n".join(lines)


def _solver_vehicle_name(
    instance: ToyInstance,
    vehicle_id: str,
) -> str:
    vehicle = instance.vehicles[vehicle_id]
    return vehicle.solver_name or vehicle.vehicle_type


def _solver_trip_routes(
    adapter_result: MatrixAdapterResult,
    evaluation: SolutionEvaluation,
) -> Dict[str, List[List[str]]]:
    routes: Dict[str, List[List[str]]] = {}
    for vehicle_id, vehicle_evaluation in (
        evaluation.vehicle_evaluations.items()
    ):
        if not vehicle_evaluation.trips:
            continue
        solver_name = _solver_vehicle_name(
            adapter_result.instance,
            vehicle_id,
        )
        routes[solver_name] = [
            [DEPOT, *trip.customer_sequence, DEPOT]
            for trip in vehicle_evaluation.trips
        ]
    return routes


def _technical_trip_routes(
    adapter_result: MatrixAdapterResult,
    evaluation: SolutionEvaluation,
) -> Dict[str, List[List[str]]]:
    routes: Dict[str, List[List[str]]] = {}
    for vehicle_id, vehicle_evaluation in (
        evaluation.vehicle_evaluations.items()
    ):
        if not vehicle_evaluation.trips:
            continue
        solver_name = _solver_vehicle_name(
            adapter_result.instance,
            vehicle_id,
        )
        routes[solver_name] = [
            list(trip.stop_sequence)
            for trip in vehicle_evaluation.trips
        ]
    return routes


def _charging_side_trips(
    adapter_result: MatrixAdapterResult,
    evaluation: SolutionEvaluation,
) -> Dict[str, List[Dict[str, Any]]]:
    side_trips: Dict[str, List[Dict[str, Any]]] = {}
    chargers = set(adapter_result.instance.chargers)
    for vehicle_id, vehicle_evaluation in (
        evaluation.vehicle_evaluations.items()
    ):
        vehicle_side_trips: List[Dict[str, Any]] = []
        for trip in vehicle_evaluation.trips:
            stops = trip.stop_sequence
            for stop_index, station_id in enumerate(stops):
                if station_id not in chargers:
                    continue
                origin_stop = (
                    stops[stop_index - 1]
                    if stop_index > 0
                    else None
                )
                returns_to_origin = (
                    origin_stop is not None
                    and stop_index + 1 < len(stops)
                    and stops[stop_index + 1] == origin_stop
                )
                vehicle_side_trips.append(
                    {
                        "trip_index": trip.trip_index,
                        "origin_stop": origin_stop,
                        "station_id": station_id,
                        "returns_to_origin": returns_to_origin,
                        "solver_y_compatible": (
                            origin_stop
                            in adapter_result.instance.customers
                            and returns_to_origin
                        ),
                    }
                )
        if vehicle_evaluation.trips:
            solver_name = _solver_vehicle_name(
                adapter_result.instance,
                vehicle_id,
            )
            side_trips[solver_name] = vehicle_side_trips
    return side_trips


def _vnd_result_metadata(vnd_run: Optional[VNDRun]) -> Optional[Dict[str, Any]]:
    if vnd_run is None:
        return None
    return {
        "status": vnd_run.status,
        "stop_reason": vnd_run.status,
        "max_neighborhood_passes": vnd_run.max_neighborhood_passes,
        "neighborhood_passes": vnd_run.neighborhood_passes,
        "initial_objective": vnd_run.initial_evaluation.objective,
        "final_objective": vnd_run.evaluation.objective,
        "accepted_moves": [
            {
                "neighborhood": move.neighborhood,
                "description": move.description,
                "objective_before": move.objective_before,
                "objective_after": move.objective_after,
            }
            for move in vnd_run.accepted_moves
        ],
        "evaluated_candidates": vnd_run.evaluated_candidates,
        "incomplete_candidates": vnd_run.incomplete_candidates,
        "incomplete_neighborhoods": list(
            vnd_run.incomplete_neighborhoods
        ),
        "runtime_seconds": vnd_run.runtime_seconds,
        "single_trip_per_vehicle": vnd_run.single_trip_per_vehicle,
    }


def _vns_result_metadata(vns_run: Optional[VNSRun]) -> Optional[Dict[str, Any]]:
    if vns_run is None:
        return None
    return {
        "status": vns_run.status,
        "stop_reason": vns_run.status,
        "random_seed": vns_run.random_seed,
        "max_iterations": vns_run.max_iterations,
        "max_seconds": vns_run.max_seconds,
        "max_vnd_neighborhood_passes": (
            vns_run.max_vnd_neighborhood_passes
        ),
        "iterations": vns_run.iterations,
        "initial_objective": vns_run.initial_evaluation.objective,
        "final_objective": vns_run.evaluation.objective,
        "accepted_improvements": [
            {
                "iteration": improvement.iteration,
                "neighborhood": improvement.neighborhood,
                "shake_description": improvement.shake_description,
                "objective_before": improvement.objective_before,
                "shaken_objective": improvement.shaken_objective,
                "objective_after": improvement.objective_after,
                "vnd_moves": improvement.vnd_moves,
            }
            for improvement in vns_run.accepted_improvements
        ],
        "evaluated_shakes": vns_run.evaluated_shakes,
        "feasible_shakes": vns_run.feasible_shakes,
        "incomplete_shakes": vns_run.incomplete_shakes,
        "incomplete_local_searches": (
            vns_run.incomplete_local_searches
        ),
        "incomplete_neighborhoods": list(
            vns_run.incomplete_neighborhoods
        ),
        "vnd_runs": vns_run.vnd_runs,
        "vnd_evaluated_candidates": vns_run.vnd_evaluated_candidates,
        "runtime_seconds": vns_run.runtime_seconds,
        "single_trip_per_vehicle": vns_run.single_trip_per_vehicle,
    }


def _schedule_details(
    adapter_result: MatrixAdapterResult,
    evaluation: SolutionEvaluation,
) -> Dict[str, Any]:
    details: Dict[str, Any] = {}
    for vehicle_id, vehicle_evaluation in sorted(
        evaluation.vehicle_evaluations.items()
    ):
        details[vehicle_id] = {
            "vehicle_id": vehicle_id,
            "solver_name": _solver_vehicle_name(
                adapter_result.instance,
                vehicle_id,
            ),
            "feasible": vehicle_evaluation.feasible,
            "reasons": list(vehicle_evaluation.reasons),
            "activation_cost": vehicle_evaluation.activation_cost,
            "trip_cost": vehicle_evaluation.trip_cost,
            "road_operating_cost": (
                vehicle_evaluation.road_operating_cost
            ),
            "station_charging_cost": (
                vehicle_evaluation.station_charging_cost
            ),
            "end_of_day_recharge_kwh": (
                vehicle_evaluation.end_of_day_recharge_kwh
            ),
            "end_of_day_recharge_cost": (
                vehicle_evaluation.end_of_day_recharge_cost
            ),
            "total_cost": vehicle_evaluation.total_cost,
            "total_risk": vehicle_evaluation.total_risk,
            "total_distance_km": vehicle_evaluation.total_distance_km,
            "total_travel_minutes": (
                vehicle_evaluation.total_travel_minutes
            ),
            "total_service_minutes": (
                vehicle_evaluation.total_service_minutes
            ),
            "total_waiting_minutes": (
                vehicle_evaluation.total_waiting_minutes
            ),
            "total_charging_minutes": (
                vehicle_evaluation.total_charging_minutes
            ),
            "total_break_minutes": (
                vehicle_evaluation.total_break_minutes
            ),
            "operating_minutes": vehicle_evaluation.operating_minutes,
            "first_activity_minute": (
                vehicle_evaluation.first_activity_minute
            ),
            "last_return_minute": vehicle_evaluation.last_return_minute,
            "final_battery_kwh": vehicle_evaluation.final_battery_kwh,
            "charging_branch_evaluations": (
                vehicle_evaluation.charging_branch_evaluations
            ),
            "trips": [
                {
                    "trip_index": trip.trip_index,
                    "hazard_class": trip.hazard_class,
                    "customer_sequence": list(trip.customer_sequence),
                    "stop_sequence": list(trip.stop_sequence),
                    "start_minute": trip.start_minute,
                    "return_minute": trip.return_minute,
                    "initial_load_kg": trip.initial_load_kg,
                    "final_battery_kwh": trip.final_battery_kwh,
                    "minimum_battery_kwh": trip.minimum_battery_kwh,
                    "total_risk": trip.total_risk,
                    "road_operating_cost": trip.road_operating_cost,
                    "station_charging_cost": (
                        trip.station_charging_cost
                    ),
                    "trip_cost": trip.trip_cost,
                    "travel_minutes": trip.travel_minutes,
                    "service_minutes": trip.service_minutes,
                    "waiting_minutes": trip.waiting_minutes,
                    "charging_minutes": trip.charging_minutes,
                    "break_minutes": trip.break_minutes,
                    "visits": [
                        {
                            "stop_id": visit.stop_id,
                            "stop_type": visit.stop_type,
                            "arrival_minute": visit.arrival_minute,
                            "departure_minute": visit.departure_minute,
                            "delivered_kg": visit.delivered_kg,
                            "remaining_load_kg": (
                                visit.remaining_load_kg
                            ),
                            "battery_arrival_kwh": (
                                visit.battery_arrival_kwh
                            ),
                            "battery_departure_kwh": (
                                visit.battery_departure_kwh
                            ),
                            "charged_energy_kwh": (
                                visit.charged_energy_kwh
                            ),
                            "charging_minutes": visit.charging_minutes,
                            "break_minutes": visit.break_minutes,
                        }
                        for visit in trip.visits
                    ],
                    "legs": [
                        {
                            "from_stop": leg.from_stop,
                            "to_stop": leg.to_stop,
                            "loaded": leg.loaded,
                            "distance_km": leg.distance_km,
                            "travel_minutes": leg.travel_minutes,
                            "risk": leg.risk,
                            "energy_kwh": leg.energy_kwh,
                            "road_operating_cost": (
                                leg.road_operating_cost
                            ),
                            "battery_before_kwh": (
                                leg.battery_before_kwh
                            ),
                            "battery_after_kwh": leg.battery_after_kwh,
                        }
                        for leg in trip.legs
                    ],
                }
                for trip in vehicle_evaluation.trips
            ],
        }
    return details


def build_result_payload(
    adapter_result: MatrixAdapterResult,
    evaluation: SolutionEvaluation,
    *,
    construction_run: HeuristicRun,
    search_status: str,
    runtime_seconds: Mapping[str, float],
    objective_scales: Optional[ObjectiveScales] = None,
    repair_run: Optional[RepairRun] = None,
    depth_two_repair_run: Optional[DepthTwoRepairRun] = None,
    vnd_run: Optional[VNDRun] = None,
    vns_run: Optional[VNSRun] = None,
) -> Dict[str, Any]:
    """Build a JSON-safe heuristic result and comparison payload."""
    if construction_run.construction_strategy not in CONSTRUCTION_STRATEGIES:
        allowed = ", ".join(CONSTRUCTION_STRATEGIES)
        raise InputDataError(
            "construction_run contains an invalid construction strategy "
            f"{construction_run.construction_strategy!r}; expected one of: "
            f"{allowed}."
        )
    final_search_run = vns_run if vns_run is not None else vnd_run
    if vns_run is not None and vnd_run is not None:
        if vns_run.initial_evaluation != vnd_run.evaluation:
            raise InputDataError(
                "vns_run does not start from the supplied vnd_run "
                "evaluation."
            )
        if vns_run.scales != vnd_run.scales:
            raise InputDataError(
                "vns_run and vnd_run use different objective scales."
            )
    if final_search_run is not None:
        if evaluation != final_search_run.evaluation:
            raise InputDataError(
                "Final evaluation does not match the supplied VND/VNS run."
            )
        if search_status != final_search_run.status:
            raise InputDataError(
                "search_status does not match the supplied VND/VNS run."
            )
        if objective_scales is None:
            objective_scales = final_search_run.scales
        elif objective_scales != final_search_run.scales:
            raise InputDataError(
                "objective_scales do not match the supplied VND/VNS run."
            )
    feasible = evaluation.feasible and not evaluation.unserved_customers
    routes = (
        {
            vehicle_id: list(route)
            for vehicle_id, route in build_heuristic_routes(
                adapter_result.instance,
                evaluation,
            ).items()
        }
        if feasible
        else {}
    )
    trips = (
        _solver_trip_routes(adapter_result, evaluation)
        if feasible
        else {}
    )
    technical_routes = (
        _technical_trip_routes(adapter_result, evaluation)
        if feasible
        else {}
    )
    charging_side_trips = (
        _charging_side_trips(adapter_result, evaluation)
        if feasible
        else {}
    )
    single_trip_per_vehicle = all(
        len(vehicle_trips) <= 1
        for vehicle_trips in trips.values()
    )
    charging_is_solver_compatible = all(
        side_trip["solver_y_compatible"]
        for vehicle_side_trips in charging_side_trips.values()
        for side_trip in vehicle_side_trips
    )
    solver_structure_compatible = (
        feasible
        and single_trip_per_vehicle
        and charging_is_solver_compatible
    )
    runtimes: Dict[str, float] = {}
    for name, value in runtime_seconds.items():
        runtime_name = str(name)
        runtimes[runtime_name] = _finite_nonnegative(
            value,
            f"runtime_seconds.{runtime_name}",
        )

    return {
        "schema_version": "1.0",
        "status": "feasible" if feasible else "infeasible",
        "search_status": search_status,
        "routes": routes,
        "trips": trips,
        "charging_side_trips": charging_side_trips,
        "technical_routes": technical_routes,
        "metadata": {
            "dataset_name": adapter_result.dataset_name,
            "construction_strategy": construction_run.construction_strategy,
            "included_customers": list(
                adapter_result.included_customers
            ),
            "excluded_customers": list(
                adapter_result.excluded_customers
            ),
            "served_customers": list(evaluation.served_customers),
            "unserved_customers": list(evaluation.unserved_customers),
            "customer_names": dict(adapter_result.customer_names),
            "vehicle_ids": list(adapter_result.instance.vehicles),
            "vehicle_hazard_compatibility": {
                vehicle_id: list(classes)
                for vehicle_id, classes
                in adapter_result.vehicle_hazard_compatibility.items()
            },
            "vehicle_hazard_compatibility_source": (
                adapter_result.vehicle_hazard_compatibility_source
            ),
            "risk_source": adapter_result.risk_source,
            "max_charging_branch_evaluations": (
                adapter_result.instance.max_charging_branch_evaluations
            ),
            "repair": (
                {
                    "status": repair_run.status,
                    "stop_reason": repair_run.stop_reason,
                    "max_candidate_evaluations": (
                        repair_run.max_candidate_evaluations
                    ),
                    "max_seconds": repair_run.max_seconds,
                    "max_primary_candidates_per_ejection": (
                        repair_run.max_primary_candidates_per_ejection
                    ),
                    "accepted_moves": [
                        {
                            "inserted_customer": move.inserted_customer,
                            "ejected_customer": move.ejected_customer,
                            "objective_before": move.objective_before,
                            "objective_after": move.objective_after,
                        }
                        for move in repair_run.accepted_moves
                    ],
                    "evaluated_candidates": (
                        repair_run.evaluated_candidates
                    ),
                    "incomplete_candidates": (
                        repair_run.incomplete_candidates
                    ),
                }
                if repair_run is not None
                else None
            ),
            "depth_two_repair": (
                {
                    "status": depth_two_repair_run.status,
                    "stop_reason": depth_two_repair_run.stop_reason,
                    "max_candidate_evaluations": (
                        depth_two_repair_run.max_candidate_evaluations
                    ),
                    "max_seconds": depth_two_repair_run.max_seconds,
                    "max_primary_candidates": (
                        depth_two_repair_run.max_primary_candidates
                    ),
                    "max_first_reinsertions": (
                        depth_two_repair_run.max_first_reinsertions
                    ),
                    "accepted_moves": [
                        {
                            "inserted_customer": move.inserted_customer,
                            "ejected_customers": list(
                                move.ejected_customers
                            ),
                            "reinsertion_order": list(
                                move.reinsertion_order
                            ),
                            "objective_before": move.objective_before,
                            "objective_after": move.objective_after,
                        }
                        for move in depth_two_repair_run.accepted_moves
                    ],
                    "evaluated_candidates": (
                        depth_two_repair_run.evaluated_candidates
                    ),
                    "incomplete_candidates": (
                        depth_two_repair_run.incomplete_candidates
                    ),
                }
                if depth_two_repair_run is not None
                else None
            ),
            "vnd": _vnd_result_metadata(vnd_run),
            "vns": _vns_result_metadata(vns_run),
            "source_files": {
                name: Path(path).name
                for name, path in adapter_result.source_files.items()
            },
            "single_trip_per_vehicle_requested": (
                construction_run.single_trip_per_vehicle
            ),
            "single_trip_per_vehicle": single_trip_per_vehicle,
            "charging_is_solver_compatible": (
                charging_is_solver_compatible
            ),
            "route_structure_compatible": (
                solver_structure_compatible
            ),
            "customer_set_complete": (
                not adapter_result.excluded_customers
            ),
            "requires_solver_importer_validation": True,
            "warnings": list(adapter_result.warnings),
        },
        "objective": {
            "value": evaluation.objective,
            "weights": {
                "risk": adapter_result.instance.weights.risk,
                "cost": adapter_result.instance.weights.cost,
                "time": adapter_result.instance.weights.time,
            },
            "scales": (
                {
                    "risk": objective_scales.risk,
                    "cost": objective_scales.cost,
                    "time": objective_scales.time,
                    "risk_active": objective_scales.risk_active,
                }
                if objective_scales is not None
                else None
            ),
        },
        "metrics": {
            "total_risk": evaluation.total_risk,
            "total_cost": evaluation.total_cost,
            "total_activation_cost": evaluation.total_activation_cost,
            "total_trip_cost": evaluation.total_trip_cost,
            "total_road_operating_cost": (
                evaluation.total_road_operating_cost
            ),
            "total_station_charging_cost": (
                evaluation.total_station_charging_cost
            ),
            "total_end_of_day_recharge_cost": (
                evaluation.total_end_of_day_recharge_cost
            ),
            "total_distance_km": evaluation.total_distance_km,
            "total_travel_minutes": evaluation.total_travel_minutes,
            "total_service_minutes": evaluation.total_service_minutes,
            "total_waiting_minutes": evaluation.total_waiting_minutes,
            "total_charging_minutes": evaluation.total_charging_minutes,
            "total_break_minutes": evaluation.total_break_minutes,
            "total_time_minutes": evaluation.total_time_minutes,
            "makespan_minute": evaluation.makespan_minute,
        },
        "runtime_seconds": {
            **runtimes,
            "total_algorithm": sum(runtimes.values()),
        },
        "schedule_details": _schedule_details(
            adapter_result,
            evaluation,
        ),
        "infeasibility_reasons": list(evaluation.reasons),
    }


def export_result_json(
    adapter_result: MatrixAdapterResult,
    evaluation: SolutionEvaluation,
    output_path: Path,
    *,
    construction_run: HeuristicRun,
    search_status: str,
    runtime_seconds: Mapping[str, float],
    objective_scales: Optional[ObjectiveScales] = None,
    repair_run: Optional[RepairRun] = None,
    depth_two_repair_run: Optional[DepthTwoRepairRun] = None,
    vnd_run: Optional[VNDRun] = None,
    vns_run: Optional[VNSRun] = None,
) -> Path:
    payload = build_result_payload(
        adapter_result,
        evaluation,
        construction_run=construction_run,
        search_status=search_status,
        runtime_seconds=runtime_seconds,
        objective_scales=objective_scales,
        repair_run=repair_run,
        depth_two_repair_run=depth_two_repair_run,
        vnd_run=vnd_run,
        vns_run=vns_run,
    )
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path


# Compatibility aliases for existing comparison scripts.
build_warm_start_payload = build_result_payload
export_warm_start_json = export_result_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the multi-customer heuristic with precomputed Small, "
            "Medium, or Large CSV data."
        )
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Directory containing one coherent matrix-based data set.",
    )
    parser.add_argument(
        "--vehicles-file",
        type=Path,
        default=None,
        help="Vehicle CSV; defaults to vehicles.csv in the parent data directory.",
    )
    parser.add_argument(
        "--instance-file",
        type=Path,
        default=None,
        help="Explicit instance CSV; otherwise a unique *instanz_*Timo.csv is used.",
    )
    parser.add_argument(
        "--od-matrix-file",
        type=Path,
        default=None,
        help=(
            "Explicit regular OD matrix CSV; otherwise the unique "
            "non-charger od_matrix_*.csv in --data-dir is used."
        ),
    )
    parser.add_argument(
        "--charger-matrix-file",
        type=Path,
        default=None,
        help=(
            "Explicit charger OD matrix CSV; otherwise the unique "
            "charger od_matrix_*.csv in --data-dir is used."
        ),
    )
    parser.add_argument(
        "--vehicle-hazard-compatibility-file",
        type=Path,
        default=None,
        help=(
            "Optional JSON object mapping every vehicle ID to its complete "
            "hazard-class capability list. Legal classes not used by the "
            "selected instance may remain in the list."
        ),
    )
    parser.add_argument(
        "--exclude-customer",
        action="append",
        default=[],
        help="Customer ID to exclude explicitly; may be repeated.",
    )
    parser.add_argument(
        "--risk-weight",
        type=float,
        default=0.5,
        help="Risk weight in the normalized heuristic objective.",
    )
    parser.add_argument(
        "--cost-weight",
        type=float,
        default=0.3,
        help="Cost weight in the normalized heuristic objective.",
    )
    parser.add_argument(
        "--time-weight",
        type=float,
        default=0.2,
        help="Operating-time weight in the normalized heuristic objective.",
    )
    parser.add_argument(
        "--construction-strategy",
        choices=CONSTRUCTION_STRATEGIES,
        default="best_insertion",
        help=(
            "New-trip seed rule used during sequential construction. "
            "regret_2 reserves vehicles for customers with few or costly "
            "vehicle alternatives; hardest_first starts with the largest "
            "best feasible time increment. Trip extension remains best "
            "insertion."
        ),
    )
    parser.add_argument(
        "--single-trip-per-vehicle",
        action="store_true",
        help=(
            "Enforce the current solver-compatible route structure: each "
            "physical vehicle may receive at most one depot-to-depot trip."
        ),
    )
    parser.add_argument(
        "--repair-evaluations",
        type=int,
        default=20_000,
        help="Maximum schedule evaluations in depth-one ejection repair.",
    )
    parser.add_argument(
        "--repair-seconds",
        type=float,
        default=300.0,
        help="Maximum depth-one ejection-repair runtime in seconds.",
    )
    parser.add_argument(
        "--vns-seconds",
        type=float,
        default=10.0,
        help="Maximum VNS runtime in seconds after construction and VND.",
    )
    parser.add_argument(
        "--vnd-passes",
        type=int,
        default=1_000,
        help="Maximum number of deterministic VND neighborhood passes.",
    )
    parser.add_argument(
        "--max-charging-branch-evaluations",
        type=int,
        default=100,
        help=(
            "Maximum charging-state branches per schedule evaluation. "
            "Use a larger value for Medium or Large diagnostics."
        ),
    )
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help=(
            "Optional path for a machine-readable heuristic result JSON. "
            "Infeasible runs write status and reasons with empty routes."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        adapter = build_matrix_adapter(
            args.data_dir,
            vehicles_file=args.vehicles_file,
            instance_file=args.instance_file,
            od_matrix_file=args.od_matrix_file,
            charger_matrix_file=args.charger_matrix_file,
            vehicle_hazard_compatibility_file=(
                args.vehicle_hazard_compatibility_file
            ),
            excluded_customers=args.exclude_customer,
            weights=ObjectiveWeights(
                risk=args.risk_weight,
                cost=args.cost_weight,
                time=args.time_weight,
            ),
            max_charging_branch_evaluations=(
                args.max_charging_branch_evaluations
            ),
        )
        construction = construct_initial_solution(
            adapter.instance,
            construction_strategy=args.construction_strategy,
            single_trip_per_vehicle=args.single_trip_per_vehicle,
        )
        repair = repair_partial_solution_depth_one(
            adapter.instance,
            construction,
            max_candidate_evaluations=args.repair_evaluations,
            max_seconds=args.repair_seconds,
            single_trip_per_vehicle=args.single_trip_per_vehicle,
        )
        vnd = improve_solution_vnd(
            adapter.instance,
            repair,
            max_neighborhood_passes=args.vnd_passes,
            single_trip_per_vehicle=args.single_trip_per_vehicle,
        )
        vns = improve_solution_vns(
            adapter.instance,
            vnd,
            random_seed=args.random_seed,
            max_seconds=args.vns_seconds,
            max_vnd_neighborhood_passes=args.vnd_passes,
            single_trip_per_vehicle=args.single_trip_per_vehicle,
        )
    except (InputDataError, ValueError) as error:
        raise SystemExit(f"Input error: {error}") from error

    print(summarize_adapter(adapter))
    print()
    print(f"construction_strategy={args.construction_strategy}")
    print(f"single_trip_per_vehicle={args.single_trip_per_vehicle}")
    print()
    print(summarize_run(construction))
    print()
    print(summarize_repair_run(repair))
    print()
    print(summarize_vnd_run(vnd))
    print()
    print(summarize_vns_run(vns))
    if args.output_json is not None:
        try:
            output_path = export_result_json(
                adapter,
                vns.evaluation,
                args.output_json,
                construction_run=construction,
                search_status=vns.status,
                runtime_seconds={
                    "construction": construction.runtime_seconds,
                    "repair": repair.runtime_seconds,
                    "vnd": vnd.runtime_seconds,
                    "vns": vns.runtime_seconds,
                },
                objective_scales=vns.scales,
                repair_run=repair,
                vnd_run=vnd,
                vns_run=vns,
            )
        except (OSError, ValueError) as error:
            raise SystemExit(
                f"Could not write result JSON: {error}"
            ) from error
        print()
        print(f"result_json={output_path}")
    if vns.evaluation.feasible:
        routes = build_heuristic_routes(adapter.instance, vns.evaluation)
        print()
        print("heuristic_routes = " + pformat(routes, sort_dicts=False))
    else:
        print()
        print("heuristic_routes not exported: final solution is infeasible.")


if __name__ == "__main__":
    main()
