import pickle
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import pandas as pd
from scipy.sparse.csgraph import dijkstra

from heuristics.real_data_adapter import (
    AdapterResult,
    MappedDelivery,
    MappedVehicle,
    attach_accident_rate,
    berlin_delivery_table,
    build_node_lookup,
    ensure_arc_id,
    load_edge_table,
    map_deliveries,
    normalize_region,
    risk_component_activity,
    select_energy_price,
)
from heuristics.real_data_path_heuristic import (
    ResolvedMapping,
    add_weighted_search_cost,
    apply_hazard_class_risk,
    assign_candidates,
    build_graph_context,
    build_routing_table,
    build_sparse_graph,
    collapse_parallel_edges,
    candidate_to_row,
    crop_delivery_edges,
    filter_largest_strong_component,
    generate_metric_candidates,
    hazard_class_factor,
    make_path_candidate,
    path_edges_from_nodes,
    prepare_metric_columns,
    reconstruct_node_path,
    resolve_delivery_mappings,
    run_heuristic,
    tunnel_allowed,
    validate_objective_weights,
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


def delivery(
    delivery_id="delivery_1",
    demand_kg=1_000.0,
    tunnel_code=None,
    hazard_class="1",
):
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
        hazard_class=hazard_class,
        adr_tunnel_code=tunnel_code,
    )


def edge_table(rows):
    table = pd.DataFrame(rows)
    table["tunnel"] = table.get("tunnel", "no")
    table["is_tunnel_edge"] = table.get("is_tunnel_edge", False)
    return prepare_metric_columns(table)


class AdapterRiskTests(unittest.TestCase):
    def test_energy_price_can_be_overridden_for_solver_comparison(self):
        energy_prices = pd.DataFrame(
            {"scenario": ["highway_hpc"], "price_eur_per_kwh": [0.75]}
        )
        self.assertEqual(
            select_energy_price(energy_prices, override_eur_per_kwh=0.35),
            0.35,
        )
        with self.assertRaisesRegex(ValueError, "must be positive"):
            select_energy_price(energy_prices, override_eur_per_kwh=0.0)

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

    def test_solver_score_has_priority_over_accident_count(self):
        edges = pd.DataFrame(
            {"arc_id": [1], "u": [0], "v": [1], "length_km": [2.0]}
        )
        accidents = pd.DataFrame(
            {
                "arc_id": [1],
                "u": [0],
                "v": [1],
                "score": [0.25],
                "acc_rate": [999.0],
                "accidents": [100.0],
            }
        )
        result, source, transformation = attach_accident_rate(edges, accidents)
        self.assertEqual(source, "score")
        self.assertIn("direct solver score", transformation)
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


