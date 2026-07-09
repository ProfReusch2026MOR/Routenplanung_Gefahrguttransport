from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pandas as pd

import heuristics.multi_customer_small_adapter as legacy_adapter
from heuristics.multi_customer_heuristic_toy import (
    DEPOT,
    InputDataError,
    ObjectiveWeights,
    build_toy_instance,
    construct_initial_solution,
    improve_solution_vnd,
    improve_solution_vns,
    repair_partial_solution_depth_one,
    repair_partial_solution_depth_two,
)
from heuristics.precomputed_matrix_adapter import (
    MatrixAdapterResult,
    SmallAdapterResult,
    build_matrix_adapter,
    build_small_adapter,
    build_result_payload,
    build_warm_start_payload,
    export_result_json,
    export_warm_start_json,
)


class PrecomputedMatrixAdapterTests(unittest.TestCase):
    def test_legacy_small_adapter_names_remain_compatible(self) -> None:
        self.assertIs(SmallAdapterResult, MatrixAdapterResult)
        self.assertIs(build_small_adapter, build_matrix_adapter)
        self.assertIs(build_warm_start_payload, build_result_payload)
        self.assertIs(export_warm_start_json, export_result_json)
        self.assertIs(
            legacy_adapter.build_small_adapter,
            build_matrix_adapter,
        )
        self.assertIs(
            legacy_adapter.export_warm_start_json,
            export_result_json,
        )

    def test_legacy_module_cli_forwards_to_new_adapter(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "heuristics.multi_customer_small_adapter",
                "--help",
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--data-dir", result.stdout)
        self.assertIn("--output-json", result.stdout)

    def test_default_objective_weights_include_time(self) -> None:
        self.assertEqual(
            ObjectiveWeights(),
            ObjectiveWeights(risk=0.5, cost=0.3, time=0.2),
        )

    def _write_fixture(
        self,
        root: Path,
        *,
        unreachable_relation=None,
    ) -> Path:
        unreachable: set = set()
        if isinstance(unreachable_relation, list):
            unreachable.update(unreachable_relation)
        elif unreachable_relation is not None:
            unreachable.add(unreachable_relation)
        small_dir = root / "Small"
        small_dir.mkdir()
        pd.DataFrame(
            [
                {
                    "id": DEPOT,
                    "destination_name": "Test_Depot",
                    "danger_class": "-",
                    "quantity": "-",
                    "unit": "-",
                },
                {
                    "id": "C1",
                    "destination_name": "Customer_One",
                    "danger_class": "3",
                    "quantity": 6_500,
                    "unit": "Liter",
                },
                {
                    "id": "C2",
                    "destination_name": "Customer_Two",
                    "danger_class": "3",
                    "quantity": 9_000,
                    "unit": "Liter",
                },
            ]
        ).to_csv(
            small_dir / "small_instanz.csv",
            index=False,
        )
        pd.DataFrame(
            [
                {
                    "type": "MAN_eTGX",
                    "battery_kwh": 480,
                    "range_km": 500,
                    "energy_kwh_per_km": 0.96,
                    "variable_cost_per_km": 0.55,
                    "charging_power_kw": 375,
                    "fuel_capacity_l": 32_000,
                    "fixcost": 1_000,
                }
            ]
        ).to_csv(root / "vehicles.csv", index=False)

        stops = [DEPOT, "C1", "C2"]
        od_rows = []
        for from_stop in stops:
            for to_stop in stops:
                if from_stop == to_stop:
                    continue
                relation = (from_stop, to_stop)
                od_rows.append(
                    {
                        "from": from_stop,
                        "to": to_stop,
                        "profile": "safest",
                        "load_state": "loaded",
                        "dist_km": 10.0,
                        "cost": 5.0,
                        "time_min": 12.0,
                        "risk_total": 0.5,
                        "road_penalty_total": 0.0,
                        "reachable": relation not in unreachable,
                        "tunnel_used": False,
                    }
                )
        pd.DataFrame(od_rows).to_csv(
            small_dir / "od_matrix_small.csv",
            index=False,
        )

        charger_rows = [
            {
                "from": "C1",
                "to": "L1",
                "profile": "safest",
                "tunnel_used": False,
                "from_type": "customer",
                "to_type": "charger",
                "dist_km": 2.0,
                "time_min": 3.0,
                "risk": 0.4,
            },
            {
                "from": "L1",
                "to": "C1",
                "profile": "safest",
                "tunnel_used": False,
                "from_type": "charger",
                "to_type": "customer",
                "dist_km": 2.5,
                "time_min": 4.0,
                "risk": 0.5,
            },
            {
                "from": "C2",
                "to": "L2",
                "profile": "safest",
                "tunnel_used": False,
                "from_type": "customer",
                "to_type": "charger",
                "dist_km": 3.0,
                "time_min": 5.0,
                "risk": 0.6,
            },
            {
                "from": "L2",
                "to": "C2",
                "profile": "safest",
                "tunnel_used": True,
                "from_type": "charger",
                "to_type": "customer",
                "dist_km": 3.0,
                "time_min": 5.0,
                "risk": 0.6,
            },
        ]
        pd.DataFrame(charger_rows).to_csv(
            small_dir / "od_matrix_small_charger.csv",
            index=False,
        )
        return small_dir


    def test_builds_instance_and_runs_construction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))

            result = build_matrix_adapter(small_dir)
            run = construct_initial_solution(result.instance)

        self.assertEqual(result.included_customers, ("C1", "C2"))
        self.assertEqual(result.dataset_name, "Small")
        self.assertEqual(result.customer_names["C1"], "Customer_One")
        self.assertEqual(result.instance.customers["C1"].demand_kg, 6_500)
        vehicle = result.instance.vehicles["MAN_eTGX"]
        self.assertEqual(vehicle.capacity_kg, 32_000)
        self.assertEqual(vehicle.activation_cost, 1_000)
        self.assertEqual(vehicle.compatible_classes, ("3",))
        self.assertEqual(
            result.vehicle_hazard_compatibility_source,
            "assumption_all_vehicles_support_all_instance_classes",
        )
        self.assertAlmostEqual(
            result.instance.legs[(DEPOT, "C1")].base_risk_rate_per_km,
            0.5,
        )
        self.assertTrue(run.evaluation.feasible)
        self.assertEqual(set(run.evaluation.served_customers), {"C1", "C2"})

    def test_auto_discovers_medium_matrix_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            small_dir = self._write_fixture(root)
            medium_dir = root / "Medium"
            small_dir.rename(medium_dir)
            (
                medium_dir / "small_instanz.csv"
            ).rename(medium_dir / "medium_instanz.csv")
            (
                medium_dir / "od_matrix_small.csv"
            ).rename(medium_dir / "od_matrix_medium.csv")
            (
                medium_dir / "od_matrix_small_charger.csv"
            ).rename(medium_dir / "od_matrix_medium_charger.csv")

            result = build_matrix_adapter(medium_dir)

        self.assertEqual(result.dataset_name, "Medium")
        self.assertEqual(
            Path(result.source_files["instance"]).name,
            "medium_instanz.csv",
        )
        self.assertEqual(
            Path(result.source_files["od_matrix"]).name,
            "od_matrix_medium.csv",
        )
        self.assertEqual(
            Path(result.source_files["charger_matrix"]).name,
            "od_matrix_medium_charger.csv",
        )

    def test_rejects_ambiguous_regular_matrix_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))
            default_file = small_dir / "od_matrix_small.csv"
            (small_dir / "od_matrix_medium.csv").write_bytes(
                default_file.read_bytes()
            )

            with self.assertRaisesRegex(
                InputDataError,
                "Several OD matrix CSV files were found",
            ):
                build_matrix_adapter(small_dir)

    def test_rejects_ambiguous_charger_matrix_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))
            default_file = small_dir / "od_matrix_small_charger.csv"
            (small_dir / "od_matrix_medium_charger.csv").write_bytes(
                default_file.read_bytes()
            )

            with self.assertRaisesRegex(
                InputDataError,
                "Several charger matrix CSV files were found",
            ):
                build_matrix_adapter(small_dir)

    def test_accepts_explicit_regular_od_matrix_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))
            default_file = small_dir / "od_matrix_small.csv"
            explicit_file = small_dir / "regular_routes.csv"
            default_file.rename(explicit_file)

            result = build_matrix_adapter(
                small_dir,
                od_matrix_file=explicit_file,
            )

        self.assertEqual(
            Path(result.source_files["od_matrix"]).name,
            explicit_file.name,
        )
        self.assertIn((DEPOT, "C1"), result.instance.legs)

    def test_accepts_three_component_objective_weights(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))
            weights = ObjectiveWeights(
                risk=0.5,
                cost=0.3,
                time=0.2,
            )

            result = build_matrix_adapter(
                small_dir,
                weights=weights,
            )
            run = construct_initial_solution(result.instance)

        self.assertEqual(result.instance.weights, weights)
        self.assertTrue(run.evaluation.feasible)

    def test_excludes_unreachable_loaded_relations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(
                Path(directory),
                unreachable_relation=(DEPOT, "C2"),
            )

            result = build_matrix_adapter(small_dir)

        self.assertNotIn((DEPOT, "C2"), result.instance.legs)
        self.assertIn((DEPOT, "C2"), result.illegal_loaded_relations)
        self.assertIn(("C2", DEPOT), result.instance.legs)
        self.assertEqual(result.risk_source, "risk_total (direct)")
        self.assertFalse(result.risk_penalty_applied)

    def test_charger_candidate_requires_both_legal_directions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))

            result = build_matrix_adapter(small_dir)

        self.assertEqual(
            result.instance.customer_charger_candidates["C1"],
            ("L1",),
        )
        self.assertEqual(
            result.instance.customer_charger_candidates["C2"],
            tuple(),
        )
        self.assertIn(("C1", "L1"), result.instance.legs)
        self.assertNotIn(("L2", "C2"), result.instance.legs)

    def test_explicit_vehicle_hazard_compatibility_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            small_dir = self._write_fixture(root)
            vehicle_file = root / "vehicles.csv"
            vehicles = pd.read_csv(vehicle_file)
            second_vehicle = vehicles.iloc[0].copy()
            second_vehicle["type"] = "VOLVO_TEST"
            second_vehicle["fixcost"] = 900
            vehicles = pd.concat(
                [vehicles, second_vehicle.to_frame().T],
                ignore_index=True,
            )
            vehicles.to_csv(vehicle_file, index=False)
            compatibility_file = root / "vehicle_hazard.json"
            compatibility_file.write_text(
                json.dumps(
                    {
                        "MAN_eTGX": [],
                        "VOLVO_TEST": ["3"],
                    }
                ),
                encoding="utf-8",
            )

            result = build_matrix_adapter(
                small_dir,
                vehicle_hazard_compatibility_file=compatibility_file,
            )
            run = construct_initial_solution(result.instance)

        self.assertEqual(
            result.instance.vehicles["MAN_eTGX"].compatible_classes,
            tuple(),
        )
        self.assertEqual(
            result.instance.vehicles["VOLVO_TEST"].compatible_classes,
            ("3",),
        )
        self.assertEqual(
            result.vehicle_hazard_compatibility_source,
            "explicit_mapping",
        )
        self.assertEqual(
            Path(
                result.source_files["vehicle_hazard_compatibility"]
            ).name,
            compatibility_file.name,
        )
        self.assertEqual(
            run.evaluation.vehicle_evaluations["MAN_eTGX"].trips,
            tuple(),
        )
        self.assertTrue(
            run.evaluation.vehicle_evaluations["VOLVO_TEST"].trips
        )

    def test_accepts_unused_supported_hazard_class_in_compatibility(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))

            result = build_matrix_adapter(
                small_dir,
                vehicle_hazard_compatibility={
                    "MAN_eTGX": ("3", "8"),
                },
            )

        self.assertEqual(
            result.instance.vehicles["MAN_eTGX"].compatible_classes,
            ("3", "8"),
        )

    def test_rejects_unsupported_hazard_class_in_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))

            with self.assertRaisesRegex(
                InputDataError,
                "unsupported hazard classes: 99",
            ):
                build_matrix_adapter(
                    small_dir,
                    vehicle_hazard_compatibility={
                        "MAN_eTGX": ("3", "99"),
                    },
                )

    def test_requires_vehicle_support_for_each_instance_class(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))

            with self.assertRaisesRegex(
                InputDataError,
                "No vehicle supports instance hazard classes: 3",
            ):
                build_matrix_adapter(
                    small_dir,
                    vehicle_hazard_compatibility={
                        "MAN_eTGX": ("8",),
                    },
                )

    def test_rejects_regular_od_duplicate_after_whitespace_trim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))
            od_file = small_dir / "od_matrix_small.csv"
            frame = pd.read_csv(od_file)
            duplicate = frame.iloc[0].copy()
            duplicate["from"] = f" {duplicate['from']} "
            pd.concat(
                [frame, duplicate.to_frame().T],
                ignore_index=True,
            ).to_csv(od_file, index=False)

            with self.assertRaisesRegex(
                InputDataError,
                "duplicate safest loaded pairs",
            ):
                build_matrix_adapter(small_dir)

    def test_rejects_charger_duplicate_after_whitespace_trim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))
            charger_file = (
                small_dir / "od_matrix_small_charger.csv"
            )
            frame = pd.read_csv(charger_file)
            duplicate = frame.iloc[0].copy()
            duplicate["to"] = f" {duplicate['to']} "
            pd.concat(
                [frame, duplicate.to_frame().T],
                ignore_index=True,
            ).to_csv(charger_file, index=False)

            with self.assertRaisesRegex(
                InputDataError,
                "duplicate safest rows",
            ):
                build_matrix_adapter(small_dir)

    def test_accepts_explicit_charger_matrix_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))
            default_file = (
                small_dir / "od_matrix_small_charger.csv"
            )
            explicit_file = small_dir / "charger_explicit.csv"
            default_file.rename(explicit_file)

            result = build_matrix_adapter(
                small_dir,
                charger_matrix_file=explicit_file,
            )

        self.assertEqual(
            Path(result.source_files["charger_matrix"]).name,
            explicit_file.name,
        )
        self.assertEqual(
            result.instance.customer_charger_candidates["C1"],
            ("L1",),
        )

    def test_customer_exclusion_is_explicit_and_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))

            result = build_matrix_adapter(
                small_dir,
                excluded_customers=("C2",),
            )
            run = construct_initial_solution(result.instance)
            payload = build_result_payload(
                result,
                run.evaluation,
                construction_run=run,
                search_status=run.status,
                runtime_seconds={
                    "construction": run.runtime_seconds,
                },
                objective_scales=run.scales,
            )

        self.assertEqual(result.included_customers, ("C1",))
        self.assertEqual(result.excluded_customers, ("C2",))
        self.assertNotIn("C2", result.instance.customers)
        self.assertNotIn((DEPOT, "C2"), result.instance.legs)
        self.assertTrue(
            payload["metadata"]["route_structure_compatible"]
        )
        self.assertFalse(
            payload["metadata"]["customer_set_complete"]
        )

    def test_single_trip_request_is_exported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))

            result = build_matrix_adapter(small_dir)
            run = construct_initial_solution(
                result.instance,
                single_trip_per_vehicle=True,
            )
            payload = build_result_payload(
                result,
                run.evaluation,
                construction_run=run,
                search_status=run.status,
                runtime_seconds={
                    "construction": run.runtime_seconds,
                },
                objective_scales=run.scales,
            )

        self.assertTrue(
            payload["metadata"]["single_trip_per_vehicle_requested"]
        )
        self.assertTrue(payload["metadata"]["single_trip_per_vehicle"])
        self.assertTrue(
            payload["metadata"]["route_structure_compatible"]
        )

    def test_rejects_unknown_excluded_customer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))

            with self.assertRaisesRegex(
                InputDataError,
                "Unknown excluded customer IDs",
            ):
                build_matrix_adapter(
                    small_dir,
                    excluded_customers=("C99",),
                )

    def test_rejects_missing_required_od_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))
            od_file = small_dir / "od_matrix_small.csv"
            frame = pd.read_csv(od_file).drop(columns=["cost"])
            frame.to_csv(od_file, index=False)

            with self.assertRaisesRegex(
                InputDataError,
                "missing required columns: cost",
            ):
                build_matrix_adapter(small_dir)

    def test_exports_result_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            small_dir = self._write_fixture(root)
            adapter = build_matrix_adapter(small_dir)
            run = construct_initial_solution(adapter.instance)
            repair = repair_partial_solution_depth_one(
                adapter.instance,
                run,
                max_candidate_evaluations=321,
                max_seconds=12.5,
                max_primary_candidates_per_ejection=4,
            )
            depth_two_repair = repair_partial_solution_depth_two(
                adapter.instance,
                repair,
                max_candidate_evaluations=654,
                max_seconds=23.5,
                max_primary_candidates=8,
                max_first_reinsertions=2,
            )
            output_path = root / "output" / "result.json"

            exported_path = export_result_json(
                adapter,
                repair.evaluation,
                output_path,
                construction_run=run,
                search_status=run.status,
                runtime_seconds={
                    "construction": run.runtime_seconds,
                    "repair": repair.runtime_seconds,
                },
                objective_scales=run.scales,
                repair_run=repair,
                depth_two_repair_run=depth_two_repair,
            )
            payload = json.loads(exported_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["status"], "feasible")
        self.assertEqual(payload["metadata"]["dataset_name"], "Small")
        self.assertEqual(
            payload["metadata"]["construction_strategy"],
            run.construction_strategy,
        )
        self.assertEqual(
            payload["metadata"]["repair"]["status"],
            "feasible",
        )
        self.assertEqual(
            payload["metadata"]["repair"]["stop_reason"],
            "completed",
        )
        self.assertEqual(
            payload["metadata"]["repair"]["max_candidate_evaluations"],
            321,
        )
        self.assertEqual(
            payload["metadata"]["repair"]["max_seconds"],
            12.5,
        )
        self.assertEqual(
            payload["metadata"]["repair"][
                "max_primary_candidates_per_ejection"
            ],
            4,
        )
        depth_two_metadata = payload["metadata"]["depth_two_repair"]
        self.assertEqual(depth_two_metadata["status"], "feasible")
        self.assertEqual(depth_two_metadata["stop_reason"], "completed")
        self.assertEqual(
            depth_two_metadata["max_candidate_evaluations"],
            654,
        )
        self.assertEqual(depth_two_metadata["max_seconds"], 23.5)
        self.assertEqual(
            depth_two_metadata["max_primary_candidates"],
            8,
        )
        self.assertEqual(
            depth_two_metadata["max_first_reinsertions"],
            2,
        )
        self.assertEqual(
            set(payload["routes"]["MAN_eTGX"]),
            {DEPOT, "C1", "C2"},
        )
        self.assertEqual(
            payload["trips"]["MAN_eTGX"],
            [payload["routes"]["MAN_eTGX"]],
        )
        self.assertEqual(
            payload["charging_side_trips"]["MAN_eTGX"],
            [],
        )
        self.assertTrue(
            payload["metadata"]["route_structure_compatible"]
        )
        self.assertTrue(payload["metadata"]["customer_set_complete"])
        self.assertTrue(
            payload["metadata"]["requires_solver_importer_validation"]
        )
        self.assertEqual(
            payload["metadata"]["max_charging_branch_evaluations"],
            100,
        )
        self.assertEqual(
            payload["objective"]["scales"]["risk"],
            run.scales.risk,
        )
        self.assertIn("total_algorithm", payload["runtime_seconds"])
        self.assertIsNone(payload["metadata"]["vnd"])
        self.assertIsNone(payload["metadata"]["vns"])
        vehicle_schedule = payload["schedule_details"]["MAN_eTGX"]
        self.assertTrue(vehicle_schedule["trips"])
        first_trip = vehicle_schedule["trips"][0]
        self.assertTrue(first_trip["visits"])
        self.assertTrue(first_trip["legs"])
        self.assertIn("arrival_minute", first_trip["visits"][0])
        self.assertIn("battery_before_kwh", first_trip["legs"][0])

    def test_exports_actual_vnd_vns_configuration_and_diagnostics(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))
            adapter = build_matrix_adapter(small_dir)
            construction = construct_initial_solution(adapter.instance)
            repair = repair_partial_solution_depth_one(
                adapter.instance,
                construction,
            )
            vnd = improve_solution_vnd(
                adapter.instance,
                repair,
                max_neighborhood_passes=7,
            )
            vns = improve_solution_vns(
                adapter.instance,
                vnd,
                random_seed=73,
                max_iterations=3,
                max_seconds=5.0,
                max_vnd_neighborhood_passes=5,
            )

            payload = build_result_payload(
                adapter,
                vns.evaluation,
                construction_run=construction,
                search_status=vns.status,
                runtime_seconds={
                    "construction": construction.runtime_seconds,
                    "repair": repair.runtime_seconds,
                    "vnd": vnd.runtime_seconds,
                    "vns": vns.runtime_seconds,
                },
                repair_run=repair,
                vnd_run=vnd,
                vns_run=vns,
            )

            with self.assertRaisesRegex(
                InputDataError,
                "Final evaluation does not match",
            ):
                build_result_payload(
                    adapter,
                    replace(
                        vns.evaluation,
                        objective=vns.evaluation.objective + 1.0,
                    ),
                    construction_run=construction,
                    search_status=vns.status,
                    runtime_seconds={},
                    vnd_run=vnd,
                    vns_run=vns,
                )

        vnd_metadata = payload["metadata"]["vnd"]
        self.assertEqual(vnd_metadata["max_neighborhood_passes"], 7)
        self.assertEqual(
            vnd_metadata["initial_objective"],
            vnd.initial_evaluation.objective,
        )
        self.assertEqual(
            vnd_metadata["final_objective"],
            vnd.evaluation.objective,
        )
        self.assertIn("accepted_moves", vnd_metadata)
        self.assertIn("incomplete_neighborhoods", vnd_metadata)

        vns_metadata = payload["metadata"]["vns"]
        self.assertEqual(vns_metadata["random_seed"], 73)
        self.assertEqual(vns_metadata["max_iterations"], 3)
        self.assertEqual(vns_metadata["max_seconds"], 5.0)
        self.assertEqual(
            vns_metadata["max_vnd_neighborhood_passes"],
            5,
        )
        self.assertEqual(
            vns_metadata["final_objective"],
            payload["objective"]["value"],
        )
        self.assertIn("accepted_improvements", vns_metadata)
        self.assertIn("evaluated_shakes", vns_metadata)
        self.assertIn("incomplete_local_searches", vns_metadata)

    def test_infeasible_json_has_no_stale_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(
                Path(directory),
                unreachable_relation=[("C2", DEPOT), ("C2", "C1")],
            )
            adapter = build_matrix_adapter(small_dir)
            run = construct_initial_solution(adapter.instance)

            payload = build_result_payload(
                adapter,
                run.evaluation,
                construction_run=run,
                search_status=run.status,
                runtime_seconds={
                    "construction": run.runtime_seconds,
                },
                objective_scales=run.scales,
            )

        self.assertEqual(payload["status"], "infeasible")
        self.assertEqual(payload["routes"], {})
        self.assertEqual(payload["trips"], {})
        self.assertFalse(
            payload["metadata"]["route_structure_compatible"]
        )
        self.assertTrue(payload["infeasibility_reasons"])

    def test_rejects_invalid_runtime_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))
            adapter = build_matrix_adapter(small_dir)
            run = construct_initial_solution(adapter.instance)

            for invalid_runtime in (-1.0, float("nan"), float("inf")):
                with self.subTest(runtime=invalid_runtime):
                    with self.assertRaisesRegex(
                        InputDataError,
                        "runtime_seconds.construction",
                    ):
                        build_result_payload(
                            adapter,
                            run.evaluation,
                            construction_run=run,
                            search_status=run.status,
                            runtime_seconds={
                                "construction": invalid_runtime,
                            },
                            objective_scales=run.scales,
                        )

    def test_charging_side_trips_are_exported_separately(self) -> None:
        instance = build_toy_instance()
        run = construct_initial_solution(instance)
        adapter = MatrixAdapterResult(
            instance=instance,
            dataset_name="toy",
            source_files={},
            customer_names={
                customer_id: customer_id
                for customer_id in instance.customers
            },
            vehicle_hazard_compatibility={
                vehicle_id: vehicle.compatible_classes
                for vehicle_id, vehicle in instance.vehicles.items()
            },
            vehicle_hazard_compatibility_source="toy",
            included_customers=tuple(instance.customers),
            excluded_customers=tuple(),
            illegal_loaded_relations=tuple(),
            penalty_risk_relations=tuple(),
            risk_penalty_prem=0.0,
            risk_penalty_applied=False,
            risk_source="toy",
            warnings=tuple(),
        )

        payload = build_result_payload(
            adapter,
            run.evaluation,
            construction_run=run,
            search_status=run.status,
            runtime_seconds={"construction": run.runtime_seconds},
            objective_scales=run.scales,
        )

        side_trips = [
            side_trip
            for vehicle_side_trips
            in payload["charging_side_trips"].values()
            for side_trip in vehicle_side_trips
        ]
        self.assertTrue(side_trips)
        self.assertTrue(
            all(
                side_trip["returns_to_origin"]
                and side_trip["solver_y_compatible"]
                for side_trip in side_trips
            )
        )
        self.assertTrue(
            any(
                stop in instance.chargers
                for vehicle_routes
                in payload["technical_routes"].values()
                for route in vehicle_routes
                for stop in route
            )
        )

    def test_payload_uses_actual_construction_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))
            adapter = build_matrix_adapter(small_dir)
            run = construct_initial_solution(
                adapter.instance,
                construction_strategy="regret_2",
            )

            payload = build_result_payload(
                adapter,
                run.evaluation,
                construction_run=run,
                search_status=run.status,
                runtime_seconds={"construction": run.runtime_seconds},
                objective_scales=run.scales,
            )

        self.assertEqual(run.construction_strategy, "regret_2")
        self.assertEqual(
            payload["metadata"]["construction_strategy"],
            "regret_2",
        )

    def test_payload_rejects_invalid_run_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))
            adapter = build_matrix_adapter(small_dir)
            run = construct_initial_solution(adapter.instance)
            invalid_run = replace(
                run,
                construction_strategy="not_a_strategy",
            )

            with self.assertRaisesRegex(
                InputDataError,
                "invalid construction strategy",
            ):
                build_result_payload(
                    adapter,
                    run.evaluation,
                    construction_run=invalid_run,
                    search_status=run.status,
                    runtime_seconds={
                        "construction": run.runtime_seconds,
                    },
                    objective_scales=run.scales,
                )


if __name__ == "__main__":
    unittest.main()
