import unittest

import pandas as pd
from scipy.sparse.csgraph import dijkstra

from heuristics.real_data_adapter import (
    MappedDelivery,
    MappedVehicle,
    attach_accident_rate,
    build_node_lookup,
    map_deliveries,
)
from heuristics.real_data_path_heuristic import (
    ResolvedMapping,
    add_weighted_search_cost,
    assign_candidates,
    build_graph_context,
    build_routing_table,
    build_sparse_graph,
    collapse_parallel_edges,
    candidate_to_row,
    generate_metric_candidates,
    make_path_candidate,
    path_edges_from_nodes,
    prepare_metric_columns,
    reconstruct_node_path,
    resolve_delivery_mappings,
)


def vehicle(
    vehicle_id="truck",
    capacity_kg=20_000.0,
    range_km=500.0,
    fixed_cost=100.0,
):
    return MappedVehicle(
        vehicle_id=vehicle_id,
        capacity_kg=capacity_kg,
        range_km=range_km,
        fixed_cost=fixed_cost,
        variable_cost_per_km=1.0,
        energy_kwh_per_km=0.0,
        charging_power_kw=300.0,
    )


def delivery(delivery_id="delivery_1", demand_kg=1_000.0, tunnel_code=None):
    return MappedDelivery(
        delivery_id=delivery_id,
        origin_name="Origin",
        destination_name="Destination",
        destination_latitude=0.0,
        destination_longitude=0.0,
        origin_node=0,
        origin_distance_m=10.0,
        destination_node=2,
        destination_distance_m=10.0,
        mapping_feasible=True,
        mapping_status="mapped",
        mapping_infeasible_reason="",
        demand_kg=demand_kg,
        quantity=demand_kg,
        unit="kg",
        un_number="UN 1",
        hazard_class="1",
        adr_tunnel_code=tunnel_code,
    )


def edge_table(rows):
    table = pd.DataFrame(rows)
    table["tunnel"] = table.get("tunnel", "no")
    table["is_tunnel_edge"] = table.get("is_tunnel_edge", False)
    return prepare_metric_columns(table)


class AdapterRiskTests(unittest.TestCase):
    def test_accidents_are_converted_to_rate_and_zero_length_is_zero(self):
        edges = pd.DataFrame(
            {
                "arc_id": [1, 2],
                "u": [0, 1],
                "v": [1, 2],
                "length_km": [2.0, 0.0],
            }
        )
        accidents = pd.DataFrame(
            {
                "arc_id": [1, 2],
                "u": [0, 1],
                "v": [1, 2],
                "accidents": [4.0, 3.0],
                "weighted_score": [999.0, 999.0],
            }
        )
        result, source, transformation = attach_accident_rate(edges, accidents)
        self.assertEqual(source, "accidents")
        self.assertEqual(transformation, "accidents / length_km")
        self.assertEqual(result["accident_rate"].tolist(), [2.0, 0.0])

    def test_acc_rate_has_priority(self):
        edges = pd.DataFrame(
            {"arc_id": [1], "u": [0], "v": [1], "length_km": [2.0]}
        )
        accidents = pd.DataFrame(
            {
                "arc_id": [1],
                "u": [0],
                "v": [1],
                "acc_rate": [0.25],
                "accidents": [100.0],
            }
        )
        result, source, transformation = attach_accident_rate(edges, accidents)
        self.assertEqual(source, "acc_rate")
        self.assertEqual(transformation, "direct rate")
        self.assertEqual(result.loc[0, "accident_rate"], 0.25)

    def test_undefined_accident_score_is_rejected(self):
        edges = pd.DataFrame(
            {"arc_id": [1], "u": [0], "v": [1], "length_km": [1.0]}
        )
        accidents = pd.DataFrame(
            {"arc_id": [1], "u": [0], "v": [1], "accident_score": [0.2]}
        )
        with self.assertRaisesRegex(ValueError, "semantics are not defined"):
            attach_accident_rate(edges, accidents)


