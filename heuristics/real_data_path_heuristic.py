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
import json
from pathlib import Path
import sys
import time
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

try:
    from real_data_adapter import (
        AdapterResult,
        MappedDelivery,
        MappedVehicle,
        build_adapter_result,
        chord_to_meters,
        latlon_to_xyz,
    )
except ModuleNotFoundError:  # pragma: no cover - module execution fallback
    from heuristics.real_data_adapter import (
        AdapterResult,
        MappedDelivery,
        MappedVehicle,
        build_adapter_result,
        chord_to_meters,
        latlon_to_xyz,
    )


RISK_WEIGHT = 0.65
COST_WEIGHT = 0.35
WEIGHT_EPSILON = 1e-9
DESTINATION_MAPPING_CANDIDATES = 250


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


@dataclass(frozen=True)
class HeuristicResult:
    candidates: List[PathCandidate]
    selected: List[PathCandidate]
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
) -> pd.DataFrame:
    if fixed_risk_scale <= 0 or fixed_length_scale <= 0:
        raise ValueError("Weighted-search scales must be positive.")
    routing_table = routing_table.copy()
    routing_table["weighted_search_cost"] = (
        RISK_WEIGHT * routing_table["risk_score"] / fixed_risk_scale
        + COST_WEIGHT * routing_table["length_km"] / fixed_length_scale
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
    base = edge_table[columns].copy()
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
    avoid_tunnels: bool,
) -> pd.DataFrame:
    eligible = routing_table
    if avoid_tunnels:
        eligible = eligible.loc[~eligible["is_tunnel_edge"].to_numpy(dtype=bool)]
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


def delivery_requires_tunnel_avoidance(delivery: MappedDelivery) -> bool:
    code = str(delivery.adr_tunnel_code or "").strip().upper()
    return code not in {"", "-", "NONE", "NAN"}


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

    for avoid_tunnels in (False, True):
        group = [
            delivery
            for delivery in deliveries
            if delivery.mapping_feasible
            and delivery_requires_tunnel_avoidance(delivery) == avoid_tunnels
        ]
        if not group:
            continue
        legal_edges = collapse_parallel_edges(
            routing_table,
            "distance_weight",
            avoid_tunnels,
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
    )


