import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from heuristics.multi_customer_heuristic_toy import (
    DEPOT,
    InputDataError,
    build_toy_instance,
    construct_initial_solution,
)
from heuristics.multi_customer_small_adapter import (
    SmallAdapterResult,
    build_small_adapter,
    build_warm_start_payload,
    export_warm_start_json,
)


class MultiCustomerSmallAdapterTests(unittest.TestCase):
    def _write_fixture(
        self,
        root: Path,
        *,
        tunnel_relation=None,
        infinite_relation=None,
    ) -> Path:
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
            small_dir / "small_instanz_for_Timo.csv",
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
                        "cost": (
                            float("inf")
                            if relation == infinite_relation
                            else 5.0
                        ),
                        "time_min": 12.0,
                        "reachable": True,
                        "tunnel_used": relation == tunnel_relation,
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

            result = build_small_adapter(small_dir)
            run = construct_initial_solution(result.instance)

        self.assertEqual(result.included_customers, ("C1", "C2"))
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

    def test_excludes_tunnel_and_nonfinite_loaded_relations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(
                Path(directory),
                tunnel_relation=(DEPOT, "C2"),
                infinite_relation=("C2", DEPOT),
            )

            result = build_small_adapter(small_dir)

        self.assertNotIn((DEPOT, "C2"), result.instance.legs)
        self.assertNotIn(("C2", DEPOT), result.instance.legs)
        self.assertIn((DEPOT, "C2"), result.illegal_loaded_relations)
        self.assertIn(("C2", DEPOT), result.illegal_loaded_relations)

    def test_charger_candidate_requires_both_legal_directions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))

            result = build_small_adapter(small_dir)

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

            result = build_small_adapter(
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

    def test_rejects_unknown_hazard_class_in_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))

            with self.assertRaisesRegex(
                InputDataError,
                "hazard classes not used by this instance: 8",
            ):
                build_small_adapter(
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
                build_small_adapter(small_dir)

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
                build_small_adapter(small_dir)

    def test_accepts_explicit_charger_matrix_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))
            default_file = (
                small_dir / "od_matrix_small_charger.csv"
            )
            explicit_file = small_dir / "charger_explicit.csv"
            default_file.rename(explicit_file)

            result = build_small_adapter(
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

            result = build_small_adapter(
                small_dir,
                excluded_customers=("C2",),
            )
            run = construct_initial_solution(result.instance)
            payload = build_warm_start_payload(
                result,
                run.evaluation,
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

    def test_rejects_unknown_excluded_customer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(Path(directory))

            with self.assertRaisesRegex(
                InputDataError,
                "Unknown excluded customer IDs",
            ):
                build_small_adapter(
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
                build_small_adapter(small_dir)

    def test_exports_solver_warm_start_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            small_dir = self._write_fixture(root)
            adapter = build_small_adapter(small_dir)
            run = construct_initial_solution(adapter.instance)
            output_path = root / "output" / "warm_start.json"

            exported_path = export_warm_start_json(
                adapter,
                run.evaluation,
                output_path,
                search_status=run.status,
                runtime_seconds={
                    "construction": run.runtime_seconds,
                },
                objective_scales=run.scales,
            )
            payload = json.loads(exported_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["status"], "feasible")
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
            payload["objective"]["scales"]["risk"],
            run.scales.risk,
        )
        self.assertIn("total_algorithm", payload["runtime_seconds"])

    def test_infeasible_json_has_no_stale_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            small_dir = self._write_fixture(
                Path(directory),
                tunnel_relation=(DEPOT, "C2"),
                infinite_relation=("C2", DEPOT),
            )
            adapter = build_small_adapter(small_dir)
            run = construct_initial_solution(adapter.instance)

            payload = build_warm_start_payload(
                adapter,
                run.evaluation,
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
            adapter = build_small_adapter(small_dir)
            run = construct_initial_solution(adapter.instance)

            for invalid_runtime in (-1.0, float("nan"), float("inf")):
                with self.subTest(runtime=invalid_runtime):
                    with self.assertRaisesRegex(
                        InputDataError,
                        "runtime_seconds.construction",
                    ):
                        build_warm_start_payload(
                            adapter,
                            run.evaluation,
                            search_status=run.status,
                            runtime_seconds={
                                "construction": invalid_runtime,
                            },
                            objective_scales=run.scales,
                        )

    def test_charging_side_trips_are_exported_separately(self) -> None:
        instance = build_toy_instance()
        run = construct_initial_solution(instance)
        adapter = SmallAdapterResult(
            instance=instance,
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
            risk_source="toy",
            warnings=tuple(),
        )

        payload = build_warm_start_payload(
            adapter,
            run.evaluation,
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


if __name__ == "__main__":
    unittest.main()