class MappingTests(unittest.TestCase):
    def test_origin_and_destination_thresholds_are_both_checked(self):
        nodes = pd.DataFrame({"node": [1], "lat": [0.0], "lon": [0.0]})
        tree, nodes = build_node_lookup(nodes)
        deliveries = pd.DataFrame(
            {
                "customer_id": [1],
                "origin": ["Origin"],
                "destination_name": ["Far"],
                "destination_latitude": [0.02],
                "destination_longitude": [0.0],
                "un_number": ["UN 1"],
                "danger_class": ["1"],
                "quantity": [100.0],
                "unit": ["kg"],
            }
        )
        mapped = map_deliveries(
            deliveries,
            {},
            tree,
            nodes,
            origin_node=1,
            origin_distance_m=1_200.0,
            max_mapping_distance_m=1_000.0,
        )[0]
        self.assertFalse(mapped.mapping_feasible)
        self.assertEqual(mapped.mapping_status, "mapping_infeasible")
        self.assertIn("origin distance", mapped.mapping_infeasible_reason)
        self.assertIn("destination distance", mapped.mapping_infeasible_reason)

    def test_no_reachable_node_within_threshold_is_mapping_infeasible(self):
        table = edge_table(
            [
                {
                    "arc_id": 1,
                    "u": 0,
                    "v": 1,
                    "oneway": "yes",
                    "length_km": 1.0,
                    "risk_score": 0.1,
                }
            ]
        )
        routing = build_routing_table(table)
        context = build_graph_context(routing)
        mappings = resolve_delivery_mappings(
            routing,
            context,
            [delivery()],
            {"delivery_1": []},
            1_000.0,
        )
        self.assertFalse(mappings["delivery_1"].feasible)
        self.assertEqual(mappings["delivery_1"].status, "mapping_infeasible")

    def test_mapped_but_forbidden_connection_is_route_infeasible(self):
        table = edge_table(
            [
                {
                    "arc_id": 1,
                    "u": 0,
                    "v": 2,
                    "oneway": "yes",
                    "length_km": 1.0,
                    "risk_score": 0.1,
                    "tunnel": "yes",
                    "is_tunnel_edge": True,
                }
            ]
        )
        routing = build_routing_table(table)
        context = build_graph_context(routing)
        restricted_delivery = delivery(tunnel_code="D/E")
        candidates = generate_metric_candidates(
            routing,
            context,
            [restricted_delivery],
            {"delivery_1": ResolvedMapping(2, 10.0, True, "mapped", "")},
            [vehicle()],
            "distance",
            "distance_weight",
        )
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].mapping_feasible)
        self.assertIn("route_infeasible", candidates[0].infeasible_reason)

    def test_mapping_tries_second_option_when_nearest_requires_tunnel(self):
        table = edge_table(
            [
                {
                    "arc_id": 1,
                    "u": 0,
                    "v": 2,
                    "oneway": "yes",
                    "length_km": 1.0,
                    "risk_score": 0.1,
                    "tunnel": "yes",
                    "is_tunnel_edge": True,
                },
                {
                    "arc_id": 2,
                    "u": 0,
                    "v": 3,
                    "oneway": "yes",
                    "length_km": 2.0,
                    "risk_score": 0.2,
                    "tunnel": "no",
                    "is_tunnel_edge": False,
                },
            ]
        )
        routing = build_routing_table(table)
        context = build_graph_context(routing)
        restricted_delivery = delivery(tunnel_code="D/E")
        mappings = resolve_delivery_mappings(
            routing,
            context,
            [restricted_delivery],
            {"delivery_1": [(2, 10.0), (3, 20.0)]},
            1_000.0,
        )
        self.assertTrue(mappings["delivery_1"].feasible)
        self.assertEqual(mappings["delivery_1"].target_node, 3)
        self.assertEqual(mappings["delivery_1"].distance_m, 20.0)