def generate_metric_candidates(
    routing_table: pd.DataFrame,
    context: GraphContext,
    deliveries: List[MappedDelivery],
    mappings: Dict[str, ResolvedMapping],
    vehicles: List[MappedVehicle],
    label: str,
    metric_column: str,
) -> List[PathCandidate]:
    generated: List[PathCandidate] = []
    for avoid_tunnels in (False, True):
        group = [
            delivery
            for delivery in deliveries
            if delivery_requires_tunnel_avoidance(delivery) == avoid_tunnels
        ]
        if not group:
            continue
        collapsed = collapse_parallel_edges(routing_table, metric_column, avoid_tunnels)
        graph = build_sparse_graph(context, collapsed, metric_column)
        predecessor_cache: Dict[int, np.ndarray] = {}
        for delivery in group:
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
            source_index = context.node_to_index.get(delivery.origin_node)
            target_index = context.node_to_index.get(int(mapping.target_node))
            if source_index is None or target_index is None:
                generated.append(
                    empty_candidate(
                        delivery,
                        label,
                        mapping,
                        "mapping_infeasible: mapped node is not in the routing graph",
                        mapping_feasible=False,
                    )
                )
                continue
            if source_index not in predecessor_cache:
                _, predecessor_cache[source_index] = dijkstra(
                    csgraph=graph,
                    directed=True,
                    indices=source_index,
                    return_predecessors=True,
                )
            predecessors = predecessor_cache[source_index]
            node_path = reconstruct_node_path(
                predecessors,
                source_index,
                target_index,
                context.node_ids,
            )
            if not node_path:
                generated.append(
                    empty_candidate(
                        delivery,
                        label,
                        mapping,
                        "route_infeasible: no permitted path to the mapped destination",
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
) -> Tuple[List[PathCandidate], List[PathCandidate], Tuple[str, ...], float, float]:
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
                activation_cost = 0.0 if vehicle_id in active_vehicles else vehicle.fixed_cost
                incremental_cost = route_variable_cost + activation_cost
                score = (
                    RISK_WEIGHT * candidate.path_risk / risk_scale
                    + COST_WEIGHT * incremental_cost / cost_scale
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
                        activation_cost,
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


def run_heuristic(adapter_result: AdapterResult) -> HeuristicResult:
    start = time.perf_counter()
    energy_price = adapter_result.energy_price_eur_per_kwh
    destination_options = build_destination_options(
        adapter_result.node_table,
        adapter_result.deliveries,
        adapter_result.max_mapping_distance_m,
    )
    edge_table = attach_oneway_information(
        adapter_result.edge_table,
        adapter_result.data_dir,
    )
    edge_table = prepare_metric_columns(edge_table)
    routing_table = build_routing_table(edge_table)
    context = build_graph_context(routing_table)
    mappings = resolve_delivery_mappings(
        routing_table,
        context,
        adapter_result.deliveries,
        destination_options,
        adapter_result.max_mapping_distance_m,
    )

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
            )
        )
    weighted_risk_scale, weighted_length_scale = weighted_search_scales(all_candidates)
    weighted_routing_table = add_weighted_search_cost(
        routing_table,
        weighted_risk_scale,
        weighted_length_scale,
    )
    all_candidates.extend(
        generate_metric_candidates(
            weighted_routing_table,
            context,
            adapter_result.deliveries,
            mappings,
            adapter_result.vehicles,
            "weighted",
            "weighted_search_cost",
        )
    )

    all_candidates.sort(key=lambda candidate: (candidate.delivery_id, candidate.label))
    all_candidates, selected, active_vehicles, risk_scale, cost_scale = assign_candidates(
        all_candidates,
        adapter_result.deliveries,
        adapter_result.vehicles,
        energy_price,
    )
    feasible_selected = [candidate for candidate in selected if candidate.feasible]
    vehicle_lookup = {vehicle.vehicle_id: vehicle for vehicle in adapter_result.vehicles}
    total_variable_cost = sum(
        candidate.variable_cost or 0.0 for candidate in feasible_selected
    )
    total_fixed_cost = sum(vehicle_lookup[vehicle_id].fixed_cost for vehicle_id in active_vehicles)
    return HeuristicResult(
        candidates=all_candidates,
        selected=selected,
        runtime_seconds=time.perf_counter() - start,
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
        risk_metadata=dict(adapter_result.risk_metadata),
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


def candidate_to_row(candidate: PathCandidate, selected: bool) -> Dict[str, object]:
    return {
        "delivery_id": candidate.delivery_id,
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
    metadata = {
        **result.risk_metadata,
        "max_mapping_distance_m": result.max_mapping_distance_m,
        "fixed_path_risk_scale": result.fixed_path_risk_scale,
        "fixed_cost_scale": result.fixed_cost_scale,
        "weighted_path_risk_scale": result.weighted_path_risk_scale,
        "weighted_path_length_scale": result.weighted_path_length_scale,
    }
    return {
        "runtime_seconds": round(result.runtime_seconds, 6),
        "energy_price_scenario": result.energy_price_scenario,
        "energy_price_eur_per_kwh": result.energy_price_eur_per_kwh,
        "candidate_count": len(result.candidates),
        "selected_count": len(result.selected),
        "feasible_deliveries": result.feasible_deliveries,
        "infeasible_deliveries": result.infeasible_deliveries,
        "mapping_infeasible_deliveries": mapping_infeasible,
        "route_infeasible_deliveries": route_infeasible,
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
        "notes": [
            "Deliveries are independent one-way OD tasks; no return trip is modelled.",
            "Payload capacity is released after each delivery; execution order is not scheduled.",
            "Risk and cost are reported separately for solver comparison.",
            "Tunnel filtering is conservative for ADR-restricted deliveries.",
            "Range is checked without inserting charging stops in this baseline.",
        ],
    }


def export_results(result: HeuristicResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates_dataframe(result).to_csv(output_dir / "heuristic_candidates.csv", index=False)
    selected_dataframe(result).to_csv(
        output_dir / "heuristic_selected_paths.csv",
        index=False,
    )
    with (output_dir / "heuristic_summary.json").open("w", encoding="utf-8") as file:
        json.dump(summary_dict(result), file, indent=2, ensure_ascii=False)


def summarize(result: HeuristicResult) -> str:
    summary = summary_dict(result)
    lines = [
        "Real-data path heuristic summary",
        "-" * 36,
        f"runtime_seconds={result.runtime_seconds:.2f}",
        f"candidate_count={len(result.candidates)}",
        f"feasible_deliveries={result.feasible_deliveries}",
        f"infeasible_deliveries={result.infeasible_deliveries}",
        f"mapping_infeasible_deliveries={summary['mapping_infeasible_deliveries']}",
        f"route_infeasible_deliveries={summary['route_infeasible_deliveries']}",
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
        help="Optional directory for solver-comparable CSV/JSON output.",
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
    adapter_result = build_adapter_result(
        args.data_dir,
        max_mapping_distance_m=args.max_mapping_distance_m,
    )
    result = run_heuristic(adapter_result)
    if args.output_dir is not None:
        export_results(result, args.output_dir)
    text = summarize(result)
    if args.output_dir is not None:
        text += f"\n\nExported results to: {args.output_dir}"
    output_encoding = sys.stdout.encoding or "utf-8"
    safe_text = text.encode(output_encoding, errors="replace").decode(output_encoding)
    print(safe_text)


if __name__ == "__main__":
    main()
