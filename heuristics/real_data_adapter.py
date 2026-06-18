"""Real-data adapter for the HMVRP heuristic.

This module is the bridge between the team's data files and the heuristic
logic from the toy prototype. It does not solve paths yet. Its job is to load
and normalize the project data into objects that the real heuristic can use:

- mapped deliveries;
- electric-truck data;
- Germany-wide graph nodes and edges;
- first edge-level risk scores;
- mapped high-power charging stations;
- clear notes about still-missing permission data.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import mmap
from pathlib import Path
import pickle
import struct
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import numpy as np
    import pandas as pd
    from scipy.spatial import cKDTree
except ModuleNotFoundError as exc:  # pragma: no cover - user environment guard
    raise SystemExit(
        "Missing runtime dependency. Run this script with a Python environment "
        "that has pandas, numpy, and scipy installed."
    ) from exc


EARTH_RADIUS_M = 6_371_000.0
KASSEL_CITY_CENTER = (51.3127, 9.4797)
LITER_TO_KG_ASSUMPTION = 1.0
MIN_CHARGING_POWER_KW = 150.0
DEFAULT_ENERGY_PRICE_SCENARIO = "highway_hpc"

RISK_POPULATION_WEIGHT = 0.45
RISK_ACCIDENT_WEIGHT = 0.35
RISK_NATURE_WEIGHT = 0.20


@dataclass(frozen=True)
class MappedVehicle:
    vehicle_id: str
    capacity_kg: float
    range_km: float
    fixed_cost: float
    variable_cost_per_km: float
    energy_kwh_per_km: float
    charging_power_kw: float


@dataclass(frozen=True)
class MappedDelivery:
    delivery_id: str
    origin_name: str
    destination_name: str
    destination_latitude: float
    destination_longitude: float
    origin_node: int
    origin_distance_m: float
    destination_node: int
    destination_distance_m: float
    mapping_feasible: bool
    mapping_status: str
    mapping_infeasible_reason: str
    demand_kg: float
    quantity: float
    unit: str
    un_number: str
    hazard_class: str
    adr_tunnel_code: Optional[str]


@dataclass(frozen=True)
class AdapterResult:
    data_dir: Path
    origin_node: int
    origin_distance_m: float
    origin_mapping_feasible: bool
    max_mapping_distance_m: float
    node_table: pd.DataFrame
    vehicles: List[MappedVehicle]
    deliveries: List[MappedDelivery]
    edge_table: pd.DataFrame
    charging_stations: pd.DataFrame
    edge_permission_ready: bool
    energy_price_scenario: str
    energy_price_eur_per_kwh: float
    risk_metadata: Dict[str, object]
    notes: List[str]
    warnings: List[str]


def validate_data_dir(data_dir: Path) -> Path:
    resolved = data_dir.expanduser().resolve()
    required = [
        "all_data.pkl",
        "germany_graph_with_population.pkl",
    ]
    missing = [name for name in required if not (resolved / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Data directory {resolved} is missing required files: {missing}."
        )
    return resolved


def load_pickle(path: Path) -> Any:
    try:
        with path.open("rb") as file:
            return pickle.load(file)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"Could not read {path.name}. Missing Python module: {exc.name}. "
            "Use the Python environment with pandas, numpy, scipy, pyarrow, "
            "and any geospatial modules needed by that file."
        ) from exc


def load_optional_pickle(path: Path, warnings: List[str]) -> Optional[Any]:
    if not path.exists():
        warnings.append(f"Optional file not found: {path.name}.")
        return None
    try:
        return load_pickle(path)
    except RuntimeError as exc:
        warnings.append(str(exc))
        return None


def latlon_to_xyz(latitudes: Iterable[float], longitudes: Iterable[float]) -> np.ndarray:
    lat = np.radians(np.asarray(latitudes, dtype=float))
    lon = np.radians(np.asarray(longitudes, dtype=float))
    return np.column_stack(
        (
            np.cos(lat) * np.cos(lon),
            np.cos(lat) * np.sin(lon),
            np.sin(lat),
        )
    )


def chord_to_meters(chord_distance: np.ndarray) -> np.ndarray:
    return 2 * EARTH_RADIUS_M * np.arcsin(np.clip(chord_distance / 2, 0, 1))


def build_node_lookup(nodes: pd.DataFrame) -> Tuple[cKDTree, pd.DataFrame]:
    required_columns = {"node", "lat", "lon"}
    if not required_columns.issubset(nodes.columns):
        raise ValueError(f"Node table must contain columns {sorted(required_columns)}.")
    node_coordinates = latlon_to_xyz(nodes["lat"].to_numpy(), nodes["lon"].to_numpy())
    return cKDTree(node_coordinates), nodes.reset_index(drop=True)


def nearest_node(
    tree: cKDTree,
    nodes: pd.DataFrame,
    latitude: float,
    longitude: float,
) -> Tuple[int, float, float, float]:
    query_point = latlon_to_xyz([latitude], [longitude])
    chord_distance, index = tree.query(query_point, k=1)
    distance_m = float(chord_to_meters(np.asarray(chord_distance))[0])
    node_row = nodes.iloc[int(index[0])]
    return (
        int(node_row["node"]),
        float(node_row["lat"]),
        float(node_row["lon"]),
        distance_m,
    )


def parse_un_number(value: Any) -> Optional[int]:
    digits = "".join(char for char in str(value) if char.isdigit())
    return int(digits) if digits else None


def demand_to_kg(quantity: float, unit: str) -> float:
    normalized_unit = str(unit).strip().lower()
    if normalized_unit == "kg":
        return float(quantity)
    if normalized_unit == "liter":
        return float(quantity) * LITER_TO_KG_ASSUMPTION
    raise ValueError(f"Unsupported delivery quantity unit: {unit}")


def parse_decimal_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    )


def robust_normalized(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0).clip(lower=0.0)
    upper = values.quantile(0.99)
    if not np.isfinite(upper) or upper <= 0:
        return pd.Series(0.0, index=series.index)
    return values.clip(upper=upper) / upper


def max_normalized(series: pd.Series) -> Tuple[pd.Series, float]:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0).clip(lower=0.0)
    maximum = float(values.max()) if not values.empty else 0.0
    if not np.isfinite(maximum) or maximum <= 0:
        return pd.Series(0.0, index=series.index), 0.0
    return values / maximum, maximum


def existing_columns(table: pd.DataFrame, candidates: List[str]) -> List[str]:
    return [column for column in candidates if column in table.columns]


def map_vehicles(vehicles_table: pd.DataFrame) -> List[MappedVehicle]:
    vehicles: List[MappedVehicle] = []
    for _, row in vehicles_table.iterrows():
        vehicles.append(
            MappedVehicle(
                vehicle_id=str(row["type"]),
                capacity_kg=float(row["capacity_kg"]),
                range_km=float(row["range_km"]),
                fixed_cost=float(row["fixed_cost"]),
                variable_cost_per_km=float(row["variable_cost_per_km"]),
                energy_kwh_per_km=float(row["energy_kwh_per_km"]),
                charging_power_kw=float(row.get("charging_power_kw", 0.0)),
            )
        )
    return vehicles


def select_energy_price(
    energy_prices: pd.DataFrame,
    scenario: str = DEFAULT_ENERGY_PRICE_SCENARIO,
) -> float:
    match = energy_prices[energy_prices["scenario"] == scenario]
    if match.empty:
        raise ValueError(f"Energy-price scenario is not available: {scenario}")
    return float(match.iloc[0]["price_eur_per_kwh"])


def build_adr_lookup(adr_table: pd.DataFrame) -> Dict[int, Optional[str]]:
    lookup: Dict[int, Optional[str]] = {}
    for _, row in adr_table.iterrows():
        un_number = parse_un_number(row["S_UNNR"])
        if un_number is not None and un_number not in lookup:
            tunnel_code = row.get("S_TUNNEL_CODE")
            lookup[un_number] = None if str(tunnel_code) == "nan" else str(tunnel_code)
    return lookup


def map_deliveries(
    delivery_table: pd.DataFrame,
    adr_lookup: Dict[int, Optional[str]],
    tree: cKDTree,
    nodes: pd.DataFrame,
    origin_node: int,
    origin_distance_m: float,
    max_mapping_distance_m: float,
) -> List[MappedDelivery]:
    deliveries: List[MappedDelivery] = []
    for _, row in delivery_table.iterrows():
        destination_node, _, _, destination_distance = nearest_node(
            tree,
            nodes,
            float(row["destination_latitude"]),
            float(row["destination_longitude"]),
        )
        un_int = parse_un_number(row["un_number"])
        tunnel_code = adr_lookup.get(un_int) if un_int is not None else None
        origin_mapping_feasible = origin_distance_m <= max_mapping_distance_m
        destination_mapping_feasible = destination_distance <= max_mapping_distance_m
        mapping_feasible = origin_mapping_feasible and destination_mapping_feasible
        mapping_reasons = []
        if not origin_mapping_feasible:
            mapping_reasons.append(
                f"origin distance {origin_distance_m:.2f} m exceeds "
                f"{max_mapping_distance_m:.2f} m"
            )
        if not destination_mapping_feasible:
            mapping_reasons.append(
                f"destination distance {destination_distance:.2f} m exceeds "
                f"{max_mapping_distance_m:.2f} m"
            )
        deliveries.append(
            MappedDelivery(
                delivery_id=f"delivery_{int(row['customer_id'])}",
                origin_name=str(row["origin"]),
                destination_name=str(row["destination_name"]),
                destination_latitude=float(row["destination_latitude"]),
                destination_longitude=float(row["destination_longitude"]),
                origin_node=origin_node,
                origin_distance_m=round(origin_distance_m, 2),
                destination_node=destination_node,
                destination_distance_m=round(destination_distance, 2),
                mapping_feasible=mapping_feasible,
                mapping_status="mapped" if mapping_feasible else "mapping_infeasible",
                mapping_infeasible_reason="; ".join(mapping_reasons),
                demand_kg=demand_to_kg(float(row["quantity"]), str(row["unit"])),
                quantity=float(row["quantity"]),
                unit=str(row["unit"]),
                un_number=str(row["un_number"]),
                hazard_class=str(row["danger_class"]),
                adr_tunnel_code=tunnel_code,
            )
        )
    return deliveries


def merge_edge_feature(
    edge_table: pd.DataFrame,
    feature_table: pd.DataFrame,
    feature_columns: List[str],
) -> pd.DataFrame:
    keys = ["arc_id", "u", "v"] if "arc_id" in feature_table.columns else ["u", "v"]
    available_columns = keys + existing_columns(feature_table, feature_columns)
    if len(available_columns) == len(keys):
        return edge_table
    return edge_table.merge(
        feature_table[available_columns].drop_duplicates(subset=keys),
        on=keys,
        how="left",
    )


def read_pickle_unicode(
    memory_map: mmap.mmap,
    position: int,
    opcode: int,
) -> Tuple[str, int]:
    if opcode == 0x8C:  # SHORT_BINUNICODE
        length = memory_map[position + 1]
        start = position + 2
        return (
            memory_map[start : start + length].decode("utf-8", errors="replace"),
            start + length,
        )
    if opcode == 0x58:  # BINUNICODE
        length = struct.unpack_from("<I", memory_map, position + 1)[0]
        start = position + 5
        return (
            memory_map[start : start + length].decode("utf-8", errors="replace"),
            start + length,
        )
    if opcode == 0x8D:  # BINUNICODE8
        length = struct.unpack_from("<Q", memory_map, position + 1)[0]
        start = position + 9
        return (
            memory_map[start : start + length].decode("utf-8", errors="replace"),
            start + length,
        )
    raise ValueError(f"Unsupported unicode pickle opcode: {opcode}")


def find_pickle_short_unicode_key(path: Path, key: str) -> Optional[int]:
    key_bytes = key.encode("utf-8")
    if len(key_bytes) > 255:
        raise ValueError("Only short pickle unicode keys are supported.")
    pattern = bytes([0x8C, len(key_bytes)]) + key_bytes
    with path.open("rb") as file:
        memory_map = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            position = memory_map.find(pattern)
        finally:
            memory_map.close()
    return None if position == -1 else position


def extract_tunnel_values(
    data_dir: Path,
    edge_count: int,
    warnings: List[str],
) -> Optional[pd.Series]:
    tunnel_graph_path = data_dir / "germany_graph_geo_tun.pkl"
    if not tunnel_graph_path.exists():
        warnings.append("Tunnel-enabled Germany graph was not found.")
        return None

    start_position = find_pickle_short_unicode_key(tunnel_graph_path, "tunnel")
    if start_position is None:
        warnings.append("Tunnel-enabled Germany graph has no pickle key named tunnel.")
        return None

    values: List[Optional[str]] = [None] * edge_count
    entries = 0
    max_key = -1

    with tunnel_graph_path.open("rb") as file:
        memory_map = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            position = start_position
            local_memo: Dict[int, Any] = {}
            next_local_memo_id = 0
            base_memo_id: Optional[int] = None
            last_memoized_local_id: Optional[int] = None
            last_object: Any = None
            current_key: Optional[int] = None

            while entries < edge_count and position < len(memory_map):
                opcode = memory_map[position]

                if opcode == 0x95:  # FRAME
                    position += 9
                    continue
                if opcode in (0x8C, 0x58, 0x8D):
                    value, position = read_pickle_unicode(memory_map, position, opcode)
                    last_object = value
                    if current_key is not None:
                        if 0 <= current_key < edge_count:
                            values[current_key] = value
                        max_key = max(max_key, current_key)
                        entries += 1
                        current_key = None
                    continue
                if opcode == 0x94:  # MEMOIZE
                    local_memo[next_local_memo_id] = last_object
                    last_memoized_local_id = next_local_memo_id
                    next_local_memo_id += 1
                    position += 1
                    continue
                if opcode in (0x7D, 0x28, 0x75):  # EMPTY_DICT, MARK, SETITEMS
                    position += 1
                    continue
                if opcode == 0x2E:  # STOP
                    break
                if opcode == 0x4B:  # BININT1
                    current_key = memory_map[position + 1]
                    last_object = current_key
                    position += 2
                    continue
                if opcode == 0x4D:  # BININT2
                    current_key = struct.unpack_from("<H", memory_map, position + 1)[0]
                    last_object = current_key
                    position += 3
                    continue
                if opcode == 0x4A:  # BININT
                    current_key = struct.unpack_from("<i", memory_map, position + 1)[0]
                    last_object = current_key
                    position += 5
                    continue
                if opcode == 0x6A:  # LONG_BINGET
                    memo_id = struct.unpack_from("<I", memory_map, position + 1)[0]
                    if base_memo_id is None and last_memoized_local_id is not None:
                        base_memo_id = memo_id - last_memoized_local_id
                    local_id = memo_id - base_memo_id if base_memo_id is not None else memo_id
                    value = local_memo.get(local_id)
                    last_object = value
                    if current_key is not None:
                        if 0 <= current_key < edge_count:
                            values[current_key] = str(value)
                        max_key = max(max_key, current_key)
                        entries += 1
                        current_key = None
                    position += 5
                    continue
                if opcode == 0x68:  # BINGET
                    memo_id = memory_map[position + 1]
                    value = local_memo.get(memo_id)
                    last_object = value
                    if current_key is not None:
                        if 0 <= current_key < edge_count:
                            values[current_key] = str(value)
                        max_key = max(max_key, current_key)
                        entries += 1
                        current_key = None
                    position += 2
                    continue
                if opcode in (0x4E, 0x88, 0x89):  # NONE, NEWTRUE, NEWFALSE
                    value = None if opcode == 0x4E else opcode == 0x88
                    last_object = value
                    if current_key is not None:
                        if 0 <= current_key < edge_count:
                            values[current_key] = str(value)
                        max_key = max(max_key, current_key)
                        entries += 1
                        current_key = None
                    position += 1
                    continue

                warnings.append(
                    f"Tunnel parser stopped at unsupported pickle opcode {opcode}."
                )
                break
        finally:
            memory_map.close()

    if entries < edge_count:
        warnings.append(
            f"Tunnel parser returned {entries:,} entries for {edge_count:,} edges."
        )
        return None
    if max_key != edge_count - 1:
        warnings.append(
            f"Tunnel parser max key is {max_key:,}, expected {edge_count - 1:,}."
        )
        return None

    return pd.Series(values, name="tunnel").fillna("unknown")


def attach_tunnel_information(
    edge_table: pd.DataFrame,
    data_dir: Path,
    warnings: List[str],
) -> pd.DataFrame:
    tunnel_values = extract_tunnel_values(data_dir, len(edge_table), warnings)
    if tunnel_values is None:
        return edge_table

    arc_ids = edge_table["arc_id"].to_numpy(dtype=np.int64, copy=False)
    expected_arc_ids = np.arange(len(edge_table), dtype=np.int64)
    if np.array_equal(arc_ids, expected_arc_ids):
        edge_table["tunnel"] = tunnel_values.to_numpy()
    else:
        tunnel_table = pd.DataFrame(
            {
                "arc_id": expected_arc_ids,
                "tunnel": tunnel_values.to_numpy(),
            }
        )
        edge_table = edge_table.merge(tunnel_table, on="arc_id", how="left")

    normalized_tunnel = edge_table["tunnel"].astype(str).str.lower()
    edge_table["is_tunnel_edge"] = ~normalized_tunnel.isin(["no", "nan", "none", ""])
    return edge_table


def attach_accident_rate(
    edge_table: pd.DataFrame,
    accident_edges: pd.DataFrame,
) -> Tuple[pd.DataFrame, str, str]:
    if "acc_rate" in accident_edges.columns:
        source_field = "acc_rate"
        transformation = "direct rate"
    elif "accidents" in accident_edges.columns:
        source_field = "accidents"
        transformation = "accidents / length_km"
    elif "weighted_score" in accident_edges.columns:
        source_field = "weighted_score"
        transformation = "direct rate (verified weighted_accidents / length)"
    elif "score" in accident_edges.columns:
        source_field = "score"
        transformation = "direct rate (verified accidents / length)"
    elif "accident_score" in accident_edges.columns:
        raise ValueError(
            "The accident graph only contains accident_score, whose rate/total "
            "semantics are not defined. Provide an explicit accident-rate field."
        )
    else:
        raise ValueError("The accident graph has no supported accident-rate field.")

    edge_table = merge_edge_feature(edge_table, accident_edges, [source_field])
    source_values = pd.to_numeric(
        edge_table[source_field],
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    if source_field == "accidents":
        lengths = edge_table["length_km"].to_numpy(dtype=float, copy=False)
        accident_values = source_values.to_numpy(dtype=float, copy=False)
        accident_rate = np.divide(
            accident_values,
            lengths,
            out=np.zeros(len(edge_table), dtype=float),
            where=lengths > 0,
        )
        edge_table["accident_rate"] = accident_rate
    else:
        edge_table["accident_rate"] = source_values
    return edge_table, source_field, transformation


def load_edge_table(
    data_dir: Path,
    germany_population: Dict[str, pd.DataFrame],
    warnings: List[str],
) -> Tuple[pd.DataFrame, bool, Dict[str, object]]:
    population_edges = germany_population["edges"]
    base_columns = existing_columns(
        population_edges,
        ["arc_id", "u", "v", "distance_m", "length_m", "population", "pop_per_meter"],
    )
    edge_table = population_edges[base_columns].copy()
    if "length_m" not in edge_table.columns and "distance_m" in edge_table.columns:
        edge_table["length_m"] = edge_table["distance_m"]
    edge_table["length_km"] = pd.to_numeric(
        edge_table["length_m"],
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0) / 1000.0

    germany_nature = load_optional_pickle(data_dir / "germany_graph_with_nature.pkl", warnings)
    if germany_nature is not None and "edges" in germany_nature:
        edge_table = merge_edge_feature(
            edge_table,
            germany_nature["edges"],
            [
                "highway",
                "name",
                "intersects_nature",
                "reserve_count",
                "in_nature_ratio",
                "dist_to_nature_m",
                "nature_score",
            ],
        )
    else:
        edge_table["nature_score"] = 0.0
        warnings.append("Nature edge scores are not available; nature risk is set to 0.")

    germany_accidents = load_optional_pickle(
        data_dir / "germany_graph_with_accidents.pkl",
        warnings,
    )
    if germany_accidents is not None and "edges" in germany_accidents:
        accident_edges = germany_accidents["edges"]
        edge_table, accident_source_field, accident_transformation = attach_accident_rate(
            edge_table,
            accident_edges,
        )
    else:
        edge_table["accident_rate"] = 0.0
        accident_source_field = "none"
        accident_transformation = "missing accident data; rate set to 0"
        warnings.append("Accident risk is set to 0 because the accident graph is unavailable.")

    if "nature_score" not in edge_table.columns:
        edge_table["nature_score"] = 0.0

    population_rate = pd.to_numeric(
        edge_table["pop_per_meter"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    nature_rate = pd.to_numeric(
        edge_table["nature_score"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    edge_table["population_rate_norm"], population_rate_max = max_normalized(
        population_rate
    )
    edge_table["accident_rate_norm"], accident_rate_max = max_normalized(
        edge_table["accident_rate"]
    )
    edge_table["nature_rate_norm"], nature_rate_max = max_normalized(nature_rate)
    edge_table["risk_rate_per_km"] = (
        RISK_POPULATION_WEIGHT * edge_table["population_rate_norm"]
        + RISK_ACCIDENT_WEIGHT * edge_table["accident_rate_norm"]
        + RISK_NATURE_WEIGHT * edge_table["nature_rate_norm"]
    )
    edge_table["risk_score"] = edge_table["risk_rate_per_km"] * edge_table["length_km"]
    risk_metadata: Dict[str, object] = {
        "accident_source_field": accident_source_field,
        "accident_transformation": accident_transformation,
        "population_rate_max": population_rate_max,
        "accident_rate_max": accident_rate_max,
        "nature_rate_max": nature_rate_max,
    }

    edge_table = attach_tunnel_information(edge_table, data_dir, warnings)
    edge_permission_ready = "tunnel" in edge_table.columns
    if not edge_permission_ready:
        warnings.append(
            "Germany edge table has no tunnel column in the default loaded files. "
            "ADR tunnel-code filtering is prepared at delivery level, but edge-level "
            "forbidden-edge filtering still needs the tunnel-enabled Germany graph."
        )

    return edge_table, edge_permission_ready, risk_metadata


def empty_charging_station_table() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "station_id",
            "node",
            "latitude",
            "longitude",
            "power_kw",
            "charge_points",
            "city",
            "distance_m",
        ]
    )


def map_charging_stations(
    charging_table: pd.DataFrame,
    tree: cKDTree,
    nodes: pd.DataFrame,
    min_power_kw: float = MIN_CHARGING_POWER_KW,
) -> pd.DataFrame:
    required = {
        "Ladeeinrichtungs-ID",
        "Nennleistung Ladeeinrichtung [kW]",
        "Anzahl Ladepunkte",
        "Breitengrad",
        "Längengrad",
    }
    if not required.issubset(charging_table.columns):
        return empty_charging_station_table()

    charging = charging_table.copy()
    charging["latitude"] = parse_decimal_series(charging["Breitengrad"])
    charging["longitude"] = parse_decimal_series(charging["Längengrad"])
    charging["power_kw"] = pd.to_numeric(
        charging["Nennleistung Ladeeinrichtung [kW]"],
        errors="coerce",
    )
    charging["charge_points"] = pd.to_numeric(
        charging["Anzahl Ladepunkte"],
        errors="coerce",
    ).fillna(0).astype(int)
    charging = charging.dropna(subset=["latitude", "longitude", "power_kw"])
    charging = charging[charging["power_kw"] >= min_power_kw].reset_index(drop=True)
    if charging.empty:
        return empty_charging_station_table()

    query_points = latlon_to_xyz(
        charging["latitude"].to_numpy(),
        charging["longitude"].to_numpy(),
    )
    chord_distance, indices = tree.query(query_points, k=1)
    matched_nodes = nodes.iloc[np.asarray(indices, dtype=int)].reset_index(drop=True)

    result = pd.DataFrame(
        {
            "station_id": charging["Ladeeinrichtungs-ID"].astype(str).to_numpy(),
            "node": matched_nodes["node"].astype(int).to_numpy(),
            "latitude": charging["latitude"].to_numpy(),
            "longitude": charging["longitude"].to_numpy(),
            "power_kw": charging["power_kw"].to_numpy(),
            "charge_points": charging["charge_points"].to_numpy(),
            "city": charging.get("Ort", pd.Series("", index=charging.index)).astype(str).to_numpy(),
            "distance_m": chord_to_meters(np.asarray(chord_distance)),
        }
    )
    return result


def capacity_feasibility_preview(
    deliveries: List[MappedDelivery],
    vehicles: List[MappedVehicle],
) -> Dict[str, List[str]]:
    feasible: Dict[str, List[str]] = {}
    for delivery in deliveries:
        feasible[delivery.delivery_id] = [
            vehicle.vehicle_id
            for vehicle in vehicles
            if delivery.demand_kg <= vehicle.capacity_kg
        ]
    return feasible


def build_adapter_result(
    data_dir: Path,
    max_mapping_distance_m: float = 1000.0,
) -> AdapterResult:
    if max_mapping_distance_m <= 0:
        raise ValueError("max_mapping_distance_m must be positive.")
    resolved_data_dir = validate_data_dir(data_dir)
    warnings: List[str] = []
    all_data = load_pickle(resolved_data_dir / "all_data.pkl")
    germany_population = load_pickle(resolved_data_dir / "germany_graph_with_population.pkl")

    tree, nodes = build_node_lookup(germany_population["nodes"])
    origin_node, _, _, origin_distance = nearest_node(
        tree,
        nodes,
        KASSEL_CITY_CENTER[0],
        KASSEL_CITY_CENTER[1],
    )

    vehicles = map_vehicles(all_data["vehicles"])
    energy_price = select_energy_price(all_data["energy_prices"])
    adr_lookup = build_adr_lookup(all_data["ADR_dataset"])
    deliveries = map_deliveries(
        all_data["delivery_routes"],
        adr_lookup,
        tree,
        nodes,
        origin_node,
        origin_distance,
        max_mapping_distance_m,
    )
    edge_table, edge_permission_ready, risk_metadata = load_edge_table(
        resolved_data_dir,
        germany_population,
        warnings,
    )
    charging_stations = map_charging_stations(
        all_data["charging_infrastructure"],
        tree,
        nodes,
    )

    notes = [
        "Kassel origin uses a temporary city-center coordinate.",
        "Liter quantities use a first-version 1 liter = 1 kg conversion.",
        "Germany population graph nodes are used for nearest-node mapping because deliveries are Germany-wide.",
        "Edge risk score currently combines population and nature data; accident data is added only if the graph is readable in the local environment.",
        f"Charging stations are filtered to >= {MIN_CHARGING_POWER_KW:.0f} kW and mapped to nearest graph nodes for later EV routing.",
    ]
    return AdapterResult(
        data_dir=resolved_data_dir,
        origin_node=origin_node,
        origin_distance_m=round(origin_distance, 2),
        origin_mapping_feasible=origin_distance <= max_mapping_distance_m,
        max_mapping_distance_m=float(max_mapping_distance_m),
        node_table=nodes[["node", "lat", "lon"]].copy(),
        vehicles=vehicles,
        deliveries=deliveries,
        edge_table=edge_table,
        charging_stations=charging_stations,
        edge_permission_ready=edge_permission_ready,
        energy_price_scenario=DEFAULT_ENERGY_PRICE_SCENARIO,
        energy_price_eur_per_kwh=energy_price,
        risk_metadata=risk_metadata,
        notes=notes,
        warnings=warnings,
    )


def summarize(result: AdapterResult) -> str:
    max_destination_distance = max(
        delivery.destination_distance_m for delivery in result.deliveries
    )
    total_demand = sum(delivery.demand_kg for delivery in result.deliveries)
    edge_table = result.edge_table
    charging_stations = result.charging_stations
    capacity_preview = capacity_feasibility_preview(result.deliveries, result.vehicles)
    capacity_infeasible = [
        delivery_id
        for delivery_id, vehicle_ids in capacity_preview.items()
        if not vehicle_ids
    ]
    tunnel_counts = (
        edge_table["tunnel"].value_counts().head(8).to_dict()
        if "tunnel" in edge_table.columns
        else {}
    )
    tunnel_edge_count = (
        int(edge_table["is_tunnel_edge"].sum())
        if "is_tunnel_edge" in edge_table.columns
        else 0
    )

    lines = [
        "Real-data adapter summary",
        "-" * 30,
        f"data_dir={result.data_dir}",
        f"origin=Kassel, origin_node={result.origin_node}, nearest_distance_m={result.origin_distance_m:.2f}",
        f"origin_mapping_feasible={result.origin_mapping_feasible}",
        f"max_mapping_distance_m={result.max_mapping_distance_m:.2f}",
        f"energy_price_scenario={result.energy_price_scenario}",
        f"energy_price_eur_per_kwh={result.energy_price_eur_per_kwh:.2f}",
        f"vehicles={len(result.vehicles)}",
        f"deliveries={len(result.deliveries)}",
        f"total_delivery_demand_kg={total_demand:.1f}",
        f"max_destination_node_distance_m={max_destination_distance:.2f}",
        f"edges={len(edge_table):,}",
        f"edge_columns={list(edge_table.columns)}",
        f"edge_permission_ready={result.edge_permission_ready}",
        f"tunnel_edges={tunnel_edge_count:,}",
        f"tunnel_value_counts={tunnel_counts}",
        f"high_power_charging_stations={len(charging_stations):,}",
        f"charging_nodes={charging_stations['node'].nunique() if not charging_stations.empty else 0:,}",
        f"capacity_infeasible_deliveries={capacity_infeasible}",
        f"risk_metadata={result.risk_metadata}",
        "",
        "Risk score preview:",
        f"- min={edge_table['risk_score'].min():.6f}",
        f"- mean={edge_table['risk_score'].mean():.6f}",
        f"- max={edge_table['risk_score'].max():.6f}",
        "",
        "Vehicles:",
    ]
    for vehicle in result.vehicles:
        lines.append(
            f"- {vehicle.vehicle_id}: capacity={vehicle.capacity_kg:.0f} kg, "
            f"range={vehicle.range_km:.0f} km, charging_power={vehicle.charging_power_kw:.0f} kW"
        )

    lines.extend(["", "Deliveries:"])
    for delivery in result.deliveries:
        feasible_vehicles = ", ".join(capacity_preview[delivery.delivery_id]) or "none"
        lines.append(
            f"- {delivery.delivery_id}: {delivery.origin_name} -> {delivery.destination_name}, "
            f"node {delivery.origin_node} -> {delivery.destination_node}, "
            f"demand={delivery.demand_kg:.1f} kg, class={delivery.hazard_class}, "
            f"{delivery.un_number}, tunnel_code={delivery.adr_tunnel_code}, "
            f"mapping_status={delivery.mapping_status}, "
            f"capacity_feasible_vehicles=[{feasible_vehicles}], "
            f"dest_match={delivery.destination_distance_m:.2f} m"
        )

    if not charging_stations.empty:
        lines.extend(["", "Charging preview:"])
        lines.append(
            f"- max_power_kw={charging_stations['power_kw'].max():.1f}, "
            f"max_node_match_distance_m={charging_stations['distance_m'].max():.2f}"
        )

    lines.extend(["", "Notes:"])
    for note in result.notes:
        lines.append(f"- {note}")

    if result.warnings:
        lines.extend(["", "Warnings:"])
        for warning in result.warnings:
            lines.append(f"- {warning}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load real project data for the heuristic.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Directory containing the agreed project data files.",
    )
    parser.add_argument(
        "--max-mapping-distance-m",
        type=float,
        default=1000.0,
        help="Maximum coordinate-to-network mapping distance for origins and destinations.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_adapter_result(
        args.data_dir,
        max_mapping_distance_m=args.max_mapping_distance_m,
    )
    text = summarize(result)
    output_encoding = sys.stdout.encoding or "utf-8"
    safe_text = text.encode(output_encoding, errors="replace").decode(output_encoding)
    print(safe_text)


if __name__ == "__main__":
    main()