class RoutingGraphTests(unittest.TestCase):
    def test_oneway_values_create_only_allowed_directions(self):
        table = edge_table(
            [
                {"arc_id": 1, "u": 1, "v": 2, "oneway": "yes", "length_km": 1, "risk_score": 0},
                {"arc_id": 2, "u": 2, "v": 3, "oneway": "no", "length_km": 1, "risk_score": 0},
                {"arc_id": 3, "u": 3, "v": 4, "oneway": "-1", "length_km": 1, "risk_score": 0},
                {"arc_id": 4, "u": 4, "v": 5, "oneway": "alternating", "length_km": 1, "risk_score": 0},
            ]
        )
        routing = build_routing_table(table)
        pairs = set(zip(routing["route_u"], routing["route_v"]))
        self.assertEqual(pairs, {(1, 2), (2, 3), (3, 2), (4, 3)})

    def test_parallel_edges_use_minimum_metric_without_csr_sum(self):
        table = edge_table(
            [
                {"arc_id": 10, "u": 0, "v": 1, "oneway": "yes", "length_km": 1.0, "risk_score": 0.1},
                {"arc_id": 11, "u": 0, "v": 1, "oneway": "yes", "length_km": 2.0, "risk_score": 0.2},
            ]
        )
        routing = build_routing_table(table)
        context = build_graph_context(routing)
        collapsed = collapse_parallel_edges(routing, "distance_weight", False)
        graph = build_sparse_graph(context, collapsed, "distance_weight")
        source = context.node_to_index[0]
        target = context.node_to_index[1]
        self.assertEqual(collapsed["arc_id"].tolist(), [10])
        self.assertAlmostEqual(graph[source, target], 1.0 + 1e-9)
        _, predecessors = dijkstra(graph, directed=True, indices=source, return_predecessors=True)
        nodes = reconstruct_node_path(predecessors, source, target, context.node_ids)
        self.assertEqual(path_edges_from_nodes(collapsed, nodes)["arc_id"].tolist(), [10])

    def test_road_splitting_preserves_risk_weight_and_final_choice(self):
        unsplit = edge_table(
            [
                {"arc_id": 10, "u": 0, "v": 2, "oneway": "yes", "length_km": 2.0, "risk_score": 0.2},
                {"arc_id": 20, "u": 0, "v": 1, "oneway": "yes", "length_km": 1.0, "risk_score": 0.3},
                {"arc_id": 21, "u": 1, "v": 2, "oneway": "yes", "length_km": 1.0, "risk_score": 0.3},
            ]
        )
        split = edge_table(
            [
                {"arc_id": 10, "u": 0, "v": 3, "oneway": "yes", "length_km": 1.0, "risk_score": 0.1},
                {"arc_id": 11, "u": 3, "v": 2, "oneway": "yes", "length_km": 1.0, "risk_score": 0.1},
                {"arc_id": 20, "u": 0, "v": 1, "oneway": "yes", "length_km": 1.0, "risk_score": 0.3},
                {"arc_id": 21, "u": 1, "v": 2, "oneway": "yes", "length_km": 1.0, "risk_score": 0.3},
            ]
        )

        selected_candidates = []
        weighted_totals = []
        risk_totals = []
        for table in (unsplit, split):
            routing = build_routing_table(table)
            routing = add_weighted_search_cost(
                routing,
                fixed_risk_scale=0.6,
                fixed_length_scale=2.0,
            )
            context = build_graph_context(routing)
            collapsed = collapse_parallel_edges(routing, "weighted_search_cost", False)
            graph = build_sparse_graph(context, collapsed, "weighted_search_cost")
            source = context.node_to_index[0]
            target = context.node_to_index[2]
            _, predecessors = dijkstra(graph, directed=True, indices=source, return_predecessors=True)
            node_path = reconstruct_node_path(predecessors, source, target, context.node_ids)
            self.assertNotIn(1, node_path)
            path_edges = path_edges_from_nodes(collapsed, node_path)
            risk_totals.append(float(path_edges["risk_score"].sum()))
            weighted_totals.append(float(path_edges["weighted_search_cost"].sum()))
            direct = make_path_candidate(
                delivery(),
                "direct",
                ResolvedMapping(2, 10.0, True, "mapped", ""),
                node_path,
                path_edges,
                [vehicle()],
            )
            alternative_edges = collapsed[collapsed["arc_id"].isin([20, 21])].copy()
            alternative = make_path_candidate(
                delivery(),
                "alternative",
                ResolvedMapping(2, 10.0, True, "mapped", ""),
                (0, 1, 2),
                alternative_edges,
                [vehicle()],
            )
            _, chosen, _, _, _ = assign_candidates(
                [direct, alternative],
                [delivery()],
                [vehicle()],
                energy_price=0.0,
            )
            selected_candidates.append(chosen[0].label)

        self.assertAlmostEqual(risk_totals[0], risk_totals[1])
        self.assertAlmostEqual(weighted_totals[0], weighted_totals[1])
        self.assertEqual(selected_candidates, ["direct", "direct"])