class RegionAdapterTests(unittest.TestCase):
    def test_berlin_comparison_deliveries_match_documented_snapshot(self):
        deliveries = berlin_delivery_table()
        self.assertEqual(deliveries["customer_id"].tolist(), [1, 2, 3])
        self.assertEqual(deliveries["danger_class"].tolist(), ["3", "2", "8"])
        self.assertEqual(deliveries["quantity"].tolist(), [10_000.0, 8_000.0, 5_000.0])
        self.assertTrue((deliveries["origin"] == "Berlin Mitte").all())

    def test_missing_arc_ids_are_generated_from_stable_row_order(self):
        table = pd.DataFrame({"u": [10, 20], "v": [20, 30]})
        result = ensure_arc_id(table)
        self.assertEqual(result["arc_id"].tolist(), [0, 1])
        self.assertNotIn("arc_id", table.columns)

    def test_region_names_are_normalized_and_validated(self):
        self.assertEqual(normalize_region(" Berlin "), "berlin")
        with self.assertRaisesRegex(ValueError, "Unsupported region"):
            normalize_region("brandenburg")

    def test_inactive_risk_component_is_reported_without_reweighting(self):
        warnings = []
        activity = risk_component_activity(
            "berlin",
            {"population": 2.0, "accident": 0.0, "nature": 1.0},
            warnings,
        )
        self.assertTrue(activity["population_component_active"])
        self.assertFalse(activity["accident_component_active"])
        self.assertTrue(activity["nature_component_active"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("accident edge-risk source has maximum 0", warnings[0])
        self.assertIn("weights remain unchanged", warnings[0])

    def test_berlin_edge_files_are_combined_as_directed_arcs(self):
        population_graph = {
            "edges": pd.DataFrame(
                {
                    "u": [1, 2],
                    "v": [2, 3],
                    "length_m": [1_000.0, 2_000.0],
                    "population": [10.0, 20.0],
                    "pop_per_meter": [0.01, 0.01],
                }
            )
        }
        nature_graph = {
            "edges": pd.DataFrame(
                {
                    "u": [1, 2],
                    "v": [2, 3],
                    "dist_to_nature_m": [0.0, 100.0],
                }
            )
        }
        accident_graph = {
            "edges": pd.DataFrame(
                {
                    "u": [1, 2],
                    "v": [2, 3],
                    "accidents": [2.0, 1.0],
                    "score": [0.4, 0.1],
                }
            )
        }
        geo_graph = {"tunnel": {0: "no", 1: "yes"}}

        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            for name, value in [
                ("berlin_graph_with_nature_new.pkl", nature_graph),
                ("berlin_graph_with_accidents_new.pkl", accident_graph),
                ("berlin_graph_geo_com.pkl", geo_graph),
            ]:
                with (data_dir / name).open("wb") as handle:
                    pickle.dump(value, handle)

            warnings = []
            result, permission_ready, metadata = load_edge_table(
                data_dir,
                population_graph,
                warnings,
                region="berlin",
            )

        self.assertEqual(result["arc_id"].tolist(), [0, 1])
        self.assertEqual(result["oneway"].tolist(), ["yes", "yes"])
        self.assertEqual(result["tunnel"].tolist(), ["no", "yes"])
        self.assertEqual(result["accident_rate"].tolist(), [0.4, 0.1])
        self.assertEqual(result["population_rate_norm"].tolist(), [0.0, 0.0])
        self.assertEqual(result["accident_rate_norm"].tolist(), [1.0, 0.0])
        self.assertEqual(result["nature_rate_norm"].tolist(), [1.0, 0.0])
        self.assertAlmostEqual(result.loc[0, "risk_rate_per_km"], 0.6)
        self.assertAlmostEqual(result.loc[1, "risk_rate_per_km"], 0.0)
        self.assertAlmostEqual(result.loc[0, "risk_score"], 0.6)
        self.assertAlmostEqual(result.loc[1, "risk_score"], 0.0)
        self.assertTrue(permission_ready)
        self.assertEqual(metadata["accident_source_field"], "score")
        self.assertEqual(metadata["nature_source_field"], "dist_to_nature_m")
        self.assertEqual(
            metadata["risk_component_weights"],
            {"population": 0.4, "accident": 0.4, "nature": 0.2},
        )
        self.assertTrue(metadata["accident_component_active"])
        self.assertEqual(warnings, [])


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
        restricted_delivery = delivery(tunnel_code="D/E", hazard_class="6")
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
        restricted_delivery = delivery(tunnel_code="D/E", hazard_class="6")
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

    def test_cropped_network_failure_is_reported_separately(self):
        table = edge_table(
            [
                {"arc_id": 1, "u": 0, "v": 1, "oneway": "yes", "length_km": 1, "risk_score": 0.1},
                {"arc_id": 2, "u": 1, "v": 2, "oneway": "yes", "length_km": 1, "risk_score": 0.1},
            ]
        )
        routing = build_routing_table(table)
        cropped = routing.loc[routing["arc_id"] == 1].copy()
        full_candidates = generate_metric_candidates(
            routing,
            build_graph_context(routing),
            [delivery()],
            {"delivery_1": ResolvedMapping(2, 10.0, True, "mapped", "")},
            [vehicle()],
            "distance",
            "distance_weight",
        )
        candidates = generate_metric_candidates(
            routing,
            build_graph_context(routing),
            [delivery()],
            {"delivery_1": ResolvedMapping(2, 10.0, True, "mapped", "")},
            [vehicle()],
            "distance",
            "distance_weight",
            delivery_routing_tables={"delivery_1": cropped},
        )
        self.assertTrue(full_candidates[0].feasible)
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].infeasible_reason.startswith("crop_infeasible"))


