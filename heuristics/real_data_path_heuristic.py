"""Real-data path heuristic for independent one-way OD deliveries.

The baseline generates distance, risk, and weighted path candidates, applies
road and tunnel restrictions, and assigns a feasible electric truck to each
selected candidate. Deliveries are independent one-way tasks: payload capacity
is released after unloading, while execution order and repositioning between
deliveries are outside the current scope.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import html
import json
import pickle
from pathlib import Path
import sys
import time
from typing import Dict, Iterable, List, Optional, Tuple

MODULE_START_SECONDS = time.perf_counter()

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

try:
    from real_data_adapter import (
        AdapterResult,
        DEFAULT_REGION,
        MappedDelivery,
        MappedVehicle,
        SUPPORTED_REGIONS,
        build_adapter_result,
        chord_to_meters,
        latlon_to_xyz,
    )
except ModuleNotFoundError:  # pragma: no cover - module execution fallback
    from heuristics.real_data_adapter import (
        AdapterResult,
        DEFAULT_REGION,
        MappedDelivery,
        MappedVehicle,
        SUPPORTED_REGIONS,
        build_adapter_result,
        chord_to_meters,
        latlon_to_xyz,
    )


RISK_WEIGHT = 0.65
COST_WEIGHT = 0.35
WEIGHT_EPSILON = 1e-9
DESTINATION_MAPPING_CANDIDATES = 250
DEFAULT_NETWORK_MODE = "solver_cropped"
SUPPORTED_NETWORK_MODES = ("full", "solver_cropped")
SOLVER_CROP_BUFFER = 0.3
MAP_BACKGROUND_EDGE_LIMIT = 8_000
MAP_NATURE_BBOX_BUFFER_DEGREES = 0.05
MAP_NATURE_RESERVE_LIMIT = 250

HAZARD_CLASS_FACTORS = {
    "3": 1.0,
    "2 (TOC)": 0.8,
    "1.1D": 2.0,
    "8": 0.9,
    "9": 0.7,
    "6": 1.5,
    "2": 0.8,
}

TUNNEL_CATEGORY_MAPPING = {
    "no": "A",
    "": "A",
    "none": "A",
    "nan": "A",
    "building_passage": "B",
    "covered": "C",
    "yes": "D",
    "avalanche_protector": "D",
}

FORBIDDEN_CLASSES_BY_TUNNEL_CATEGORY = {
    "A": frozenset(),
    "B": frozenset(),
    "C": frozenset({"1.1D", "1.5D"}),
    "D": frozenset({"1.1D", "1.5D", "6", "9"}),
}


@dataclass(frozen=True)
class GraphContext:
    node_ids: np.ndarray
    node_to_index: Dict[int, int]


@dataclass(frozen=True)
class ResolvedMapping:
    target_node: Optional[int]
    distance_m: float
    feasible: bool
    status: str
    reason: str


@dataclass(frozen=True)
class PathCandidate:
    delivery_id: str
    destination_name: str
    demand_kg: float
    hazard_class: str
    hazard_class_factor: float
    label: str
    mapping_status: str
    mapping_feasible: bool
    path_found: bool
    legal_feasible: bool
    capacity_feasible: bool
    range_feasible_without_charging: bool
    feasible_vehicle_ids: Tuple[str, ...]
    vehicle_id: Optional[str]
    feasible: bool
    infeasible_reason: str
    path_length_km: float
    path_risk: float
    variable_cost: Optional[float]
    activation_cost: Optional[float]
    incremental_cost: Optional[float]
    assignment_score: Optional[float]
    edge_count: int
    tunnel_edges_used: int
    reverse_edges_used: int
    target_node: Optional[int]
    destination_match_distance_m: float
    arc_ids: Tuple[int, ...]
    node_path: Tuple[int, ...]
    edge_details: Tuple[Dict[str, object], ...]


@dataclass(frozen=True)
class HeuristicResult:
    candidates: List[PathCandidate]
    selected: List[PathCandidate]
    data_dir: Path
    region: str
    network_mode: str
    risk_weight: float
    cost_weight: float
    startup_seconds: float
    data_preparation_seconds: float
    network_preprocessing_seconds: float
    mapping_seconds: float
    candidate_generation_seconds: float
    vehicle_assignment_seconds: float
    export_seconds: float
    end_to_end_runtime_seconds: float
    runtime_seconds: float
    total_risk: float
    total_variable_cost: float
    total_fixed_cost: float
    total_cost: float
    feasible_deliveries: int
    infeasible_deliveries: int
    energy_price_scenario: str
    energy_price_eur_per_kwh: float
    active_vehicles: Tuple[str, ...]
    fixed_path_risk_scale: float
    fixed_cost_scale: float
    weighted_path_risk_scale: float
    weighted_path_length_scale: float
    max_mapping_distance_m: float
    risk_metadata: Dict[str, object]
    data_warnings: Tuple[str, ...]
    node_coordinates: Dict[int, Tuple[float, float]]
    map_background_edges: Tuple[Dict[str, object], ...]
    nature_reserve_polygons: Tuple[Dict[str, object], ...]


@dataclass(frozen=True)
class ScenarioRun:
    name: str
    result: HeuristicResult
    output_dir: Path


def build_destination_options(
    node_table: pd.DataFrame,
    deliveries: List[MappedDelivery],
    max_mapping_distance_m: float,
    k: int = DESTINATION_MAPPING_CANDIDATES,
) -> Dict[str, List[Tuple[int, float]]]:
    nodes = node_table.reset_index(drop=True)
    tree = cKDTree(latlon_to_xyz(nodes["lat"].to_numpy(), nodes["lon"].to_numpy()))
    query_count = min(k, len(nodes))

    options: Dict[str, List[Tuple[int, float]]] = {}
    for delivery in deliveries:
        query_point = latlon_to_xyz(
            [delivery.destination_latitude],
            [delivery.destination_longitude],
        )
        chord_distances, indices = tree.query(query_point, k=query_count)
        distances_m = np.ravel(chord_to_meters(np.ravel(chord_distances)))
        indices = np.ravel(indices)
        seen = set()
        delivery_options: List[Tuple[int, float]] = []
        for index, distance_m in zip(indices, distances_m):
            node = int(nodes.iloc[int(index)]["node"])
            if distance_m <= max_mapping_distance_m and node not in seen:
                delivery_options.append((node, float(distance_m)))
                seen.add(node)
        options[delivery.delivery_id] = delivery_options
    return options


def validate_objective_weights(risk_weight: float, cost_weight: float) -> None:
    if risk_weight < 0 or cost_weight < 0:
        raise ValueError("Risk and cost weights must be non-negative.")
    if not np.isclose(risk_weight + cost_weight, 1.0):
        raise ValueError("Risk and cost weights must sum to 1.0.")


def hazard_class_factor(hazard_class: str) -> float:
    return HAZARD_CLASS_FACTORS.get(str(hazard_class).strip(), 1.0)


def tunnel_category(tunnel_value: object) -> str:
    normalized = str(tunnel_value or "").strip().lower()
    return TUNNEL_CATEGORY_MAPPING.get(normalized, "A")


def tunnel_allowed(tunnel_value: object, hazard_class: str) -> bool:
    category = tunnel_category(tunnel_value)
    forbidden = FORBIDDEN_CLASSES_BY_TUNNEL_CATEGORY[category]
    return str(hazard_class).strip() not in forbidden


def apply_hazard_class_risk(
    routing_table: pd.DataFrame,
    hazard_class: str,
) -> pd.DataFrame:
    adjusted = routing_table.copy()
    factor = hazard_class_factor(hazard_class)
    if "risk_rate_per_km" in adjusted.columns:
        adjusted_rate = (
            pd.to_numeric(adjusted["risk_rate_per_km"], errors="coerce")
            .fillna(0.0)
            .clip(lower=0.0)
            .mul(factor)
            .clip(upper=1.0)
        )
        adjusted["risk_score"] = adjusted_rate
    else:
        adjusted["risk_score"] = (
            pd.to_numeric(adjusted["risk_score"], errors="coerce")
            .fillna(0.0)
            .clip(lower=0.0)
            .mul(factor)
        )
    adjusted["risk_weight"] = adjusted["risk_score"]
    return adjusted


def attach_oneway_information(edge_table: pd.DataFrame, data_dir: Path) -> pd.DataFrame:
    if "oneway" in edge_table.columns:
        return edge_table

    edge_csv = data_dir / "edges_germany_geo.csv"
    if not edge_csv.exists():
        raise FileNotFoundError(
            "The edge table has no oneway field and edges_germany_geo.csv was not found."
        )

    oneway_table = pd.read_csv(edge_csv, usecols=["arc_id", "oneway"])
    edge_table = edge_table.copy()
    if len(oneway_table) == len(edge_table) and np.array_equal(
        oneway_table["arc_id"].to_numpy(dtype=np.int64),
        edge_table["arc_id"].to_numpy(dtype=np.int64),
    ):
        edge_table["oneway"] = oneway_table["oneway"].astype(str).to_numpy()
        return edge_table
    return edge_table.merge(oneway_table, on="arc_id", how="left")


def prepare_metric_columns(edge_table: pd.DataFrame) -> pd.DataFrame:
    edge_table = edge_table.copy()
    edge_table["distance_weight"] = edge_table["length_km"].clip(lower=0.0)
    edge_table["risk_weight"] = edge_table["risk_score"].clip(lower=0.0)
    return edge_table


def add_weighted_search_cost(
    routing_table: pd.DataFrame,
    fixed_risk_scale: float,
    fixed_length_scale: float,
    risk_weight: float = RISK_WEIGHT,
    cost_weight: float = COST_WEIGHT,
) -> pd.DataFrame:
    if fixed_risk_scale <= 0 or fixed_length_scale <= 0:
        raise ValueError("Weighted-search scales must be positive.")
    validate_objective_weights(risk_weight, cost_weight)
    routing_table = routing_table.copy()
    routing_table["weighted_search_cost"] = (
        risk_weight * routing_table["risk_score"] / fixed_risk_scale
        + cost_weight * routing_table["length_km"] / fixed_length_scale
    )
    return routing_table


def build_routing_table(edge_table: pd.DataFrame) -> pd.DataFrame:
    edge_table = edge_table.copy()
    if "tunnel" not in edge_table.columns:
        edge_table["tunnel"] = "unknown"
    if "is_tunnel_edge" not in edge_table.columns:
        edge_table["is_tunnel_edge"] = False

    columns = [
        "arc_id",
        "u",
        "v",
        "oneway",
        "length_km",
        "risk_score",
        "tunnel",
        "is_tunnel_edge",
        "distance_weight",
        "risk_weight",
    ]
    if "risk_rate_per_km" in edge_table.columns:
        columns.append("risk_rate_per_km")
    for optional_column in [
        "base_risk_score",
        "population_rate_norm",
        "accident_rate_norm",
        "nature_rate_norm",
    ]:
        if optional_column in edge_table.columns:
            columns.append(optional_column)
    base = edge_table[columns].copy()
    base["tunnel_category"] = base["tunnel"].map(tunnel_category)
    oneway = base["oneway"].astype(str).str.strip().str.lower()
    bidirectional = oneway.isin(["no", "false", "0"])
    forward_only = oneway.isin(["yes", "true", "1"])
    reverse_only = oneway.eq("-1")

    forward = base.loc[bidirectional | forward_only].copy()
    forward["route_u"] = forward["u"]
    forward["route_v"] = forward["v"]
    forward["is_reverse"] = False

    reverse = base.loc[bidirectional | reverse_only].copy()
    reverse["route_u"] = reverse["v"]
    reverse["route_v"] = reverse["u"]
    reverse["is_reverse"] = True
    return pd.concat([forward, reverse], ignore_index=True)


def build_graph_context(routing_table: pd.DataFrame) -> GraphContext:
    from_nodes = routing_table["route_u"].to_numpy(dtype=np.int64, copy=False)
    to_nodes = routing_table["route_v"].to_numpy(dtype=np.int64, copy=False)
    node_ids = np.unique(np.concatenate((from_nodes, to_nodes)))
    return GraphContext(
        node_ids=node_ids,
        node_to_index={int(node): index for index, node in enumerate(node_ids)},
    )


def collapse_parallel_edges(
    routing_table: pd.DataFrame,
    metric_column: str,
    hazard_class: Optional[str],
) -> pd.DataFrame:
    eligible = routing_table
    if hazard_class is not None:
        forbidden = FORBIDDEN_CLASSES_BY_TUNNEL_CATEGORY.get(
            "D",
            frozenset(),
        )
        if str(hazard_class).strip() in forbidden:
            allowed_categories = [
                category
                for category, blocked_classes in FORBIDDEN_CLASSES_BY_TUNNEL_CATEGORY.items()
                if str(hazard_class).strip() not in blocked_classes
            ]
            eligible = eligible.loc[
                eligible["tunnel_category"].isin(allowed_categories)
            ]
    ordered = eligible.sort_values(
        [
            "route_u",
            "route_v",
            metric_column,
            "length_km",
            "arc_id",
            "is_reverse",
        ],
        kind="mergesort",
    )
    return ordered.drop_duplicates(["route_u", "route_v"], keep="first").reset_index(
        drop=True
    )


def build_sparse_graph(
    context: GraphContext,
    collapsed_edges: pd.DataFrame,
    metric_column: str,
) -> csr_matrix:
    rows = np.searchsorted(
        context.node_ids,
        collapsed_edges["route_u"].to_numpy(dtype=np.int64, copy=False),
    )
    columns = np.searchsorted(
        context.node_ids,
        collapsed_edges["route_v"].to_numpy(dtype=np.int64, copy=False),
    )
    weights = (
        collapsed_edges[metric_column].to_numpy(dtype=np.float64, copy=False)
        + WEIGHT_EPSILON
    )
    return csr_matrix(
        (weights, (rows, columns)),
        shape=(len(context.node_ids), len(context.node_ids)),
    )


def filter_largest_strong_component(routing_table: pd.DataFrame) -> pd.DataFrame:
    context = build_graph_context(routing_table)
    topology_edges = collapse_parallel_edges(
        routing_table,
        "distance_weight",
        hazard_class=None,
    )
    graph = build_sparse_graph(context, topology_edges, "distance_weight")
    component_count, labels = connected_components(
        graph,
        directed=True,
        connection="strong",
        return_labels=True,
    )
    if component_count <= 1:
        return routing_table
    largest_label = int(np.argmax(np.bincount(labels)))
    largest_nodes = context.node_ids[labels == largest_label]
    return routing_table.loc[
        routing_table["route_u"].isin(largest_nodes)
        & routing_table["route_v"].isin(largest_nodes)
    ].reset_index(drop=True)


def attach_route_coordinates(
    routing_table: pd.DataFrame,
    node_table: pd.DataFrame,
) -> pd.DataFrame:
    coordinates = node_table.drop_duplicates("node").set_index("node")
    result = routing_table.copy()
    for endpoint in ("route_u", "route_v"):
        result[f"{endpoint}_lat"] = result[endpoint].map(coordinates["lat"])
        result[f"{endpoint}_lon"] = result[endpoint].map(coordinates["lon"])
    return result


def crop_delivery_edges(
    routing_table: pd.DataFrame,
    origin_node: int,
    destination_node: int,
    node_table: pd.DataFrame,
    buffer: float = SOLVER_CROP_BUFFER,
) -> pd.DataFrame:
    coordinates = node_table.drop_duplicates("node").set_index("node")
    if origin_node not in coordinates.index or destination_node not in coordinates.index:
        return routing_table.iloc[0:0].copy()
    origin = coordinates.loc[origin_node]
    destination = coordinates.loc[destination_node]
    min_lat, max_lat = sorted((float(origin["lat"]), float(destination["lat"])))
    min_lon, max_lon = sorted((float(origin["lon"]), float(destination["lon"])))
    lat_buffer = max((max_lat - min_lat) * buffer, 0.02)
    lon_buffer = max((max_lon - min_lon) * buffer, 0.02)

    required = {
        "route_u_lat",
        "route_u_lon",
        "route_v_lat",
        "route_v_lon",
    }
    with_coordinates = routing_table
    if not required.issubset(with_coordinates.columns):
        with_coordinates = attach_route_coordinates(routing_table, node_table)
    coordinate_missing = with_coordinates[list(required)].isna().any(axis=1)
    u_inside = (
        with_coordinates["route_u_lat"].between(
            min_lat - lat_buffer,
            max_lat + lat_buffer,
        )
        & with_coordinates["route_u_lon"].between(
            min_lon - lon_buffer,
            max_lon + lon_buffer,
        )
    )
    v_inside = (
        with_coordinates["route_v_lat"].between(
            min_lat - lat_buffer,
            max_lat + lat_buffer,
        )
        & with_coordinates["route_v_lon"].between(
            min_lon - lon_buffer,
            max_lon + lon_buffer,
        )
    )
    return with_coordinates.loc[coordinate_missing | (u_inside & v_inside)].reset_index(
        drop=True
    )


def build_delivery_routing_tables(
    routing_table: pd.DataFrame,
    node_table: pd.DataFrame,
    deliveries: List[MappedDelivery],
    mappings: Dict[str, ResolvedMapping],
    network_mode: str,
) -> Dict[str, pd.DataFrame]:
    if network_mode not in SUPPORTED_NETWORK_MODES:
        raise ValueError(f"Unsupported network mode: {network_mode}")
    if network_mode == "full":
        return {delivery.delivery_id: routing_table for delivery in deliveries}

    with_coordinates = attach_route_coordinates(routing_table, node_table)
    tables: Dict[str, pd.DataFrame] = {}
    for delivery in deliveries:
        mapping = mappings[delivery.delivery_id]
        if not mapping.feasible or mapping.target_node is None:
            tables[delivery.delivery_id] = with_coordinates.iloc[0:0].copy()
            continue
        tables[delivery.delivery_id] = crop_delivery_edges(
            with_coordinates,
            delivery.origin_node,
            int(mapping.target_node),
            node_table,
        )
    return tables


def reconstruct_node_path(
    predecessors: np.ndarray,
    source_index: int,
    target_index: int,
    node_ids: np.ndarray,
) -> Tuple[int, ...]:
    if predecessors[target_index] < 0 and source_index != target_index:
        return tuple()
    indices = [target_index]
    current = target_index
    while current != source_index:
        current = int(predecessors[current])
        if current < 0:
            return tuple()
        indices.append(current)
    indices.reverse()
    return tuple(int(node_ids[index]) for index in indices)


def path_edges_from_nodes(
    collapsed_edges: pd.DataFrame,
    node_path: Tuple[int, ...],
) -> pd.DataFrame:
    if len(node_path) < 2:
        return pd.DataFrame()
    pairs = pd.DataFrame(
        {
            "step": np.arange(len(node_path) - 1, dtype=np.int32),
            "route_u": node_path[:-1],
            "route_v": node_path[1:],
        }
    )
    merged = pairs.merge(collapsed_edges, on=["route_u", "route_v"], how="left")
    if merged["arc_id"].isna().any():
        return pd.DataFrame()
    return merged.sort_values("step")


def edge_detail_records(path_edges: pd.DataFrame) -> Tuple[Dict[str, object], ...]:
    detail_columns = [
        "step",
        "arc_id",
        "route_u",
        "route_v",
        "length_km",
        "risk_score",
        "population_rate_norm",
        "accident_rate_norm",
        "nature_rate_norm",
        "base_risk_score",
        "is_tunnel_edge",
        "is_reverse",
    ]
    available = [column for column in detail_columns if column in path_edges.columns]
    records: List[Dict[str, object]] = []
    for _, row in path_edges[available].iterrows():
        record: Dict[str, object] = {}
        for column in available:
            value = row[column]
            if pd.isna(value):
                value = 0.0
            if column in {"step", "arc_id", "route_u", "route_v"}:
                record[column] = int(value)
            elif column in {"is_tunnel_edge", "is_reverse"}:
                record[column] = bool(value)
            else:
                record[column] = float(value)
        records.append(record)
    return tuple(records)


def map_background_edge_records(
    delivery_routing_tables: Dict[str, pd.DataFrame],
    node_coordinates: Dict[int, Tuple[float, float]],
    max_edges: int = MAP_BACKGROUND_EDGE_LIMIT,
) -> Tuple[Dict[str, object], ...]:
    tables = [table for table in delivery_routing_tables.values() if not table.empty]
    if not tables or max_edges <= 0:
        return tuple()

    background = pd.concat(tables, ignore_index=True)
    background = background.drop_duplicates(["route_u", "route_v", "arc_id"])
    metric_columns = [
        "population_rate_norm",
        "accident_rate_norm",
        "nature_rate_norm",
        "risk_score",
    ]
    for column in metric_columns:
        if column not in background.columns:
            background[column] = 0.0

    per_metric = max(1, max_edges // (len(metric_columns) + 1))
    samples = []
    for column in metric_columns:
        samples.append(
            background.nlargest(
                min(per_metric, len(background)),
                column,
                keep="first",
            )
        )
    samples.append(
        background.iloc[
            np.linspace(
                0,
                len(background) - 1,
                min(per_metric, len(background)),
                dtype=int,
            )
        ]
    )
    sampled = (
        pd.concat(samples, ignore_index=True)
        .drop_duplicates(["route_u", "route_v", "arc_id"])
        .head(max_edges)
    )

    records: List[Dict[str, object]] = []
    for _, row in sampled.iterrows():
        route_u = int(row["route_u"])
        route_v = int(row["route_v"])
        start = node_coordinates.get(route_u)
        end = node_coordinates.get(route_v)
        if start is None or end is None:
            continue
        start_lat, start_lon = start
        end_lat, end_lon = end
        records.append(
            {
                "route_u": route_u,
                "route_v": route_v,
                "arc_id": int(row["arc_id"]),
                "coordinates": [[start_lon, start_lat], [end_lon, end_lat]],
                "length_km": float(row.get("length_km", 0.0)),
                "risk_score": float(row.get("risk_score", 0.0)),
                "population_rate_norm": float(row.get("population_rate_norm", 0.0)),
                "accident_rate_norm": float(row.get("accident_rate_norm", 0.0)),
                "nature_rate_norm": float(row.get("nature_rate_norm", 0.0)),
                "base_risk_score": float(row.get("base_risk_score", 0.0)),
                "is_tunnel_edge": bool(row.get("is_tunnel_edge", False)),
            }
        )
    return tuple(records)


def selected_route_bbox(
    selected: List[PathCandidate],
    node_coordinates: Dict[int, Tuple[float, float]],
    buffer_degrees: float = MAP_NATURE_BBOX_BUFFER_DEGREES,
) -> Optional[Tuple[float, float, float, float]]:
    lats: List[float] = []
    lons: List[float] = []
    for candidate in selected:
        if not candidate.feasible:
            continue
        for node_id in candidate.node_path:
            point = node_coordinates.get(int(node_id))
            if point is None:
                continue
            lat, lon = point
            lats.append(lat)
            lons.append(lon)
    if not lats or not lons:
        return None
    return (
        min(lons) - buffer_degrees,
        min(lats) - buffer_degrees,
        max(lons) + buffer_degrees,
        max(lats) + buffer_degrees,
    )


def json_safe_property(value: object) -> Optional[object]:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def nature_reserve_polygon_features(
    data_dir: Path,
    selected: List[PathCandidate],
    node_coordinates: Dict[int, Tuple[float, float]],
    max_features: int = MAP_NATURE_RESERVE_LIMIT,
) -> Tuple[Dict[str, object], ...]:
    all_data_path = data_dir / "all_data.pkl"
    bbox = selected_route_bbox(selected, node_coordinates)
    if not all_data_path.exists() or bbox is None or max_features <= 0:
        return tuple()

    try:
        from shapely.geometry import box, mapping
        from shapely import wkt
    except ImportError:
        return tuple()

    try:
        with all_data_path.open("rb") as file:
            all_data = pickle.load(file)
    except (OSError, pickle.PickleError):
        return tuple()

    nature_table = all_data.get("nature_reserves") if isinstance(all_data, dict) else None
    if not isinstance(nature_table, pd.DataFrame) or "geometry" not in nature_table.columns:
        return tuple()

    clip_box = box(*bbox)
    raw_features: List[Tuple[float, Dict[str, object]]] = []
    for _, row in nature_table.iterrows():
        geometry_value = row.get("geometry")
        if geometry_value is None or pd.isna(geometry_value):
            continue
        try:
            geometry = wkt.loads(str(geometry_value))
        except Exception:
            continue
        if geometry.is_empty or not geometry.intersects(clip_box):
            continue
        clipped = geometry.intersection(clip_box)
        if clipped.is_empty:
            continue
        simplified = clipped.simplify(0.0002, preserve_topology=True)
        if simplified.is_empty:
            continue
        area_value = json_safe_property(row.get("FLAECHE"))
        raw_features.append(
            (
                float(simplified.area),
                {
                    "type": "Feature",
                    "geometry": mapping(simplified),
                    "properties": {
                        "layer_type": "nature_reserve_polygon",
                        "name": json_safe_property(row.get("NAME"))
                        or "Nature reserve",
                        "status": json_safe_property(row.get("STATUS")),
                        "area_source": area_value,
                    },
                },
            )
        )

    raw_features.sort(key=lambda item: item[0], reverse=True)
    return tuple(feature for _, feature in raw_features[:max_features])


def resolve_delivery_mappings(
    routing_table: pd.DataFrame,
    context: GraphContext,
    deliveries: List[MappedDelivery],
    destination_options: Dict[str, List[Tuple[int, float]]],
    max_mapping_distance_m: float,
) -> Dict[str, ResolvedMapping]:
    mappings: Dict[str, ResolvedMapping] = {}
    for delivery in deliveries:
        if not delivery.mapping_feasible:
            mappings[delivery.delivery_id] = ResolvedMapping(
                target_node=None,
                distance_m=delivery.destination_distance_m,
                feasible=False,
                status="mapping_infeasible",
                reason=f"mapping_infeasible: {delivery.mapping_infeasible_reason}",
            )

    hazard_classes = sorted(
        {str(delivery.hazard_class).strip() for delivery in deliveries}
    )
    for hazard_class in hazard_classes:
        group = [
            delivery
            for delivery in deliveries
            if delivery.mapping_feasible
            and str(delivery.hazard_class).strip() == hazard_class
        ]
        if not group:
            continue
        legal_edges = collapse_parallel_edges(
            routing_table,
            "distance_weight",
            hazard_class,
        )
        legal_graph = build_sparse_graph(context, legal_edges, "distance_weight")
        distance_cache: Dict[int, np.ndarray] = {}
        for delivery in group:
            source_index = context.node_to_index.get(delivery.origin_node)
            if source_index is None:
                mappings[delivery.delivery_id] = ResolvedMapping(
                    target_node=None,
                    distance_m=delivery.origin_distance_m,
                    feasible=False,
                    status="mapping_infeasible",
                    reason="mapping_infeasible: origin node is not in the routing graph",
                )
                continue
            options = destination_options[delivery.delivery_id]
            if not options:
                mappings[delivery.delivery_id] = ResolvedMapping(
                    target_node=None,
                    distance_m=delivery.destination_distance_m,
                    feasible=False,
                    status="mapping_infeasible",
                    reason=(
                        "mapping_infeasible: no destination node within "
                        f"{max_mapping_distance_m:.2f} m"
                    ),
                )
                continue
            if source_index not in distance_cache:
                distance_cache[source_index] = dijkstra(
                    csgraph=legal_graph,
                    directed=True,
                    indices=source_index,
                    return_predecessors=False,
                )
            distances = distance_cache[source_index]
            selected: Optional[Tuple[int, float]] = None
            for node, match_distance_m in options:
                target_index = context.node_to_index.get(node)
                if target_index is not None and np.isfinite(distances[target_index]):
                    selected = (node, match_distance_m)
                    break
            if selected is None:
                mappings[delivery.delivery_id] = ResolvedMapping(
                    target_node=None,
                    distance_m=min(distance for _, distance in options),
                    feasible=False,
                    status="mapped",
                    reason=(
                        "route_infeasible: no permitted path reaches a destination "
                        f"mapping within {max_mapping_distance_m:.2f} m"
                    ),
                )
            else:
                mappings[delivery.delivery_id] = ResolvedMapping(
                    target_node=selected[0],
                    distance_m=selected[1],
                    feasible=True,
                    status="mapped",
                    reason="",
                )
    return mappings


def empty_candidate(
    delivery: MappedDelivery,
    label: str,
    mapping: ResolvedMapping,
    reason: str,
    mapping_feasible: bool,
    path_found: bool = False,
) -> PathCandidate:
    return PathCandidate(
        delivery_id=delivery.delivery_id,
        destination_name=delivery.destination_name,
        demand_kg=delivery.demand_kg,
        hazard_class=delivery.hazard_class,
        hazard_class_factor=hazard_class_factor(delivery.hazard_class),
        label=label,
        mapping_status=mapping.status,
        mapping_feasible=mapping_feasible,
        path_found=path_found,
        legal_feasible=False,
        capacity_feasible=False,
        range_feasible_without_charging=False,
        feasible_vehicle_ids=tuple(),
        vehicle_id=None,
        feasible=False,
        infeasible_reason=reason,
        path_length_km=0.0,
        path_risk=0.0,
        variable_cost=None,
        activation_cost=None,
        incremental_cost=None,
        assignment_score=None,
        edge_count=0,
        tunnel_edges_used=0,
        reverse_edges_used=0,
        target_node=mapping.target_node,
        destination_match_distance_m=mapping.distance_m,
        arc_ids=tuple(),
        node_path=tuple(),
        edge_details=tuple(),
    )


def make_path_candidate(
    delivery: MappedDelivery,
    label: str,
    mapping: ResolvedMapping,
    node_path: Tuple[int, ...],
    path_edges: pd.DataFrame,
    vehicles: List[MappedVehicle],
) -> PathCandidate:
    if path_edges.empty:
        return empty_candidate(
            delivery,
            label,
            mapping,
            "route_infeasible: path reconstruction failed",
            mapping_feasible=True,
        )

    path_length_km = float(path_edges["length_km"].sum())
    capacity_ids = tuple(
        sorted(
            vehicle.vehicle_id
            for vehicle in vehicles
            if delivery.demand_kg <= vehicle.capacity_kg
        )
    )
    vehicle_lookup = {vehicle.vehicle_id: vehicle for vehicle in vehicles}
    feasible_ids = tuple(
        vehicle_id
        for vehicle_id in capacity_ids
        if path_length_km <= vehicle_lookup[vehicle_id].range_km
    )
    capacity_feasible = bool(capacity_ids)
    range_feasible = bool(feasible_ids)
    if not capacity_feasible:
        reason = "capacity_infeasible: no vehicle can carry this delivery"
    elif not range_feasible:
        reason = "range_infeasible: no capacity-feasible vehicle can cover the path without charging"
    else:
        reason = ""
    return PathCandidate(
        delivery_id=delivery.delivery_id,
        destination_name=delivery.destination_name,
        demand_kg=delivery.demand_kg,
        hazard_class=delivery.hazard_class,
        hazard_class_factor=hazard_class_factor(delivery.hazard_class),
        label=label,
        mapping_status="mapped",
        mapping_feasible=True,
        path_found=True,
        legal_feasible=True,
        capacity_feasible=capacity_feasible,
        range_feasible_without_charging=range_feasible,
        feasible_vehicle_ids=feasible_ids,
        vehicle_id=None,
        feasible=range_feasible,
        infeasible_reason=reason,
        path_length_km=path_length_km,
        path_risk=float(path_edges["risk_score"].sum()),
        variable_cost=None,
        activation_cost=None,
        incremental_cost=None,
        assignment_score=None,
        edge_count=len(path_edges),
        tunnel_edges_used=int(path_edges["is_tunnel_edge"].sum()),
        reverse_edges_used=int(path_edges["is_reverse"].sum()),
        target_node=mapping.target_node,
        destination_match_distance_m=mapping.distance_m,
        arc_ids=tuple(int(arc_id) for arc_id in path_edges["arc_id"]),
        node_path=node_path,
        edge_details=edge_detail_records(path_edges),
    )


def generate_metric_candidates(
    routing_table: pd.DataFrame,
    context: GraphContext,
    deliveries: List[MappedDelivery],
    mappings: Dict[str, ResolvedMapping],
    vehicles: List[MappedVehicle],
    label: str,
    metric_column: str,
    delivery_routing_tables: Optional[Dict[str, pd.DataFrame]] = None,
    weighted_scales: Optional[Tuple[float, float]] = None,
    risk_weight: float = RISK_WEIGHT,
    cost_weight: float = COST_WEIGHT,
) -> List[PathCandidate]:
    generated: List[PathCandidate] = []
    tables = delivery_routing_tables or {}
    for delivery in deliveries:
        mapping = mappings[delivery.delivery_id]
        if not mapping.feasible:
            mapping_feasible = mapping.status != "mapping_infeasible"
            generated.append(
                empty_candidate(
                    delivery,
                    label,
                    mapping,
                    mapping.reason,
                    mapping_feasible=mapping_feasible,
                )
            )
            continue

        base_table = tables.get(delivery.delivery_id, routing_table)
        cropped_network = base_table is not routing_table
        infeasible_prefix = "crop_infeasible" if cropped_network else "route_infeasible"
        class_table = apply_hazard_class_risk(base_table, delivery.hazard_class)
        if metric_column == "weighted_search_cost":
            if weighted_scales is None:
                raise ValueError("Weighted-search scales are required for weighted paths.")
            class_table = add_weighted_search_cost(
                class_table,
                weighted_scales[0],
                weighted_scales[1],
                risk_weight,
                cost_weight,
            )
        collapsed = collapse_parallel_edges(
            class_table,
            metric_column,
            delivery.hazard_class,
        )
        if collapsed.empty:
            generated.append(
                empty_candidate(
                    delivery,
                    label,
                    mapping,
                    f"{infeasible_prefix}: network contains no permitted edges",
                    mapping_feasible=True,
                )
            )
            continue
        local_context = (
            context if base_table is routing_table else build_graph_context(collapsed)
        )
        source_index = local_context.node_to_index.get(delivery.origin_node)
        target_index = local_context.node_to_index.get(int(mapping.target_node))
        if source_index is None or target_index is None:
            generated.append(
                empty_candidate(
                    delivery,
                    label,
                    mapping,
                    f"{infeasible_prefix}: mapped node is outside the network",
                    mapping_feasible=True,
                )
            )
            continue
        graph = build_sparse_graph(local_context, collapsed, metric_column)
        _, predecessors = dijkstra(
            csgraph=graph,
            directed=True,
            indices=source_index,
            return_predecessors=True,
        )
        node_path = reconstruct_node_path(
            predecessors,
            source_index,
            target_index,
            local_context.node_ids,
        )
        if not node_path:
            generated.append(
                empty_candidate(
                    delivery,
                    label,
                    mapping,
                    f"{infeasible_prefix}: no permitted path to the mapped destination",
                    mapping_feasible=True,
                )
            )
            continue
        path_edges = path_edges_from_nodes(collapsed, node_path)
        generated.append(
            make_path_candidate(
                delivery,
                label,
                mapping,
                node_path,
                path_edges,
                vehicles,
            )
        )
    return generated


def weighted_search_scales(
    candidates: Iterable[PathCandidate],
) -> Tuple[float, float]:
    valid = [
        candidate
        for candidate in candidates
        if candidate.mapping_feasible
        and candidate.path_found
        and candidate.legal_feasible
    ]
    risk_scale = max((candidate.path_risk for candidate in valid), default=0.0)
    length_scale = max((candidate.path_length_km for candidate in valid), default=0.0)
    return risk_scale if risk_scale > 0 else 1.0, length_scale if length_scale > 0 else 1.0


def variable_cost(
    candidate: PathCandidate,
    vehicle: MappedVehicle,
    energy_price: float,
) -> float:
    return candidate.path_length_km * (
        vehicle.variable_cost_per_km
        + vehicle.energy_kwh_per_km * energy_price
    )


def assignment_scales(
    candidates: Iterable[PathCandidate],
    vehicles: Iterable[MappedVehicle],
    energy_price: float,
) -> Tuple[float, float]:
    candidate_list = [candidate for candidate in candidates if candidate.feasible]
    vehicle_lookup = {vehicle.vehicle_id: vehicle for vehicle in vehicles}
    risk_scale = max((candidate.path_risk for candidate in candidate_list), default=0.0)
    cost_values = [
        variable_cost(candidate, vehicle_lookup[vehicle_id], energy_price)
        + vehicle_lookup[vehicle_id].fixed_cost
        for candidate in candidate_list
        for vehicle_id in candidate.feasible_vehicle_ids
    ]
    cost_scale = max(cost_values, default=0.0)
    return risk_scale if risk_scale > 0 else 1.0, cost_scale if cost_scale > 0 else 1.0


def assign_candidates(
    candidates: List[PathCandidate],
    deliveries: List[MappedDelivery],
    vehicles: List[MappedVehicle],
    energy_price: float,
    risk_weight: float = RISK_WEIGHT,
    cost_weight: float = COST_WEIGHT,
) -> Tuple[List[PathCandidate], List[PathCandidate], Tuple[str, ...], float, float]:
    validate_objective_weights(risk_weight, cost_weight)
    risk_scale, cost_scale = assignment_scales(candidates, vehicles, energy_price)
    vehicle_lookup = {vehicle.vehicle_id: vehicle for vehicle in vehicles}
    candidate_indices: Dict[str, List[int]] = {}
    for index, candidate in enumerate(candidates):
        candidate_indices.setdefault(candidate.delivery_id, []).append(index)

    def delivery_order(delivery: MappedDelivery) -> Tuple[int, float, str]:
        feasible_ids = {
            vehicle_id
            for index in candidate_indices.get(delivery.delivery_id, [])
            for vehicle_id in candidates[index].feasible_vehicle_ids
        }
        return (len(feasible_ids), -delivery.demand_kg, delivery.delivery_id)

    updated = list(candidates)
    selected: Dict[str, PathCandidate] = {}
    active_vehicles = set()
    for delivery in sorted(deliveries, key=delivery_order):
        best = None
        for index in candidate_indices.get(delivery.delivery_id, []):
            candidate = updated[index]
            for vehicle_id in candidate.feasible_vehicle_ids:
                vehicle = vehicle_lookup[vehicle_id]
                route_variable_cost = variable_cost(candidate, vehicle, energy_price)
                trip_fixed_cost = vehicle.fixed_cost
                incremental_cost = route_variable_cost + trip_fixed_cost
                score = (
                    risk_weight * candidate.path_risk / risk_scale
                    + cost_weight * incremental_cost / cost_scale
                )
                key = (
                    score,
                    candidate.path_risk,
                    incremental_cost,
                    vehicle_id,
                    candidate.label,
                )
                if best is None or key < best[0]:
                    best = (
                        key,
                        index,
                        vehicle_id,
                        route_variable_cost,
                        trip_fixed_cost,
                        incremental_cost,
                        score,
                    )
        if best is None:
            indices = candidate_indices.get(delivery.delivery_id, [])
            if indices:
                fallback_index = min(indices, key=lambda index: updated[index].label)
                selected[delivery.delivery_id] = updated[fallback_index]
            continue
        _, index, vehicle_id, route_cost, activation, incremental, score = best
        assigned = replace(
            updated[index],
            vehicle_id=vehicle_id,
            variable_cost=route_cost,
            activation_cost=activation,
            incremental_cost=incremental,
            assignment_score=score,
            feasible=True,
            infeasible_reason="",
        )
        updated[index] = assigned
        selected[delivery.delivery_id] = assigned
        active_vehicles.add(vehicle_id)

    selected_in_input_order = [
        selected[delivery.delivery_id]
        for delivery in deliveries
        if delivery.delivery_id in selected
    ]
    return (
        updated,
        selected_in_input_order,
        tuple(sorted(active_vehicles)),
        risk_scale,
        cost_scale,
    )


def run_heuristic(
    adapter_result: AdapterResult,
    network_mode: str = DEFAULT_NETWORK_MODE,
    risk_weight: float = RISK_WEIGHT,
    cost_weight: float = COST_WEIGHT,
    startup_seconds: float = 0.0,
    data_preparation_seconds: float = 0.0,
) -> HeuristicResult:
    validate_objective_weights(risk_weight, cost_weight)
    if network_mode not in SUPPORTED_NETWORK_MODES:
        raise ValueError(f"Unsupported network mode: {network_mode}")
    start = time.perf_counter()
    energy_price = adapter_result.energy_price_eur_per_kwh
    network_start = time.perf_counter()
    edge_table = attach_oneway_information(
        adapter_result.edge_table,
        adapter_result.data_dir,
    )
    edge_table = prepare_metric_columns(edge_table)
    routing_table = build_routing_table(edge_table)
    full_routing_edge_count = len(routing_table)
    if network_mode == "solver_cropped":
        routing_table = filter_largest_strong_component(routing_table)
    context = build_graph_context(routing_table)
    initial_network_seconds = time.perf_counter() - network_start

    mapping_start = time.perf_counter()
    destination_options = build_destination_options(
        adapter_result.node_table,
        adapter_result.deliveries,
        adapter_result.max_mapping_distance_m,
    )
    mappings = resolve_delivery_mappings(
        routing_table,
        context,
        adapter_result.deliveries,
        destination_options,
        adapter_result.max_mapping_distance_m,
    )
    mapping_seconds = time.perf_counter() - mapping_start

    crop_start = time.perf_counter()
    delivery_routing_tables = build_delivery_routing_tables(
        routing_table,
        adapter_result.node_table,
        adapter_result.deliveries,
        mappings,
        network_mode,
    )
    network_preprocessing_seconds = (
        initial_network_seconds + time.perf_counter() - crop_start
    )

    candidate_start = time.perf_counter()
    all_candidates: List[PathCandidate] = []
    preliminary_metric_specs = [
        ("distance", "distance_weight"),
        ("risk", "risk_weight"),
    ]
    for label, metric_column in preliminary_metric_specs:
        all_candidates.extend(
            generate_metric_candidates(
                routing_table,
                context,
                adapter_result.deliveries,
                mappings,
                adapter_result.vehicles,
                label,
                metric_column,
                delivery_routing_tables=delivery_routing_tables,
            )
        )
    weighted_risk_scale, weighted_length_scale = weighted_search_scales(all_candidates)
    all_candidates.extend(
        generate_metric_candidates(
            routing_table,
            context,
            adapter_result.deliveries,
            mappings,
            adapter_result.vehicles,
            "weighted",
            "weighted_search_cost",
            delivery_routing_tables=delivery_routing_tables,
            weighted_scales=(weighted_risk_scale, weighted_length_scale),
            risk_weight=risk_weight,
            cost_weight=cost_weight,
        )
    )
    candidate_generation_seconds = time.perf_counter() - candidate_start

    assignment_start = time.perf_counter()
    all_candidates.sort(key=lambda candidate: (candidate.delivery_id, candidate.label))
    all_candidates, selected, active_vehicles, risk_scale, cost_scale = assign_candidates(
        all_candidates,
        adapter_result.deliveries,
        adapter_result.vehicles,
        energy_price,
        risk_weight=risk_weight,
        cost_weight=cost_weight,
    )
    feasible_selected = [candidate for candidate in selected if candidate.feasible]
    vehicle_lookup = {vehicle.vehicle_id: vehicle for vehicle in adapter_result.vehicles}
    total_variable_cost = sum(
        candidate.variable_cost or 0.0 for candidate in feasible_selected
    )
    total_fixed_cost = sum(
        candidate.activation_cost or 0.0 for candidate in feasible_selected
    )
    vehicle_assignment_seconds = time.perf_counter() - assignment_start
    result_metadata = dict(adapter_result.risk_metadata)
    result_metadata.update(
        {
            "hazard_class_factors": dict(HAZARD_CLASS_FACTORS),
            "tunnel_permission_source": "solver A/B/C/D matrix",
            "full_routing_edge_count": full_routing_edge_count,
            "largest_scc_edge_count": len(routing_table),
            "cropped_edge_counts": {
                delivery_id: len(table)
                for delivery_id, table in delivery_routing_tables.items()
            },
            "solver_crop_buffer": (
                SOLVER_CROP_BUFFER if network_mode == "solver_cropped" else None
            ),
        }
    )
    node_coordinates = {
        int(row["node"]): (float(row["lat"]), float(row["lon"]))
        for _, row in adapter_result.node_table.drop_duplicates("node").iterrows()
    }
    map_background_edges = map_background_edge_records(
        delivery_routing_tables,
        node_coordinates,
    )
    runtime_seconds = time.perf_counter() - start
    return HeuristicResult(
        candidates=all_candidates,
        selected=selected,
        data_dir=adapter_result.data_dir,
        region=adapter_result.region,
        network_mode=network_mode,
        risk_weight=risk_weight,
        cost_weight=cost_weight,
        startup_seconds=startup_seconds,
        data_preparation_seconds=data_preparation_seconds,
        network_preprocessing_seconds=network_preprocessing_seconds,
        mapping_seconds=mapping_seconds,
        candidate_generation_seconds=candidate_generation_seconds,
        vehicle_assignment_seconds=vehicle_assignment_seconds,
        export_seconds=0.0,
        end_to_end_runtime_seconds=(
            startup_seconds + data_preparation_seconds + runtime_seconds
        ),
        runtime_seconds=runtime_seconds,
        total_risk=sum(candidate.path_risk for candidate in feasible_selected),
        total_variable_cost=total_variable_cost,
        total_fixed_cost=total_fixed_cost,
        total_cost=total_variable_cost + total_fixed_cost,
        feasible_deliveries=len(feasible_selected),
        infeasible_deliveries=len(selected) - len(feasible_selected),
        energy_price_scenario=adapter_result.energy_price_scenario,
        energy_price_eur_per_kwh=energy_price,
        active_vehicles=active_vehicles,
        fixed_path_risk_scale=risk_scale,
        fixed_cost_scale=cost_scale,
        weighted_path_risk_scale=weighted_risk_scale,
        weighted_path_length_scale=weighted_length_scale,
        max_mapping_distance_m=adapter_result.max_mapping_distance_m,
        risk_metadata=result_metadata,
        data_warnings=tuple(adapter_result.warnings),
        node_coordinates=node_coordinates,
        map_background_edges=map_background_edges,
        nature_reserve_polygons=tuple(),
    )


def format_candidate(candidate: PathCandidate) -> str:
    status = "feasible" if candidate.feasible else f"infeasible: {candidate.infeasible_reason}"
    variable_cost_text = (
        f"{candidate.variable_cost:.2f}" if candidate.variable_cost is not None else "-"
    )
    activation_cost_text = (
        f"{candidate.activation_cost:.2f}" if candidate.activation_cost is not None else "-"
    )
    return (
        f"- {candidate.delivery_id}/{candidate.label}: {status}, "
        f"mapping={candidate.mapping_status}, vehicle={candidate.vehicle_id or '-'}, "
        f"length={candidate.path_length_km:.2f} km, risk={candidate.path_risk:.4f}, "
        f"variable_cost={variable_cost_text}, "
        f"activation_cost={activation_cost_text}, "
        f"edges={candidate.edge_count}, tunnel_edges={candidate.tunnel_edges_used}, "
        f"reverse_edges={candidate.reverse_edges_used}, "
        f"target_match={candidate.destination_match_distance_m:.2f} m"
    )


def compact_route(node_path: Tuple[int, ...], visible_nodes: int = 6) -> str:
    if not node_path:
        return "-"
    if len(node_path) <= visible_nodes * 2:
        return " -> ".join(str(node) for node in node_path)
    start = " -> ".join(str(node) for node in node_path[:visible_nodes])
    end = " -> ".join(str(node) for node in node_path[-visible_nodes:])
    return f"{start} -> ... -> {end}"


def solver_style_report(result: HeuristicResult) -> str:
    lines = ["HEURISTIK-ERGEBNIS", "=" * 85]
    for candidate in result.selected:
        status = "Feasible" if candidate.feasible else "Infeasible"
        lines.extend(
            [
                "",
                (
                    f"LIEFERUNG {candidate.delivery_id} | "
                    f"Gefahrgutklasse: {candidate.hazard_class} | "
                    f"Gewicht: {candidate.demand_kg:.0f} kg"
                ),
                "-" * 85,
                f"Status:               {status}",
                f"Ziel:                 {candidate.destination_name}",
                f"Fahrzeug:             {candidate.vehicle_id or '-'}",
                f"Kandidat:             {candidate.label}",
                f"Route ({candidate.edge_count} Kanten): {compact_route(candidate.node_path)}",
                f"Gesamtdistanz:        {candidate.path_length_km:.2f} km",
                f"Variable Kosten:      {(candidate.variable_cost or 0.0):.2f} EUR",
                f"Fixkosten je Fahrt:   {(candidate.activation_cost or 0.0):.2f} EUR",
                f"Kumuliertes Risiko:   {candidate.path_risk:.6f}",
            ]
        )
        if candidate.infeasible_reason:
            lines.append(f"Grund:                {candidate.infeasible_reason}")

    lines.extend(
        [
            "",
            "GESAMTSYSTEM",
            "=" * 85,
            f"Region:                 {result.region}",
            f"Netzwerkmodus:          {result.network_mode}",
            f"Strompreis:             {result.energy_price_eur_per_kwh:.2f} EUR/kWh ({result.energy_price_scenario})",
            f"Zulaessige Lieferungen: {result.feasible_deliveries}/{len(result.selected)}",
            f"Eingesetzte Fahrzeugtypen: {len(result.active_vehicles)}",
            f"Namen:                  {', '.join(result.active_vehicles) or '-'}",
            f"Gesamte Fixkosten:       {result.total_fixed_cost:.2f} EUR",
            f"Gesamte var. Kosten:     {result.total_variable_cost:.2f} EUR",
            f"TOTALE KOSTEN:           {result.total_cost:.2f} EUR",
            f"TOTALES RISIKO:          {result.total_risk:.6f}",
            "=" * 85,
            "",
            "ZUSAMMENFASSUNG: ZUWEISUNG UND KOSTEN",
            "-" * 85,
            f"| {'Lieferung':<12} | {'Fahrzeug':<25} | {'Fixkosten':<10} | {'Var. Kosten':<11} | {'Risiko':<10} |",
            "-" * 85,
        ]
    )
    for candidate in result.selected:
        lines.append(
            f"| {candidate.delivery_id:<12} | {(candidate.vehicle_id or '-'):<25} | "
            f"{(candidate.activation_cost or 0.0):>6.2f} EUR | "
            f"{(candidate.variable_cost or 0.0):>7.2f} EUR | "
            f"{candidate.path_risk:>10.6f} |"
        )
    lines.extend(
        [
            "-" * 85,
            "",
            "LAUFZEIT-ZUSAMMENFASSUNG",
            "=" * 60,
            f"Python-Start/Imports: {result.startup_seconds:.3f}s",
            f"Datenvorbereitung:    {result.data_preparation_seconds:.3f}s",
            f"Netzwerkvorbereitung: {result.network_preprocessing_seconds:.3f}s",
            f"Mapping:              {result.mapping_seconds:.3f}s",
            f"Pfadgenerierung:      {result.candidate_generation_seconds:.3f}s",
            f"Fahrzeugzuweisung:    {result.vehicle_assignment_seconds:.3f}s",
            f"Ergebnisverarbeitung: {result.export_seconds:.3f}s",
            "-" * 30,
            f"Heuristik-Kernlaufzeit: {(result.candidate_generation_seconds + result.vehicle_assignment_seconds):.3f}s",
            f"Heuristiklaufzeit:      {result.runtime_seconds:.3f}s",
            f"Heuristik-Gesamtlaufzeit:{result.end_to_end_runtime_seconds:.3f}s",
            "=" * 60,
        ]
    )
    if result.data_warnings:
        lines.extend(["", "WARNUNGEN:"])
        lines.extend(f"- {warning}" for warning in result.data_warnings)
    return "\n".join(lines)


def candidate_to_row(candidate: PathCandidate, selected: bool) -> Dict[str, object]:
    return {
        "delivery_id": candidate.delivery_id,
        "destination_name": candidate.destination_name,
        "demand_kg": candidate.demand_kg,
        "hazard_class": candidate.hazard_class,
        "hazard_class_factor": candidate.hazard_class_factor,
        "candidate_label": candidate.label,
        "selected": selected,
        "mapping_status": candidate.mapping_status,
        "mapping_feasible": candidate.mapping_feasible,
        "path_found": candidate.path_found,
        "legal_feasible": candidate.legal_feasible,
        "capacity_feasible": candidate.capacity_feasible,
        "range_feasible_without_charging": candidate.range_feasible_without_charging,
        "feasible_vehicle_ids": " ".join(candidate.feasible_vehicle_ids),
        "feasible": candidate.feasible,
        "infeasible_reason": candidate.infeasible_reason,
        "vehicle_id": candidate.vehicle_id or "",
        "target_node": candidate.target_node,
        "destination_match_distance_m": round(candidate.destination_match_distance_m, 2),
        "path_length_km": round(candidate.path_length_km, 6),
        "path_risk": round(candidate.path_risk, 6),
        "variable_cost": (
            round(candidate.variable_cost, 6) if candidate.variable_cost is not None else ""
        ),
        "activation_cost": (
            round(candidate.activation_cost, 6)
            if candidate.activation_cost is not None
            else ""
        ),
        "incremental_cost": (
            round(candidate.incremental_cost, 6)
            if candidate.incremental_cost is not None
            else ""
        ),
        "assignment_score": (
            round(candidate.assignment_score, 9)
            if candidate.assignment_score is not None
            else ""
        ),
        "edge_count": candidate.edge_count,
        "tunnel_edges_used": candidate.tunnel_edges_used,
        "reverse_edges_used": candidate.reverse_edges_used,
        "arc_ids": " ".join(str(arc_id) for arc_id in candidate.arc_ids),
        "node_path": " ".join(str(node_id) for node_id in candidate.node_path),
    }


def selected_signatures(result: HeuristicResult) -> set[Tuple[str, str, Tuple[int, ...]]]:
    return {
        (candidate.delivery_id, candidate.label, candidate.arc_ids)
        for candidate in result.selected
    }


def candidates_dataframe(result: HeuristicResult) -> pd.DataFrame:
    selected = selected_signatures(result)
    return pd.DataFrame(
        [
            candidate_to_row(
                candidate,
                (candidate.delivery_id, candidate.label, candidate.arc_ids) in selected,
            )
            for candidate in result.candidates
        ]
    )


def selected_dataframe(result: HeuristicResult) -> pd.DataFrame:
    return pd.DataFrame([candidate_to_row(candidate, True) for candidate in result.selected])


def summary_dict(result: HeuristicResult) -> Dict[str, object]:
    selected = selected_dataframe(result)
    mapping_infeasible = [
        candidate.delivery_id
        for candidate in result.selected
        if candidate.mapping_status == "mapping_infeasible"
    ]
    route_infeasible = [
        candidate.delivery_id
        for candidate in result.selected
        if candidate.infeasible_reason.startswith("route_infeasible")
    ]
    crop_infeasible = [
        candidate.delivery_id
        for candidate in result.selected
        if candidate.infeasible_reason.startswith("crop_infeasible")
    ]
    metadata = {
        **result.risk_metadata,
        "network_mode": result.network_mode,
        "risk_weight": result.risk_weight,
        "cost_weight": result.cost_weight,
        "max_mapping_distance_m": result.max_mapping_distance_m,
        "fixed_path_risk_scale": result.fixed_path_risk_scale,
        "fixed_cost_scale": result.fixed_cost_scale,
        "weighted_path_risk_scale": result.weighted_path_risk_scale,
        "weighted_path_length_scale": result.weighted_path_length_scale,
    }
    return {
        "region": result.region,
        "network_mode": result.network_mode,
        "risk_weight": result.risk_weight,
        "cost_weight": result.cost_weight,
        "startup_seconds": round(result.startup_seconds, 6),
        "data_preparation_seconds": round(result.data_preparation_seconds, 6),
        "network_preprocessing_seconds": round(
            result.network_preprocessing_seconds,
            6,
        ),
        "mapping_seconds": round(result.mapping_seconds, 6),
        "candidate_generation_seconds": round(
            result.candidate_generation_seconds,
            6,
        ),
        "vehicle_assignment_seconds": round(
            result.vehicle_assignment_seconds,
            6,
        ),
        "export_seconds": round(result.export_seconds, 6),
        "end_to_end_runtime_seconds": round(result.end_to_end_runtime_seconds, 6),
        "runtime_seconds": round(result.runtime_seconds, 6),
        "energy_price_scenario": result.energy_price_scenario,
        "energy_price_eur_per_kwh": result.energy_price_eur_per_kwh,
        "candidate_count": len(result.candidates),
        "selected_count": len(result.selected),
        "feasible_deliveries": result.feasible_deliveries,
        "infeasible_deliveries": result.infeasible_deliveries,
        "mapping_infeasible_deliveries": mapping_infeasible,
        "route_infeasible_deliveries": route_infeasible,
        "crop_infeasible_deliveries": crop_infeasible,
        "total_risk": round(result.total_risk, 6),
        "total_variable_cost": round(result.total_variable_cost, 6),
        "total_fixed_cost": round(result.total_fixed_cost, 6),
        "total_cost": round(result.total_cost, 6),
        "active_vehicles": list(result.active_vehicles),
        "selected_total_length_km": round(
            float(selected["path_length_km"].sum()) if not selected.empty else 0.0,
            6,
        ),
        "selected_tunnel_edges_used": int(
            selected["tunnel_edges_used"].sum() if not selected.empty else 0
        ),
        "selected_reverse_edges_used": int(
            selected["reverse_edges_used"].sum() if not selected.empty else 0
        ),
        "metadata": metadata,
        "warnings": list(result.data_warnings),
        "notes": [
            "Deliveries are independent one-way OD tasks; no return trip is modelled.",
            "Payload capacity is released after each delivery; execution order is not scheduled.",
            "Risk and cost are reported separately for comparison preparation.",
            "Solver-style output does not imply identical objective definitions.",
            "Tunnel legality follows the solver A/B/C/D hazard-class matrix.",
            "Solver-cropped mode keeps original arc IDs instead of contracting degree chains.",
            "Range is checked without inserting charging stops in this baseline.",
            "Fixed vehicle cost is charged per delivery/trip to match the current solver snapshot.",
        ],
    }


def route_coordinates(
    candidate: PathCandidate,
    node_coordinates: Dict[int, Tuple[float, float]],
) -> List[List[float]]:
    coordinates: List[List[float]] = []
    for node_id in candidate.node_path:
        point = node_coordinates.get(int(node_id))
        if point is None:
            continue
        lat, lon = point
        coordinates.append([lon, lat])
    return coordinates


def selected_paths_geojson(result: HeuristicResult) -> Dict[str, object]:
    features = []
    for candidate in result.selected:
        coordinates = route_coordinates(candidate, result.node_coordinates)
        if not candidate.feasible or len(coordinates) < 2:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
                "properties": {
                    "delivery_id": candidate.delivery_id,
                    "destination_name": candidate.destination_name,
                    "vehicle_id": candidate.vehicle_id,
                    "hazard_class": candidate.hazard_class,
                    "candidate_label": candidate.label,
                    "path_length_km": round(candidate.path_length_km, 6),
                    "path_risk": round(candidate.path_risk, 6),
                    "variable_cost": (
                        round(candidate.variable_cost, 6)
                        if candidate.variable_cost is not None
                        else None
                    ),
                    "fixed_cost": (
                        round(candidate.activation_cost, 6)
                        if candidate.activation_cost is not None
                        else None
                    ),
                    "total_cost": round(
                        (candidate.variable_cost or 0.0)
                        + (candidate.activation_cost or 0.0),
                        6,
                    ),
                    "edge_count": candidate.edge_count,
                    "tunnel_edges_used": candidate.tunnel_edges_used,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def point_feature(
    node_id: int,
    coordinates: List[float],
    properties: Dict[str, object],
) -> Dict[str, object]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": coordinates},
        "properties": {"node_id": int(node_id), **properties},
    }


def heat_point_features(
    background_edges: Tuple[Dict[str, object], ...],
) -> List[Dict[str, object]]:
    metrics = {
        "population": "population_rate_norm",
        "accident": "accident_rate_norm",
        "nature": "nature_rate_norm",
        "risk": "risk_score",
    }
    features: List[Dict[str, object]] = []
    for edge in background_edges:
        coordinates = edge.get("coordinates", [])
        if len(coordinates) != 2:
            continue
        lon = (float(coordinates[0][0]) + float(coordinates[1][0])) / 2
        lat = (float(coordinates[0][1]) + float(coordinates[1][1])) / 2
        for metric, source in metrics.items():
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "layer_type": "heat_point",
                        "metric": metric,
                        "value": round(float(edge.get(source, 0.0)), 6),
                        "arc_id": edge.get("arc_id"),
                    },
                }
            )
    return features


def selected_map_layers_geojson(result: HeuristicResult) -> Dict[str, object]:
    features: List[Dict[str, object]] = []
    seen_origins = set()
    seen_route_nodes = set()
    for candidate in result.selected:
        if not candidate.feasible or len(candidate.node_path) < 2:
            continue
        origin_node = int(candidate.node_path[0])
        destination_node = int(candidate.node_path[-1])
        origin_point = result.node_coordinates.get(origin_node)
        destination_point = result.node_coordinates.get(destination_node)
        if origin_point is not None and origin_node not in seen_origins:
            seen_origins.add(origin_node)
            lat, lon = origin_point
            features.append(
                point_feature(
                    origin_node,
                    [lon, lat],
                    {
                        "layer_type": "origin",
                        "label": "Origin",
                        "delivery_id": "all",
                    },
                )
            )
        if destination_point is not None:
            lat, lon = destination_point
            features.append(
                point_feature(
                    destination_node,
                    [lon, lat],
                    {
                        "layer_type": "destination",
                        "label": candidate.destination_name,
                        "delivery_id": candidate.delivery_id,
                    },
                )
            )

        for step, node_id in enumerate(candidate.node_path):
            key = (candidate.delivery_id, int(node_id))
            point = result.node_coordinates.get(int(node_id))
            if point is None or key in seen_route_nodes:
                continue
            seen_route_nodes.add(key)
            lat, lon = point
            features.append(
                point_feature(
                    int(node_id),
                    [lon, lat],
                    {
                        "layer_type": "route_node",
                        "delivery_id": candidate.delivery_id,
                        "step": step,
                    },
                )
            )

        for detail in candidate.edge_details:
            route_u = int(detail.get("route_u", 0))
            route_v = int(detail.get("route_v", 0))
            start = result.node_coordinates.get(route_u)
            end = result.node_coordinates.get(route_v)
            if start is None or end is None:
                continue
            start_lat, start_lon = start
            end_lat, end_lon = end
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[start_lon, start_lat], [end_lon, end_lat]],
                    },
                    "properties": {
                        "layer_type": "edge_segment",
                        "delivery_id": candidate.delivery_id,
                        "destination_name": candidate.destination_name,
                        "arc_id": detail.get("arc_id"),
                        "step": detail.get("step"),
                        "length_km": round(float(detail.get("length_km", 0.0)), 6),
                        "risk_score": round(float(detail.get("risk_score", 0.0)), 6),
                        "population_rate_norm": round(
                            float(detail.get("population_rate_norm", 0.0)),
                            6,
                        ),
                        "accident_rate_norm": round(
                            float(detail.get("accident_rate_norm", 0.0)),
                            6,
                        ),
                        "nature_rate_norm": round(
                            float(detail.get("nature_rate_norm", 0.0)),
                            6,
                        ),
                        "base_risk_score": round(
                            float(detail.get("base_risk_score", 0.0)),
                            6,
                        ),
                        "is_tunnel_edge": bool(detail.get("is_tunnel_edge", False)),
                    },
                }
            )
    features.extend(heat_point_features(result.map_background_edges))
    features.extend(result.nature_reserve_polygons)
    return {"type": "FeatureCollection", "features": features}


def delivery_map_filename(delivery_id: str) -> str:
    suffix = str(delivery_id)
    if suffix.startswith("delivery_"):
        suffix = suffix.removeprefix("delivery_")
    safe_suffix = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in suffix
    )
    return f"route_lieferung_{safe_suffix}.html"


def map_feature_matches_delivery(
    feature: Dict[str, object],
    selected_delivery_id: Optional[str],
) -> bool:
    properties = feature.get("properties", {})
    if selected_delivery_id is None:
        return True
    delivery_id = properties.get("delivery_id")
    return delivery_id in {selected_delivery_id, "all"}


def folium_locations(coordinates: List[List[float]]) -> List[List[float]]:
    return [[float(lat), float(lon)] for lon, lat in coordinates]


def folium_map_html(
    route_geojson: Dict[str, object],
    layer_geojson: Dict[str, object],
    result: HeuristicResult,
    selected_delivery_id: Optional[str] = None,
) -> str:
    try:
        import folium
        from folium.plugins import HeatMap, MiniMap
    except ImportError as error:  # pragma: no cover - environment guard
        raise RuntimeError(
            "folium is required for route map export. Install folium or skip map export."
        ) from error

    route_features = [
        feature
        for feature in layer_geojson.get("features", [])
        if feature.get("properties", {}).get("layer_type") == "edge_segment"
        and map_feature_matches_delivery(feature, selected_delivery_id)
    ]
    point_features = [
        feature
        for feature in layer_geojson.get("features", [])
        if feature.get("properties", {}).get("layer_type")
        in {"origin", "destination", "route_node"}
        and map_feature_matches_delivery(feature, selected_delivery_id)
    ]
    all_route_coordinates = [
        location
        for feature in route_features
        for location in folium_locations(feature.get("geometry", {}).get("coordinates", []))
    ]
    center = [52.52, 13.405]
    if all_route_coordinates:
        center = [
            sum(location[0] for location in all_route_coordinates)
            / len(all_route_coordinates),
            sum(location[1] for location in all_route_coordinates)
            / len(all_route_coordinates),
        ]

    route_title = (
        f"Heuristic route {selected_delivery_id}"
        if selected_delivery_id is not None
        else "Heuristic selected routes"
    )
    route_map = folium.Map(location=center, zoom_start=12, tiles="CartoDB positron")
    MiniMap(toggle_display=True).add_to(route_map)

    metric_layers = [
        ("population", "Populationsdichte"),
        ("accident", "Unfallrate"),
        ("nature", "Naturschutznaehe"),
        ("risk", "Gesamtrisiko"),
    ]
    for metric, label in metric_layers:
        heat_data = []
        for feature in layer_geojson.get("features", []):
            properties = feature.get("properties", {})
            if (
                properties.get("layer_type") != "heat_point"
                or properties.get("metric") != metric
            ):
                continue
            value = float(properties.get("value") or 0.0)
            if value <= 0.0:
                continue
            lon, lat = feature.get("geometry", {}).get("coordinates", [None, None])
            if lon is None or lat is None:
                continue
            heat_data.append([float(lat), float(lon), value])
        heat_layer = folium.FeatureGroup(name=label, show=False)
        HeatMap(
            heat_data,
            name=label,
            min_opacity=0.2,
            radius=8,
            blur=6,
            max_zoom=15,
            gradient={0.0: "green", 0.5: "yellow", 1.0: "red"},
        ).add_to(heat_layer)
        heat_layer.add_to(route_map)

    route_colors = [
        "#E63946",
        "#2196F3",
        "#4CAF50",
        "#FF9800",
        "#9C27B0",
        "#00BCD4",
    ]
    delivery_colors: Dict[str, str] = {}
    route_layer = folium.FeatureGroup(name=route_title, show=True)
    for feature in route_features:
        properties = feature.get("properties", {})
        delivery_id = str(properties.get("delivery_id", "delivery"))
        if delivery_id not in delivery_colors:
            delivery_colors[delivery_id] = route_colors[
                len(delivery_colors) % len(route_colors)
            ]
        locations = folium_locations(
            feature.get("geometry", {}).get("coordinates", [])
        )
        if len(locations) < 2:
            continue
        tooltip = folium.Tooltip(
            (
                f"Kante {properties.get('arc_id')}<br>"
                f"Lieferung: {html.escape(delivery_id)}<br>"
                f"Distanz: {float(properties.get('length_km') or 0.0):.3f} km<br>"
                f"Risiko: {float(properties.get('risk_score') or 0.0):.4f}"
            )
        )
        folium.PolyLine(
            locations=locations,
            color=delivery_colors[delivery_id],
            weight=5,
            opacity=0.9,
            tooltip=tooltip,
        ).add_to(route_layer)
    route_layer.add_to(route_map)

    route_node_layer = folium.FeatureGroup(name="Route nodes", show=False)
    for feature in point_features:
        properties = feature.get("properties", {})
        layer_type = properties.get("layer_type")
        lon, lat = feature.get("geometry", {}).get("coordinates", [None, None])
        if lon is None or lat is None:
            continue
        location = [float(lat), float(lon)]
        if layer_type == "origin":
            folium.Marker(
                location=location,
                popup=folium.Popup(
                    f"<b>Depot</b><br>Knoten: {properties.get('node_id')}",
                    max_width=200,
                ),
                icon=folium.Icon(color="blue", icon="home", prefix="fa"),
            ).add_to(route_map)
        elif layer_type == "destination":
            folium.Marker(
                location=location,
                popup=folium.Popup(
                    f"<b>{html.escape(str(properties.get('label', 'Kunde')))}</b><br>"
                    f"Lieferung: {html.escape(str(properties.get('delivery_id', '-')))}<br>"
                    f"Knoten: {properties.get('node_id')}",
                    max_width=250,
                ),
                icon=folium.Icon(color="red", icon="truck", prefix="fa"),
            ).add_to(route_map)
        elif layer_type == "route_node":
            folium.CircleMarker(
                location=location,
                radius=2.2,
                color="#555555",
                fill=True,
                fill_color="#ffffff",
                fill_opacity=0.75,
                popup=(
                    f"Lieferung: {properties.get('delivery_id')}<br>"
                    f"Knoten: {properties.get('node_id')}<br>"
                    f"Step: {properties.get('step')}"
                ),
            ).add_to(route_node_layer)
    route_node_layer.add_to(route_map)

    nature_features = [
        feature
        for feature in layer_geojson.get("features", [])
        if feature.get("properties", {}).get("layer_type")
        == "nature_reserve_polygon"
    ]
    if nature_features:
        nature_layer = folium.FeatureGroup(name="Naturschutzgebiete", show=False)
        folium.GeoJson(
            {"type": "FeatureCollection", "features": nature_features},
            name="Naturschutzgebiete",
            style_function=lambda _feature: {
                "color": "#1b7f3a",
                "weight": 1,
                "opacity": 0.7,
                "fillColor": "#3fbf6f",
                "fillOpacity": 0.28,
            },
            tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Name:"]),
        ).add_to(nature_layer)
        nature_layer.add_to(route_map)

    folium.LayerControl(collapsed=False).add_to(route_map)
    if all_route_coordinates:
        route_map.fit_bounds(all_route_coordinates, padding=(24, 24))
    return route_map.get_root().render()


def write_map_outputs(result: HeuristicResult, output_dir: Path) -> None:
    geojson = selected_paths_geojson(result)
    layer_geojson = selected_map_layers_geojson(result)
    with (output_dir / "heuristic_selected_paths.geojson").open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(geojson, file, indent=2, ensure_ascii=False)
    with (output_dir / "heuristic_map_layers.geojson").open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(layer_geojson, file, indent=2, ensure_ascii=False)
    with (output_dir / "heuristic_map.html").open("w", encoding="utf-8") as file:
        file.write(folium_map_html(geojson, layer_geojson, result))
    for candidate in result.selected:
        if not candidate.feasible:
            continue
        with (output_dir / delivery_map_filename(candidate.delivery_id)).open(
            "w",
            encoding="utf-8",
        ) as file:
            file.write(
                folium_map_html(
                    geojson,
                    layer_geojson,
                    result,
                    selected_delivery_id=candidate.delivery_id,
                )
            )


def write_summary_outputs(result: HeuristicResult, output_dir: Path) -> None:
    with (output_dir / "heuristic_summary.json").open("w", encoding="utf-8") as file:
        json.dump(summary_dict(result), file, indent=2, ensure_ascii=False)
    with (output_dir / "heuristic_report.txt").open("w", encoding="utf-8") as file:
        file.write(solver_style_report(result))


def remove_map_outputs(output_dir: Path) -> None:
    map_files = [
        output_dir / "heuristic_selected_paths.geojson",
        output_dir / "heuristic_map_layers.geojson",
        output_dir / "heuristic_map.html",
    ]
    map_files.extend(output_dir.glob("route_lieferung_*.html"))
    for path in map_files:
        if path.exists() and path.is_file():
            path.unlink()


def export_results(
    result: HeuristicResult,
    output_dir: Path,
    export_map: bool = True,
) -> HeuristicResult:
    export_start = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    map_ready_result = result
    if export_map:
        map_ready_result = replace(
            result,
            nature_reserve_polygons=nature_reserve_polygon_features(
                result.data_dir,
                result.selected,
                result.node_coordinates,
            ),
        )
    candidates_dataframe(result).to_csv(output_dir / "heuristic_candidates.csv", index=False)
    selected_dataframe(map_ready_result).to_csv(
        output_dir / "heuristic_selected_paths.csv",
        index=False,
    )
    if export_map:
        write_map_outputs(map_ready_result, output_dir)
    else:
        remove_map_outputs(output_dir)
    export_seconds = time.perf_counter() - export_start
    updated = replace(
        map_ready_result,
        export_seconds=export_seconds,
        end_to_end_runtime_seconds=(
            result.startup_seconds
            + result.data_preparation_seconds
            + result.runtime_seconds
            + export_seconds
        ),
    )
    write_summary_outputs(updated, output_dir)
    final_export_seconds = time.perf_counter() - export_start
    final = replace(
        updated,
        export_seconds=final_export_seconds,
        end_to_end_runtime_seconds=(
            result.startup_seconds
            + result.data_preparation_seconds
            + result.runtime_seconds
            + final_export_seconds
        ),
    )
    write_summary_outputs(final, output_dir)
    return final


def scenario_specs(
    risk_weight: float,
    cost_weight: float,
    include_comparison_scenarios: bool = False,
) -> Tuple[Tuple[str, float, float], ...]:
    specs = [("normal", risk_weight, cost_weight)]
    if include_comparison_scenarios:
        specs.extend(
            [
                ("no_risk_weight", 0.0, 1.0),
                ("no_cost_weight", 1.0, 0.0),
            ]
        )
    return tuple(specs)


def export_scenario_results(
    normal_result: HeuristicResult,
    adapter_result: AdapterResult,
    output_dir: Path,
    network_mode: str,
    startup_seconds: float,
    data_preparation_seconds: float,
    export_map: bool = True,
    include_comparison_scenarios: bool = False,
) -> Tuple[ScenarioRun, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scenario_runs: List[ScenarioRun] = []
    for name, risk_weight, cost_weight in scenario_specs(
        normal_result.risk_weight,
        normal_result.cost_weight,
        include_comparison_scenarios=include_comparison_scenarios,
    ):
        if name == "normal":
            scenario_result = normal_result
        else:
            scenario_result = run_heuristic(
                adapter_result,
                network_mode=network_mode,
                risk_weight=risk_weight,
                cost_weight=cost_weight,
                startup_seconds=startup_seconds,
                data_preparation_seconds=data_preparation_seconds,
            )
        scenario_output_dir = output_dir / name
        exported = export_results(
            scenario_result,
            scenario_output_dir,
            export_map=export_map,
        )
        scenario_runs.append(
            ScenarioRun(
                name=name,
                result=exported,
                output_dir=scenario_output_dir,
            )
        )

    rows = [
        {
            "scenario": run.name,
            "risk_weight": run.result.risk_weight,
            "cost_weight": run.result.cost_weight,
            "feasible_deliveries": run.result.feasible_deliveries,
            "total_risk": run.result.total_risk,
            "total_variable_cost": run.result.total_variable_cost,
            "total_fixed_cost": run.result.total_fixed_cost,
            "total_cost": run.result.total_cost,
            "algorithm_runtime_seconds": run.result.runtime_seconds,
            "end_to_end_runtime_seconds": run.result.end_to_end_runtime_seconds,
            "output_dir": str(run.output_dir),
        }
        for run in scenario_runs
    ]
    pd.DataFrame(rows).to_csv(
        output_dir / "heuristic_scenario_summary.csv",
        index=False,
    )
    with (output_dir / "heuristic_scenario_summary.json").open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(rows, file, indent=2, ensure_ascii=False)
    return tuple(scenario_runs)


def summarize(result: HeuristicResult) -> str:
    summary = summary_dict(result)
    lines = [
        solver_style_report(result),
        "",
        "Real-data path heuristic summary",
        "-" * 36,
        f"region={result.region}",
        f"algorithm_runtime_seconds={result.runtime_seconds:.2f}",
        f"end_to_end_runtime_seconds={result.end_to_end_runtime_seconds:.2f}",
        f"candidate_count={len(result.candidates)}",
        f"feasible_deliveries={result.feasible_deliveries}",
        f"infeasible_deliveries={result.infeasible_deliveries}",
        f"mapping_infeasible_deliveries={summary['mapping_infeasible_deliveries']}",
        f"route_infeasible_deliveries={summary['route_infeasible_deliveries']}",
        f"crop_infeasible_deliveries={summary['crop_infeasible_deliveries']}",
        f"total_risk={result.total_risk:.4f}",
        f"total_variable_cost={result.total_variable_cost:.2f}",
        f"total_fixed_cost={result.total_fixed_cost:.2f}",
        f"total_cost={result.total_cost:.2f}",
        f"active_vehicles={list(result.active_vehicles)}",
        f"metadata={summary['metadata']}",
        "",
        "Selected candidates:",
    ]
    lines.extend(format_candidate(candidate) for candidate in result.selected)
    lines.extend(["", "All candidates:"])
    lines.extend(format_candidate(candidate) for candidate in result.candidates)
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the real-data path heuristic baseline.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Directory containing the agreed project data files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Optional directory for solver-style output. By default, only the normal "
            "scenario is exported. Add --export-scenarios to also export no-risk and "
            "no-cost comparison scenarios."
        ),
    )
    parser.add_argument(
        "--region",
        choices=SUPPORTED_REGIONS,
        default=DEFAULT_REGION,
        help="Road-network region to load (default: germany).",
    )
    parser.add_argument(
        "--network-mode",
        choices=SUPPORTED_NETWORK_MODES,
        default=DEFAULT_NETWORK_MODE,
        help="Use the full graph or the solver-style SCC and OD crop.",
    )
    parser.add_argument(
        "--risk-weight",
        type=float,
        default=RISK_WEIGHT,
        help="Risk share of the weighted objective (default: 0.65).",
    )
    parser.add_argument(
        "--cost-weight",
        type=float,
        default=COST_WEIGHT,
        help="Cost share of the weighted objective (default: 0.35).",
    )
    parser.add_argument(
        "--max-mapping-distance-m",
        type=float,
        default=1000.0,
        help="Maximum coordinate-to-network mapping distance for origins and destinations.",
    )
    parser.add_argument(
        "--energy-price-eur-per-kwh",
        type=float,
        default=None,
        help="Optional manual energy price override, e.g. 0.35 for Berlin solver comparison.",
    )
    parser.add_argument(
        "--no-map",
        action="store_true",
        help="Skip Folium HTML/GeoJSON map export and write only CSV/JSON/TXT outputs.",
    )
    parser.add_argument(
        "--export-scenarios",
        action="store_true",
        help=(
            "Also export no_risk_weight and no_cost_weight comparison scenarios. "
            "Without this flag, --output-dir exports only normal."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_objective_weights(args.risk_weight, args.cost_weight)
    adapter_start = time.perf_counter()
    startup_seconds = adapter_start - MODULE_START_SECONDS
    adapter_result = build_adapter_result(
        args.data_dir,
        max_mapping_distance_m=args.max_mapping_distance_m,
        region=args.region,
        energy_price_eur_per_kwh=args.energy_price_eur_per_kwh,
    )
    data_preparation_seconds = time.perf_counter() - adapter_start
    result = run_heuristic(
        adapter_result,
        network_mode=args.network_mode,
        risk_weight=args.risk_weight,
        cost_weight=args.cost_weight,
        startup_seconds=startup_seconds,
        data_preparation_seconds=data_preparation_seconds,
    )
    scenario_runs: Tuple[ScenarioRun, ...] = tuple()
    if args.output_dir is not None:
        scenario_runs = export_scenario_results(
            result,
            adapter_result,
            args.output_dir,
            network_mode=args.network_mode,
            startup_seconds=startup_seconds,
            data_preparation_seconds=data_preparation_seconds,
            export_map=not args.no_map,
            include_comparison_scenarios=args.export_scenarios,
        )
        result = scenario_runs[0].result
    text = summarize(result)
    if args.output_dir is not None:
        text += f"\n\nExported scenario results to: {args.output_dir}"
        if args.no_map:
            text += "\nMap export skipped (--no-map)."
        for scenario_run in scenario_runs:
            text += (
                f"\n- {scenario_run.name}: "
                f"risk_weight={scenario_run.result.risk_weight:.2f}, "
                f"cost_weight={scenario_run.result.cost_weight:.2f}, "
                f"total_risk={scenario_run.result.total_risk:.4f}, "
                f"total_cost={scenario_run.result.total_cost:.2f}, "
                f"dir={scenario_run.output_dir}"
            )
    output_encoding = sys.stdout.encoding or "utf-8"
    safe_text = text.encode(output_encoding, errors="replace").decode(output_encoding)
    print(safe_text)


if __name__ == "__main__":
    main()