class AssignmentTests(unittest.TestCase):
    def path_candidate(self, delivery_id, label="a", length=10.0, risk=1.0):
        row = pd.DataFrame(
            {
                "arc_id": [1],
                "length_km": [length],
                "risk_score": [risk],
                "is_tunnel_edge": [False],
                "is_reverse": [False],
            }
        )
        item = delivery(delivery_id)
        return make_path_candidate(
            item,
            label,
            ResolvedMapping(2, 10.0, True, "mapped", ""),
            (0, 2),
            row,
            [vehicle()],
        )

    def test_fixed_cost_is_charged_once_for_shared_active_vehicle(self):
        deliveries = [delivery("delivery_1"), delivery("delivery_2")]
        candidates = [self.path_candidate(item.delivery_id) for item in deliveries]
        _, selected, active, risk_scale, cost_scale = assign_candidates(
            candidates,
            deliveries,
            [vehicle(fixed_cost=100.0)],
            energy_price=0.0,
        )
        self.assertEqual(active, ("truck",))
        self.assertEqual(sum(item.activation_cost for item in selected), 100.0)
        self.assertEqual(risk_scale, 1.0)
        self.assertEqual(cost_scale, 110.0)

    def test_assignment_tie_breaks_by_path_label(self):
        item = delivery()
        candidates = [
            self.path_candidate(item.delivery_id, label="b"),
            self.path_candidate(item.delivery_id, label="a"),
        ]
        _, selected, _, _, _ = assign_candidates(
            candidates,
            [item],
            [vehicle()],
            energy_price=0.0,
        )
        self.assertEqual(selected[0].label, "a")

    def test_capacity_and_range_diagnostics_are_separate(self):
        mapping = ResolvedMapping(2, 10.0, True, "mapped", "")
        path = pd.DataFrame(
            {
                "arc_id": [1],
                "length_km": [600.0],
                "risk_score": [1.0],
                "is_tunnel_edge": [False],
                "is_reverse": [False],
            }
        )
        capacity_failure = make_path_candidate(
            delivery(demand_kg=30_000.0), "x", mapping, (0, 2), path, [vehicle()]
        )
        range_failure = make_path_candidate(
            delivery(), "x", mapping, (0, 2), path, [vehicle()]
        )
        self.assertFalse(capacity_failure.capacity_feasible)
        self.assertIn("capacity_infeasible", capacity_failure.infeasible_reason)
        self.assertTrue(range_failure.capacity_feasible)
        self.assertFalse(range_failure.range_feasible_without_charging)
        self.assertIn("range_infeasible", range_failure.infeasible_reason)

    def test_unassigned_candidate_exports_blank_costs(self):
        candidate = self.path_candidate("delivery_1")
        row = candidate_to_row(candidate, selected=False)
        self.assertEqual(row["variable_cost"], "")
        self.assertEqual(row["activation_cost"], "")
        self.assertEqual(row["incremental_cost"], "")
        self.assertEqual(row["assignment_score"], "")


if __name__ == "__main__":
    unittest.main()