class RoutingGraphTests(unittest.TestCase):
    def test_solver_tunnel_matrix_is_used_by_hazard_class(self):
        self.assertTrue(tunnel_allowed("yes", "3"))
        self.assertFalse(tunnel_allowed("yes", "6"))
        self.assertFalse(tunnel_allowed("covered", "1.1D"))
        self.assertTrue(tunnel_allowed("building_passage", "1.1D"))
        self.assertTrue(tunnel_allowed("culvert", "6"))

    def test_hazard_factor_adjusts_and_caps_solver_style_risk_score(self):
        table = pd.DataFrame(
            {
                "length_km": [2.0, 2.0],
                "risk_rate_per_km": [0.4, 0.75],
                "risk_score": [0.8, 1.5],
            }
        )
        adjusted = apply_hazard_class_risk(table, "1.1D")
        self.assertEqual(hazard_class_factor("1.1D"), 2.0)
        self.assertAlmostEqual(adjusted.loc[0, "risk_score"], 0.8)
        self.assertAlmostEqual(adjusted.loc[1, "risk_score"], 1.0)

    def test_solver_crop_keeps_only_edges_inside_od_box(self):
        nodes = pd.DataFrame(
            {
                "node": [0, 1, 2, 3],
                "lat": [0.0, 0.01, 0.02, 0.20],
                "lon": [0.0, 0.01, 0.02, 0.20],
            }
        )
        table = edge_table(
            [
                {"arc_id": 1, "u": 0, "v": 1, "oneway": "yes", "length_km": 1, "risk_score": 0},
                {"arc_id": 2, "u": 1, "v": 2, "oneway": "yes", "length_km": 1, "risk_score": 0},
                {"arc_id": 3, "u": 2, "v": 3, "oneway": "yes", "length_km": 1, "risk_score": 0},
            ]
        )
        routing = build_routing_table(table)
        cropped = crop_delivery_edges(routing, 0, 2, nodes)
        self.assertEqual(cropped["arc_id"].tolist(), [1, 2])

    def test_largest_strong_component_matches_solver_preprocessing(self):
        table = edge_table(
            [
                {"arc_id": 1, "u": 0, "v": 1, "oneway": "yes", "length_km": 1, "risk_score": 0},
                {"arc_id": 2, "u": 1, "v": 2, "oneway": "yes", "length_km": 1, "risk_score": 0},
                {"arc_id": 3, "u": 2, "v": 0, "oneway": "yes", "length_km": 1, "risk_score": 0},
                {"arc_id": 4, "u": 10, "v": 11, "oneway": "yes", "length_km": 1, "risk_score": 0},
                {"arc_id": 5, "u": 11, "v": 10, "oneway": "yes", "length_km": 1, "risk_score": 0},
            ]
        )
        filtered = filter_largest_strong_component(build_routing_table(table))
        self.assertEqual(set(filtered["route_u"]), {0, 1, 2})

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
        collapsed = collapse_parallel_edges(routing, "distance_weight", None)
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
            collapsed = collapse_parallel_edges(routing, "weighted_search_cost", None)
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
    def test_run_heuristic_records_external_and_internal_timings(self):
        mapped_delivery = replace(
            delivery(),
            destination_latitude=0.002,
            destination_longitude=0.002,
        )
        mapped_vehicle = vehicle()
        adapter = AdapterResult(
            data_dir=Path("."),
            region="test",
            origin_name="Origin",
            origin_node=0,
            origin_distance_m=10.0,
            origin_mapping_feasible=True,
            max_mapping_distance_m=1_000.0,
            node_table=pd.DataFrame(
                {
                    "node": [0, 1, 2],
                    "lat": [0.0, 0.001, 0.002],
                    "lon": [0.0, 0.001, 0.002],
                }
            ),
            vehicles=[mapped_vehicle],
            deliveries=[mapped_delivery],
            edge_table=pd.DataFrame(
                {
                    "arc_id": [1, 2],
                    "u": [0, 1],
                    "v": [1, 2],
                    "oneway": ["yes", "yes"],
                    "length_km": [1.0, 1.0],
                    "risk_score": [0.1, 0.1],
                    "tunnel": ["no", "no"],
                    "is_tunnel_edge": [False, False],
                }
            ),
            charging_stations=pd.DataFrame(),
            edge_permission_ready=True,
            energy_price_scenario="test",
            energy_price_eur_per_kwh=0.0,
            risk_metadata={},
            notes=[],
            warnings=[],
        )
        result = run_heuristic(
            adapter,
            network_mode="full",
            startup_seconds=0.2,
            data_preparation_seconds=0.3,
        )
        self.assertEqual(result.feasible_deliveries, 1)
        self.assertEqual(result.startup_seconds, 0.2)
        self.assertEqual(result.data_preparation_seconds, 0.3)
        self.assertGreaterEqual(result.end_to_end_runtime_seconds, 0.5)

    def test_objective_weights_must_be_nonnegative_and_sum_to_one(self):
        validate_objective_weights(0.65, 0.35)
        with self.assertRaisesRegex(ValueError, "sum to 1.0"):
            validate_objective_weights(0.5, 0.4)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            validate_objective_weights(-0.1, 1.1)

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

    def test_fixed_cost_is_charged_per_delivery_for_solver_comparison(self):
        deliveries = [delivery("delivery_1"), delivery("delivery_2")]
        candidates = [self.path_candidate(item.delivery_id) for item in deliveries]
        _, selected, active, risk_scale, cost_scale = assign_candidates(
            candidates,
            deliveries,
            [vehicle(fixed_cost=100.0)],
            energy_price=0.0,
        )
        self.assertEqual(active, ("truck",))
        self.assertEqual(sum(item.activation_cost for item in selected), 200.0)
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
