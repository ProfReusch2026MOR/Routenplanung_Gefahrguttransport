from dataclasses import replace
import unittest
from unittest.mock import patch

from heuristics.multi_customer_heuristic_toy import (
    ChargingStation,
    DEPOT,
    ObjectiveScales,
    ObjectiveWeights,
    build_toy_instance,
    construct_initial_solution,
    evaluate_solution,
    evaluate_vehicle_schedule,
    solver_warm_start_routes,
)


class MultiCustomerHeuristicToyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.instance = build_toy_instance()

    def test_constructs_complete_multi_trip_solution_with_charging(self) -> None:
        run = construct_initial_solution(self.instance)

        self.assertEqual(run.status, "feasible")
        self.assertTrue(run.evaluation.feasible)
        self.assertEqual(
            set(run.evaluation.served_customers),
            set(self.instance.customers),
        )
        self.assertEqual(run.evaluation.unserved_customers, tuple())
        self.assertTrue(
            any(
                len(vehicle_evaluation.trips) > 1
                for vehicle_evaluation
                in run.evaluation.vehicle_evaluations.values()
            )
        )
        self.assertTrue(
            any(
                visit.stop_type == "charging_station"
                for vehicle_evaluation
                in run.evaluation.vehicle_evaluations.values()
                for trip in vehicle_evaluation.trips
                for visit in trip.visits
            )
        )
        for vehicle_evaluation in run.evaluation.vehicle_evaluations.values():
            vehicle = self.instance.vehicles[vehicle_evaluation.vehicle_id]
            for trip in vehicle_evaluation.trips:
                self.assertGreaterEqual(
                    trip.minimum_battery_kwh,
                    vehicle.min_reserve_kwh,
                )

    def test_rejects_mixed_hazard_classes_in_one_trip(self) -> None:
        vehicle = self.instance.vehicles["TRUCK_G_1"]

        evaluation = evaluate_vehicle_schedule(
            self.instance,
            vehicle,
            [["G1", "C1"]],
        )

        self.assertFalse(evaluation.feasible)
        self.assertIn("commodity_incompatible", evaluation.reasons[0])

    def test_capacity_is_reset_only_after_returning_to_depot(self) -> None:
        vehicle = self.instance.vehicles["TRUCK_G_1"]

        overloaded = evaluate_vehicle_schedule(
            self.instance,
            vehicle,
            [["G1", "G2", "G3"]],
        )
        split_into_two_trips = evaluate_vehicle_schedule(
            self.instance,
            vehicle,
            [["G1", "G2"], ["G3"]],
        )

        self.assertFalse(overloaded.feasible)
        self.assertIn("capacity_infeasible", overloaded.reasons[0])
        self.assertTrue(split_into_two_trips.feasible)
        self.assertEqual(len(split_into_two_trips.trips), 2)
        self.assertTrue(
            all(
                trip.stop_sequence[0] == DEPOT
                and trip.stop_sequence[-1] == DEPOT
                for trip in split_into_two_trips.trips
            )
        )

    def test_public_charging_is_required_for_distant_customer(self) -> None:
        vehicle = self.instance.vehicles["TRUCK_G_1"]

        with_charger = evaluate_vehicle_schedule(
            self.instance,
            vehicle,
            [["G3"]],
        )
        without_charger = evaluate_vehicle_schedule(
            replace(self.instance, chargers={}),
            vehicle,
            [["G3"]],
        )

        self.assertTrue(with_charger.feasible)
        self.assertTrue(
            any(
                visit.stop_id == "FAST_CHARGE"
                for visit in with_charger.trips[0].visits
            )
        )
        self.assertFalse(without_charger.feasible)
        self.assertIn("charging_infeasible", without_charger.reasons[0])

    def test_charging_uses_customer_station_customer_side_trip(self) -> None:
        vehicle = self.instance.vehicles["TRUCK_G_1"]

        evaluation = evaluate_vehicle_schedule(
            self.instance,
            vehicle,
            [["G3"]],
        )
        trip = evaluation.trips[0]

        self.assertEqual(
            trip.stop_sequence,
            (DEPOT, "G3", "FAST_CHARGE", "G3", DEPOT),
        )
        self.assertEqual(
            sum(visit.delivered_kg for visit in trip.visits),
            self.instance.customers["G3"].demand_kg,
        )
        self.assertEqual(
            trip.service_minutes,
            self.instance.customers["G3"].service_minutes,
        )
        revisit = next(
            visit
            for visit in trip.visits
            if visit.stop_type == "customer_revisit"
        )
        self.assertEqual(revisit.stop_id, "G3")
        self.assertEqual(revisit.delivered_kg, 0.0)

    def test_loaded_side_trip_risk_is_included(self) -> None:
        vehicle = self.instance.vehicles["TRUCK_G_1"]

        evaluation = evaluate_vehicle_schedule(
            self.instance,
            vehicle,
            [["G3", "G1"]],
        )
        trip = evaluation.trips[0]
        outward = next(
            leg
            for leg in trip.legs
            if leg.from_stop == "G3"
            and leg.to_stop == "FAST_CHARGE"
        )
        return_leg = next(
            leg
            for leg in trip.legs
            if leg.from_stop == "FAST_CHARGE"
            and leg.to_stop == "G3"
        )

        self.assertTrue(evaluation.feasible)
        self.assertTrue(outward.loaded)
        self.assertTrue(return_leg.loaded)
        self.assertGreater(outward.risk, 0.0)
        self.assertGreater(return_leg.risk, 0.0)

    def test_directed_side_trip_legs_are_evaluated_separately(self) -> None:
        legs = dict(self.instance.legs)
        legs[("G3", "FAST_CHARGE")] = replace(
            legs[("G3", "FAST_CHARGE")],
            distance_km=1.0,
            travel_minutes=2.0,
        )
        legs[("FAST_CHARGE", "G3")] = replace(
            legs[("FAST_CHARGE", "G3")],
            distance_km=2.0,
            travel_minutes=3.0,
        )
        instance = replace(self.instance, legs=legs)

        evaluation = evaluate_vehicle_schedule(
            instance,
            instance.vehicles["TRUCK_G_1"],
            [["G3"]],
        )
        side_legs = [
            leg
            for leg in evaluation.trips[0].legs
            if {leg.from_stop, leg.to_stop}
            == {"G3", "FAST_CHARGE"}
        ]

        self.assertTrue(evaluation.feasible)
        self.assertEqual(
            [(leg.from_stop, leg.to_stop, leg.distance_km)
             for leg in side_legs],
            [
                ("G3", "FAST_CHARGE", 1.0),
                ("FAST_CHARGE", "G3", 2.0),
            ],
        )

    def test_infeasible_charger_falls_back_to_another_candidate(self) -> None:
        chargers = dict(self.instance.chargers)
        chargers["BROKEN"] = ChargingStation(
            "BROKEN",
            power_kw=0.0,
            energy_price_per_kwh=0.1,
        )
        legs = dict(self.instance.legs)
        for (from_stop, to_stop), leg in tuple(self.instance.legs.items()):
            if from_stop == "FAST_CHARGE":
                legs[("BROKEN", to_stop)] = replace(
                    leg,
                    from_stop="BROKEN",
                )
            if to_stop == "FAST_CHARGE":
                legs[(from_stop, "BROKEN")] = replace(
                    leg,
                    to_stop="BROKEN",
                )
        candidates = dict(self.instance.customer_charger_candidates)
        candidates["G3"] = ("BROKEN", "FAST_CHARGE")
        instance = replace(
            self.instance,
            chargers=chargers,
            legs=legs,
            customer_charger_candidates=candidates,
        )

        evaluation = evaluate_vehicle_schedule(
            instance,
            instance.vehicles["TRUCK_G_1"],
            [["G3"]],
        )

        self.assertTrue(evaluation.feasible)
        self.assertIn(
            "FAST_CHARGE",
            evaluation.trips[0].stop_sequence,
        )
        self.assertNotIn("BROKEN", evaluation.trips[0].stop_sequence)

    def test_charger_choice_checks_feasibility_of_remaining_schedule(self) -> None:
        customers = dict(self.instance.customers)
        for customer_id in ("G1", "G2", "G3"):
            customers[customer_id] = replace(
                customers[customer_id],
                demand_kg=3_000.0,
            )
        customers["G2"] = replace(
            customers["G2"],
            latest_minute=570.0,
        )
        vehicles = dict(self.instance.vehicles)
        vehicles["TRUCK_G_1"] = replace(
            vehicles["TRUCK_G_1"],
            capacity_kg=10_000.0,
        )
        chargers = dict(self.instance.chargers)
        chargers["CHEAP_SLOW"] = ChargingStation(
            "CHEAP_SLOW",
            power_kw=160.0,
            energy_price_per_kwh=0.0,
        )
        legs = dict(self.instance.legs)
        legs[("G3", "CHEAP_SLOW")] = replace(
            legs[("G3", "FAST_CHARGE")],
            to_stop="CHEAP_SLOW",
            travel_minutes=10.0,
        )
        legs[("CHEAP_SLOW", "G3")] = replace(
            legs[("FAST_CHARGE", "G3")],
            from_stop="CHEAP_SLOW",
            travel_minutes=10.0,
        )
        candidates = dict(self.instance.customer_charger_candidates)
        candidates["G3"] = ("CHEAP_SLOW", "FAST_CHARGE")
        instance = replace(
            self.instance,
            customers=customers,
            vehicles=vehicles,
            chargers=chargers,
            legs=legs,
            customer_charger_candidates=candidates,
            break_nodes=(*self.instance.break_nodes, "CHEAP_SLOW"),
            weights=ObjectiveWeights(risk=0.0, cost=1.0, time=0.0),
        )

        evaluation = evaluate_vehicle_schedule(
            instance,
            instance.vehicles["TRUCK_G_1"],
            [["G3", "G1", "G2"]],
        )

        self.assertTrue(evaluation.feasible)
        self.assertIn(
            "FAST_CHARGE",
            evaluation.trips[0].stop_sequence,
        )
        self.assertNotIn(
            "CHEAP_SLOW",
            evaluation.trips[0].stop_sequence,
        )

    def test_break_need_can_trigger_side_trip_with_sufficient_battery(self) -> None:
        instance = replace(
            self.instance,
            continuous_driving_limit_minutes=15.0,
        )

        evaluation = evaluate_vehicle_schedule(
            instance,
            instance.vehicles["TRUCK_G_BACKUP"],
            [["G3"]],
        )

        self.assertTrue(evaluation.feasible)
        self.assertEqual(
            evaluation.trips[0].stop_sequence,
            (DEPOT, "G3", "FAST_CHARGE", "G3", DEPOT),
        )
        charging_visit = next(
            visit
            for visit in evaluation.trips[0].visits
            if visit.stop_type == "charging_station"
        )
        self.assertEqual(
            charging_visit.break_minutes,
            instance.break_duration_minutes,
        )

    def test_proactive_charging_preserves_next_customer_continuation(self) -> None:
        vehicle = replace(
            self.instance.vehicles["TRUCK_G_1"],
            usable_battery_kwh=10.0,
            initial_battery_kwh=10.0,
            min_reserve_kwh=1.0,
        )
        vehicles = {"TRUCK_G_1": vehicle}
        customers = {
            customer_id: self.instance.customers[customer_id]
            for customer_id in ("G1", "G2")
        }
        legs = dict(self.instance.legs)
        metrics = {
            (DEPOT, "G1"): 2.0,
            ("G1", "G2"): 7.0,
            ("G1", "FAST_CHARGE"): 0.5,
            ("FAST_CHARGE", "G1"): 0.5,
            ("G2", "FAST_CHARGE"): 1.0,
            ("FAST_CHARGE", "G2"): 1.0,
            ("G2", DEPOT): 5.0,
        }
        for key, distance in metrics.items():
            legs[key] = replace(
                legs[key],
                distance_km=distance,
                travel_minutes=distance,
            )
        instance = replace(
            self.instance,
            customers=customers,
            vehicles=vehicles,
            legs=legs,
            customer_charger_candidates={
                "G1": ("FAST_CHARGE",),
                "G2": ("FAST_CHARGE",),
            },
        )

        evaluation = evaluate_vehicle_schedule(
            instance,
            vehicle,
            [["G1", "G2"]],
        )

        self.assertTrue(evaluation.feasible)
        self.assertEqual(
            evaluation.trips[0].stop_sequence,
            (
                DEPOT,
                "G1",
                "FAST_CHARGE",
                "G1",
                "G2",
                "FAST_CHARGE",
                "G2",
                DEPOT,
            ),
        )

    def test_proactive_charging_propagates_over_multiple_customers(self) -> None:
        vehicle = replace(
            self.instance.vehicles["TRUCK_G_1"],
            capacity_kg=10_000.0,
            usable_battery_kwh=10.0,
            initial_battery_kwh=10.0,
            min_reserve_kwh=1.0,
        )
        customers = {}
        for customer_id in ("G1", "G2", "G3"):
            customers[customer_id] = replace(
                self.instance.customers[customer_id],
                demand_kg=3_000.0,
            )
        legs = dict(self.instance.legs)
        metrics = {
            (DEPOT, "G1"): 2.0,
            ("G1", "G2"): 6.0,
            ("G2", "G3"): 1.0,
            ("G3", DEPOT): 5.0,
            ("G1", "FAST_CHARGE"): 0.5,
            ("FAST_CHARGE", "G1"): 0.5,
            ("G2", "FAST_CHARGE"): 2.0,
            ("FAST_CHARGE", "G2"): 1.5,
            ("G3", "FAST_CHARGE"): 2.0,
            ("FAST_CHARGE", "G3"): 1.0,
        }
        for key, distance in metrics.items():
            legs[key] = replace(
                legs[key],
                distance_km=distance,
                travel_minutes=distance,
            )
        instance = replace(
            self.instance,
            customers=customers,
            vehicles={vehicle.vehicle_id: vehicle},
            legs=legs,
            customer_charger_candidates={
                customer_id: ("FAST_CHARGE",)
                for customer_id in customers
            },
        )

        evaluation = evaluate_vehicle_schedule(
            instance,
            vehicle,
            [["G1", "G2", "G3"]],
        )

        self.assertTrue(evaluation.feasible)
        stops = evaluation.trips[0].stop_sequence
        self.assertIn(
            ("G1", "FAST_CHARGE", "G1"),
            tuple(zip(stops, stops[1:], stops[2:])),
        )
        self.assertIn(
            ("G2", "FAST_CHARGE", "G2"),
            tuple(zip(stops, stops[1:], stops[2:])),
        )

    def test_unused_charger_candidate_cannot_destroy_feasibility(self) -> None:
        customers = {
            customer_id: replace(
                self.instance.customers[customer_id],
                demand_kg=1.0,
                service_minutes=0.0,
                earliest_minute=0.0,
                latest_minute=100.0,
            )
            for customer_id in ("G1", "G2", "G3")
        }
        vehicle = replace(
            self.instance.vehicles["TRUCK_G_1"],
            capacity_kg=3.0,
            usable_battery_kwh=10.0,
            initial_battery_kwh=10.0,
            min_reserve_kwh=1.0,
            max_charging_power_kw=300.0,
            shift_start_minute=0.0,
            shift_end_minute=15.5,
            initial_load_minutes=0.0,
            reload_minutes=0.0,
        )
        chargers = dict(self.instance.chargers)
        chargers["SLOW_B"] = ChargingStation(
            "SLOW_B",
            power_kw=42.0,
            energy_price_per_kwh=0.0,
        )
        legs = dict(self.instance.legs)
        metrics = {
            (DEPOT, "G1"): (2.0, 1.0),
            ("G1", "G2"): (4.0, 1.0),
            ("G2", "G3"): (2.0, 1.0),
            ("G3", DEPOT): (2.0, 1.0),
            ("G1", "FAST_CHARGE"): (0.5, 1.0),
            ("FAST_CHARGE", "G1"): (0.5, 1.0),
        }
        for key, (distance, travel_minutes) in metrics.items():
            legs[key] = replace(
                legs[key],
                distance_km=distance,
                travel_minutes=travel_minutes,
            )
        legs[("G2", "SLOW_B")] = replace(
            legs[("G2", "FAST_CHARGE")],
            to_stop="SLOW_B",
            distance_km=1.0,
            travel_minutes=1.0,
        )
        legs[("SLOW_B", "G2")] = replace(
            legs[("FAST_CHARGE", "G2")],
            from_stop="SLOW_B",
            distance_km=1.5,
            travel_minutes=1.0,
        )
        common = replace(
            self.instance,
            customers=customers,
            vehicles={vehicle.vehicle_id: vehicle},
            chargers=chargers,
            legs=legs,
            break_nodes=(*self.instance.break_nodes, "SLOW_B"),
        )
        baseline = replace(
            common,
            customer_charger_candidates={
                "G1": ("FAST_CHARGE",),
                "G2": tuple(),
                "G3": tuple(),
            },
        )
        augmented = replace(
            common,
            customer_charger_candidates={
                "G1": ("FAST_CHARGE",),
                "G2": ("SLOW_B",),
                "G3": tuple(),
            },
        )

        baseline_result = evaluate_vehicle_schedule(
            baseline,
            vehicle,
            [["G1", "G2", "G3"]],
        )
        augmented_result = evaluate_vehicle_schedule(
            augmented,
            vehicle,
            [["G1", "G2", "G3"]],
        )

        self.assertTrue(baseline_result.feasible)
        self.assertTrue(augmented_result.feasible)
        self.assertNotIn(
            "SLOW_B",
            augmented_result.trips[0].stop_sequence,
        )
        self.assertEqual(
            baseline_result.trips[0].stop_sequence,
            augmented_result.trips[0].stop_sequence,
        )

    def test_break_at_side_trip_origin_is_considered(self) -> None:
        vehicle = replace(
            self.instance.vehicles["TRUCK_G_1"],
            usable_battery_kwh=6.0,
            initial_battery_kwh=6.0,
            min_reserve_kwh=2.0,
        )
        legs = dict(self.instance.legs)
        legs[("G1", "FAST_CHARGE")] = replace(
            legs[("G1", "FAST_CHARGE")],
            distance_km=0.5,
            travel_minutes=4.0,
        )
        legs[("FAST_CHARGE", "G1")] = replace(
            legs[("FAST_CHARGE", "G1")],
            distance_km=0.5,
            travel_minutes=4.0,
        )
        instance = replace(
            self.instance,
            vehicles={"TRUCK_G_1": vehicle},
            legs=legs,
            break_nodes=(*self.instance.break_nodes, "G1"),
            continuous_driving_limit_minutes=5.0,
        )

        evaluation = evaluate_vehicle_schedule(
            instance,
            vehicle,
            [["G1"]],
        )
        origin_breaks = [
            visit
            for visit in evaluation.trips[0].visits
            if visit.stop_id == "G1"
            and visit.stop_type == "driver_break"
        ]

        self.assertTrue(evaluation.feasible)
        self.assertEqual(
            evaluation.trips[0].stop_sequence,
            (DEPOT, "G1", "FAST_CHARGE", "G1", DEPOT),
        )
        self.assertGreaterEqual(len(origin_breaks), 1)

    def test_charger_branch_evaluations_respect_configured_limit(self) -> None:
        chargers = dict(self.instance.chargers)
        legs = dict(self.instance.legs)
        candidates = dict(self.instance.customer_charger_candidates)
        for station_id in ("FAST_CHARGE_2", "FAST_CHARGE_3"):
            chargers[station_id] = replace(
                chargers["FAST_CHARGE"],
                station_id=station_id,
            )
            for (from_stop, to_stop), leg in tuple(
                self.instance.legs.items()
            ):
                if from_stop == "FAST_CHARGE":
                    legs[(station_id, to_stop)] = replace(
                        leg,
                        from_stop=station_id,
                    )
                if to_stop == "FAST_CHARGE":
                    legs[(from_stop, station_id)] = replace(
                        leg,
                        to_stop=station_id,
                    )
        candidates["G3"] = (
            "FAST_CHARGE",
            "FAST_CHARGE_2",
            "FAST_CHARGE_3",
        )
        instance = replace(
            self.instance,
            chargers=chargers,
            legs=legs,
            customer_charger_candidates=candidates,
            break_nodes=(
                *self.instance.break_nodes,
                "FAST_CHARGE_2",
                "FAST_CHARGE_3",
            ),
            max_charging_branch_evaluations=2,
        )

        evaluation = evaluate_vehicle_schedule(
            instance,
            instance.vehicles["TRUCK_G_1"],
            [["G3"]],
        )

        self.assertTrue(evaluation.feasible)
        self.assertLessEqual(evaluation.charging_branch_evaluations, 2)

    def test_unsearched_chargers_report_search_incomplete(self) -> None:
        customers = dict(self.instance.customers)
        for customer_id in ("G1", "G2", "G3"):
            customers[customer_id] = replace(
                customers[customer_id],
                demand_kg=3_000.0,
            )
        customers["G2"] = replace(
            customers["G2"],
            latest_minute=570.0,
        )
        chargers = dict(self.instance.chargers)
        legs = dict(self.instance.legs)
        candidates = dict(self.instance.customer_charger_candidates)
        for station_id in ("CHEAP_SLOW_1", "CHEAP_SLOW_2"):
            chargers[station_id] = ChargingStation(
                station_id,
                power_kw=160.0,
                energy_price_per_kwh=0.0,
            )
            legs[("G3", station_id)] = replace(
                legs[("G3", "FAST_CHARGE")],
                to_stop=station_id,
                travel_minutes=10.0,
            )
            legs[(station_id, "G3")] = replace(
                legs[("FAST_CHARGE", "G3")],
                from_stop=station_id,
                travel_minutes=10.0,
            )
        candidates["G3"] = (
            "CHEAP_SLOW_1",
            "CHEAP_SLOW_2",
            "FAST_CHARGE",
        )
        instance = replace(
            self.instance,
            customers=customers,
            chargers=chargers,
            legs=legs,
            customer_charger_candidates=candidates,
            break_nodes=(
                *self.instance.break_nodes,
                "CHEAP_SLOW_1",
                "CHEAP_SLOW_2",
            ),
            max_charging_branch_evaluations=1,
            weights=ObjectiveWeights(risk=0.0, cost=1.0, time=0.0),
        )

        first = evaluate_vehicle_schedule(
            instance,
            instance.vehicles["TRUCK_G_1"],
            [["G3", "G1", "G2"]],
        )
        second = evaluate_vehicle_schedule(
            instance,
            instance.vehicles["TRUCK_G_1"],
            [["G3", "G1", "G2"]],
        )

        self.assertFalse(first.feasible)
        self.assertTrue(
            any(
                "charging_search_incomplete" in reason
                for reason in first.reasons
            )
        )
        self.assertEqual(first.charging_branch_evaluations, 1)
        self.assertEqual(first.reasons, second.reasons)
        self.assertEqual(
            first.charging_branch_evaluations,
            second.charging_branch_evaluations,
        )

    def test_charging_uses_vehicle_or_station_power_whichever_is_lower(self) -> None:
        vehicle = self.instance.vehicles["TRUCK_G_1"]
        evaluation = evaluate_vehicle_schedule(
            self.instance,
            vehicle,
            [["G3"]],
        )
        charging_visit = next(
            visit
            for visit in evaluation.trips[0].visits
            if visit.stop_type == "charging_station"
        )
        station = self.instance.chargers[charging_visit.stop_id]
        effective_power_kw = min(
            station.power_kw,
            vehicle.max_charging_power_kw,
        )
        expected_minutes = (
            charging_visit.charged_energy_kwh
            / effective_power_kw
            * 60.0
        )

        self.assertAlmostEqual(
            charging_visit.charging_minutes,
            expected_minutes,
        )

    def test_charging_and_required_break_can_overlap(self) -> None:
        instance = replace(
            self.instance,
            continuous_driving_limit_minutes=15.0,
        )
        evaluation = evaluate_vehicle_schedule(
            instance,
            instance.vehicles["TRUCK_G_1"],
            [["G3"]],
        )
        charging_visit = next(
            visit
            for visit in evaluation.trips[0].visits
            if visit.stop_type == "charging_station"
        )

        self.assertTrue(evaluation.feasible)
        self.assertEqual(
            charging_visit.break_minutes,
            instance.break_duration_minutes,
        )
        self.assertEqual(
            charging_visit.departure_minute - charging_visit.arrival_minute,
            max(
                charging_visit.charging_minutes,
                charging_visit.break_minutes,
            ),
        )

    def test_long_charge_resets_continuous_driving_before_later_leg(self) -> None:
        instance = replace(
            self.instance,
            continuous_driving_limit_minutes=25.0,
            break_duration_minutes=5.0,
        )

        evaluation = evaluate_vehicle_schedule(
            instance,
            instance.vehicles["TRUCK_G_1"],
            [["G3", "G1"]],
        )
        charging_visit = next(
            visit
            for visit in evaluation.trips[0].visits
            if visit.stop_type == "charging_station"
        )

        self.assertTrue(evaluation.feasible)
        self.assertGreaterEqual(
            charging_visit.charging_minutes,
            instance.break_duration_minutes,
        )
        self.assertEqual(
            charging_visit.break_minutes,
            instance.break_duration_minutes,
        )

    def test_explicit_break_is_recorded_as_visit(self) -> None:
        instance = replace(
            self.instance,
            break_nodes=(*self.instance.break_nodes, "G2"),
            continuous_driving_limit_minutes=10.0,
        )

        evaluation = evaluate_vehicle_schedule(
            instance,
            instance.vehicles["TRUCK_G_1"],
            [["G1", "G2"]],
        )
        break_visit = next(
            visit
            for visit in evaluation.trips[0].visits
            if visit.stop_type == "driver_break"
        )

        self.assertTrue(evaluation.feasible)
        self.assertEqual(break_visit.stop_id, "G2")
        self.assertEqual(
            break_visit.departure_minute - break_visit.arrival_minute,
            instance.break_duration_minutes,
        )
        self.assertEqual(
            break_visit.break_minutes,
            instance.break_duration_minutes,
        )

    def test_single_leg_longer_than_driving_limit_is_rejected(self) -> None:
        instance = replace(
            self.instance,
            continuous_driving_limit_minutes=5.0,
        )

        evaluation = evaluate_vehicle_schedule(
            instance,
            instance.vehicles["TRUCK_G_1"],
            [["G3"]],
        )

        self.assertFalse(evaluation.feasible)
        self.assertIn("break_infeasible", evaluation.reasons[0])

    def test_impossible_customer_time_window_is_reported(self) -> None:
        customers = dict(self.instance.customers)
        customers["G1"] = replace(
            customers["G1"],
            earliest_minute=480.0,
            latest_minute=480.0,
        )
        instance = replace(self.instance, customers=customers)

        evaluation = evaluate_vehicle_schedule(
            instance,
            instance.vehicles["TRUCK_G_1"],
            [["G1"]],
        )

        self.assertFalse(evaluation.feasible)
        self.assertIn("time_window_infeasible", evaluation.reasons[0])

    def test_activation_cost_is_charged_once_for_multiple_trips(self) -> None:
        vehicle = self.instance.vehicles["TRUCK_G_1"]

        evaluation = evaluate_vehicle_schedule(
            self.instance,
            vehicle,
            [["G1", "G2"], ["G4", "G3"]],
        )

        self.assertTrue(evaluation.feasible)
        self.assertEqual(evaluation.activation_cost, vehicle.activation_cost)
        self.assertEqual(evaluation.trip_cost, 2 * vehicle.trip_cost)
        self.assertAlmostEqual(
            evaluation.total_cost,
            evaluation.activation_cost
            + evaluation.trip_cost
            + evaluation.road_operating_cost
            + evaluation.station_charging_cost
            + evaluation.end_of_day_recharge_cost,
        )

    def test_depot_reload_and_charging_are_recorded(self) -> None:
        vehicle = self.instance.vehicles["TRUCK_G_1"]

        evaluation = evaluate_vehicle_schedule(
            self.instance,
            vehicle,
            [["G1", "G2"], ["G4", "G3"]],
        )
        second_trip_types = {
            visit.stop_type for visit in evaluation.trips[1].visits
        }

        self.assertTrue(evaluation.feasible)
        self.assertIn("depot_reload", second_trip_types)
        self.assertIn("depot_charging", second_trip_types)
        self.assertAlmostEqual(
            evaluation.station_charging_cost,
            sum(
                trip.station_charging_cost
                for trip in evaluation.trips
            ),
        )

    def test_end_of_day_recharge_restores_initial_energy_accounting(self) -> None:
        vehicle = self.instance.vehicles["TRUCK_C_1"]

        evaluation = evaluate_vehicle_schedule(
            self.instance,
            vehicle,
            [["C1", "C2"]],
        )

        self.assertTrue(evaluation.feasible)
        self.assertAlmostEqual(
            evaluation.end_of_day_recharge_kwh,
            vehicle.initial_battery_kwh - evaluation.final_battery_kwh,
        )
        self.assertAlmostEqual(
            evaluation.end_of_day_recharge_cost,
            evaluation.end_of_day_recharge_kwh
            * self.instance.depot_energy_price_per_kwh,
        )

    def test_construction_is_deterministic(self) -> None:
        first = construct_initial_solution(self.instance)
        second = construct_initial_solution(self.instance)

        self.assertEqual(first.evaluation.schedules, second.evaluation.schedules)
        self.assertAlmostEqual(
            first.evaluation.objective,
            second.evaluation.objective,
        )

    def test_exported_routes_retain_charging_and_revisit_stops(self) -> None:
        run = construct_initial_solution(self.instance)
        exported = solver_warm_start_routes(run.evaluation)

        self.assertTrue(
            any(
                "FAST_CHARGE" in route
                for routes in exported.values()
                for route in routes
            )
        )
        for vehicle_id, vehicle_evaluation in (
            run.evaluation.vehicle_evaluations.items()
        ):
            if not vehicle_evaluation.trips:
                continue
            self.assertEqual(
                exported[vehicle_id],
                tuple(
                    trip.stop_sequence
                    for trip in vehicle_evaluation.trips
                ),
            )

    def test_infeasible_customer_returns_structured_result(self) -> None:
        customers = dict(self.instance.customers)
        customers["G1"] = replace(
            customers["G1"],
            hazard_class="UNSUPPORTED",
        )

        run = construct_initial_solution(
            replace(self.instance, customers=customers)
        )

        self.assertEqual(run.status, "infeasible")
        self.assertFalse(run.evaluation.feasible)
        self.assertIn("G1", run.evaluation.unserved_customers)
        self.assertTrue(
            any(
                "G1 has no feasible single-customer trip" in reason
                for reason in run.evaluation.reasons
            )
        )

    def test_malformed_input_returns_input_data_error(self) -> None:
        customers = dict(self.instance.customers)
        customers["G1"] = replace(
            customers["G1"],
            demand_kg=-1.0,
        )

        run = construct_initial_solution(
            replace(self.instance, customers=customers)
        )

        self.assertEqual(run.status, "input_data_error")
        self.assertFalse(run.evaluation.feasible)
        self.assertIn(
            "demand_kg must be positive",
            run.evaluation.reasons[0],
        )

    def test_non_finite_numeric_inputs_return_input_data_error(self) -> None:
        legs = dict(self.instance.legs)
        vehicles = dict(self.instance.vehicles)
        chargers = dict(self.instance.chargers)
        cases = {
            "customer demand": replace(
                self.instance,
                customers={
                    **self.instance.customers,
                    "G1": replace(
                        self.instance.customers["G1"],
                        demand_kg=float("nan"),
                    ),
                },
            ),
            "edge distance": replace(
                self.instance,
                legs={
                    **legs,
                    (DEPOT, "G1"): replace(
                        legs[(DEPOT, "G1")],
                        distance_km=float("inf"),
                    ),
                },
            ),
            "edge travel time": replace(
                self.instance,
                legs={
                    **legs,
                    (DEPOT, "G1"): replace(
                        legs[(DEPOT, "G1")],
                        travel_minutes=float("nan"),
                    ),
                },
            ),
            "battery": replace(
                self.instance,
                vehicles={
                    **vehicles,
                    "TRUCK_G_1": replace(
                        vehicles["TRUCK_G_1"],
                        initial_battery_kwh=float("-inf"),
                    ),
                },
            ),
            "station power": replace(
                self.instance,
                chargers={
                    **chargers,
                    "FAST_CHARGE": replace(
                        chargers["FAST_CHARGE"],
                        power_kw=float("nan"),
                    ),
                },
            ),
            "objective weight": replace(
                self.instance,
                weights=ObjectiveWeights(
                    risk=float("nan"),
                    cost=0.35,
                    time=0.0,
                ),
            ),
            "branch limit": replace(
                self.instance,
                max_charging_branch_evaluations=1.5,
            ),
        }

        for label, instance in cases.items():
            with self.subTest(label=label):
                run = construct_initial_solution(instance)
                self.assertEqual(run.status, "input_data_error")
                self.assertFalse(run.evaluation.feasible)

    def test_mapping_key_mismatch_returns_input_data_error(self) -> None:
        customers = dict(self.instance.customers)
        customers["WRONG_KEY"] = customers.pop("G1")

        run = construct_initial_solution(
            replace(self.instance, customers=customers)
        )

        self.assertEqual(run.status, "input_data_error")
        self.assertIn(
            "does not match customer_id",
            run.evaluation.reasons[0],
        )

    def test_duplicate_charger_candidate_returns_input_data_error(self) -> None:
        candidates = dict(self.instance.customer_charger_candidates)
        candidates["G1"] = ("FAST_CHARGE", "FAST_CHARGE")

        run = construct_initial_solution(
            replace(
                self.instance,
                customer_charger_candidates=candidates,
            )
        )

        self.assertEqual(run.status, "input_data_error")
        self.assertIn(
            "charging candidates contain duplicates",
            run.evaluation.reasons[0],
        )

    def test_inactive_risk_scale_disables_risk_term(self) -> None:
        scales = ObjectiveScales(
            risk=1.0,
            cost=100.0,
            time=1.0,
            risk_active=False,
        )

        evaluation = evaluate_solution(
            self.instance,
            {"TRUCK_G_1": [["G1"]]},
            scales,
            require_all_customers=False,
        )

        self.assertGreater(evaluation.total_risk, 0.0)
        self.assertAlmostEqual(
            evaluation.objective,
            self.instance.weights.cost
            * evaluation.total_cost
            / scales.cost,
        )

    def test_failed_evaluation_totals_match_retained_trips(self) -> None:
        vehicle = self.instance.vehicles["TRUCK_G_1"]

        evaluation = evaluate_vehicle_schedule(
            self.instance,
            vehicle,
            [["G1"], ["C1"]],
        )

        self.assertFalse(evaluation.feasible)
        self.assertEqual(len(evaluation.trips), 1)
        self.assertAlmostEqual(
            evaluation.total_risk,
            sum(trip.total_risk for trip in evaluation.trips),
        )
        self.assertAlmostEqual(
            evaluation.road_operating_cost,
            sum(
                trip.road_operating_cost
                for trip in evaluation.trips
            ),
        )
        self.assertAlmostEqual(
            evaluation.total_cost,
            evaluation.activation_cost
            + evaluation.trip_cost
            + evaluation.road_operating_cost
            + evaluation.station_charging_cost
            + evaluation.end_of_day_recharge_cost,
        )
        self.assertAlmostEqual(
            evaluation.end_of_day_recharge_kwh,
            vehicle.initial_battery_kwh
            - evaluation.final_battery_kwh,
        )
        self.assertAlmostEqual(
            evaluation.end_of_day_recharge_cost,
            evaluation.end_of_day_recharge_kwh
            * self.instance.depot_energy_price_per_kwh,
        )

    def test_partial_infeasible_result_keeps_rejection_reasons(self) -> None:
        customers = {
            customer_id: self.instance.customers[customer_id]
            for customer_id in ("G1", "C1")
        }
        vehicle = replace(
            self.instance.vehicles["TRUCK_G_1"],
            compatible_classes=("3", "2 (TOC)"),
        )
        instance = replace(
            self.instance,
            customers=customers,
            vehicles={vehicle.vehicle_id: vehicle},
            customer_charger_candidates={
                customer_id: ("FAST_CHARGE",)
                for customer_id in customers
            },
        )

        run = construct_initial_solution(instance)

        self.assertEqual(run.status, "partial_infeasible")
        self.assertTrue(run.evaluation.unserved_customers)
        self.assertTrue(
            any(
                reason.startswith("Customer ")
                and "rejected:" in reason
                and "class change during planning day" in reason
                for reason in run.evaluation.reasons
            )
        )

    def test_insertion_search_limit_is_preserved_by_construction(self) -> None:
        customers = {
            customer_id: self.instance.customers[customer_id]
            for customer_id in ("G1", "G2")
        }
        vehicle = self.instance.vehicles["TRUCK_G_1"]
        instance = replace(
            self.instance,
            customers=customers,
            vehicles={vehicle.vehicle_id: vehicle},
            customer_charger_candidates={
                customer_id: ("FAST_CHARGE",)
                for customer_id in customers
            },
        )

        def controlled_evaluation(
            controlled_instance,
            schedules,
            scales,
            *,
            require_all_customers,
            _charging_branch_counter=None,
        ):
            result = evaluate_solution(
                controlled_instance,
                schedules,
                scales,
                require_all_customers=require_all_customers,
                _charging_branch_counter=_charging_branch_counter,
            )
            if require_all_customers:
                return result

            trips = [
                list(trip)
                for trip in schedules.get(vehicle.vehicle_id, [])
            ]
            if len(trips) == 1 and len(trips[0]) == 1:
                rank = 1.0 if trips[0][0] == "G1" else 2.0
                return replace(
                    result,
                    feasible=True,
                    reasons=tuple(),
                    objective=rank,
                    total_risk=rank,
                    total_cost=rank,
                    total_time_minutes=rank,
                )
            if len(trips) == 1 and len(trips[0]) == 2:
                return replace(
                    result,
                    feasible=False,
                    reasons=(
                        "TRUCK_G_1: charging_search_incomplete "
                        "during insertion.",
                    ),
                )
            if len(trips) == 2:
                return replace(
                    result,
                    feasible=False,
                    reasons=(
                        "TRUCK_G_1: shift_infeasible while travelling.",
                    ),
                )
            return result

        with patch(
            "heuristics.multi_customer_heuristic_toy.evaluate_solution",
            side_effect=controlled_evaluation,
        ):
            run = construct_initial_solution(instance)

        self.assertEqual(run.status, "search_limit_reached")
        customer_diagnostic = next(
            reason
            for reason in run.evaluation.reasons
            if reason.startswith("Customer G2 rejected:")
        )
        self.assertIn(
            "charging_search_incomplete during insertion",
            customer_diagnostic,
        )
        self.assertIn(
            "shift_infeasible while travelling",
            customer_diagnostic,
        )

    def test_feasible_unselected_seed_clears_stale_insertion_reason(
        self,
    ) -> None:
        customers = {
            customer_id: self.instance.customers[customer_id]
            for customer_id in ("G1", "G2", "G3")
        }
        vehicle = self.instance.vehicles["TRUCK_G_1"]
        instance = replace(
            self.instance,
            customers=customers,
            vehicles={vehicle.vehicle_id: vehicle},
            customer_charger_candidates={
                customer_id: ("FAST_CHARGE",)
                for customer_id in customers
            },
        )

        def controlled_evaluation(
            controlled_instance,
            schedules,
            scales,
            *,
            require_all_customers,
            _charging_branch_counter=None,
        ):
            result = evaluate_solution(
                controlled_instance,
                schedules,
                scales,
                require_all_customers=require_all_customers,
                _charging_branch_counter=_charging_branch_counter,
            )
            if require_all_customers:
                return result

            trips = [
                list(trip)
                for trip in schedules.get(vehicle.vehicle_id, [])
            ]
            if len(trips) == 1 and len(trips[0]) == 1:
                rank = {
                    "G1": 1.0,
                    "G2": 2.0,
                    "G3": 3.0,
                }[trips[0][0]]
                return replace(
                    result,
                    feasible=True,
                    reasons=tuple(),
                    objective=rank,
                    total_risk=rank,
                    total_cost=rank,
                    total_time_minutes=rank,
                )
            if len(trips) == 1 and len(trips[0]) == 2:
                return replace(
                    result,
                    feasible=False,
                    reasons=(
                        "TRUCK_G_1: charging_search_incomplete "
                        "during insertion.",
                    ),
                )
            if len(trips) == 2 and all(
                len(trip) == 1 for trip in trips
            ):
                rank = 2.0 if trips[-1][0] == "G2" else 3.0
                return replace(
                    result,
                    feasible=True,
                    reasons=tuple(),
                    objective=rank,
                    total_risk=rank,
                    total_cost=rank,
                    total_time_minutes=rank,
                )
            if (
                len(trips) == 2
                and len(trips[0]) == 1
                and len(trips[1]) == 2
            ):
                return replace(
                    result,
                    feasible=False,
                    reasons=(
                        "TRUCK_G_1: shift_infeasible while travelling.",
                    ),
                )
            if len(trips) == 3:
                return replace(
                    result,
                    feasible=False,
                    reasons=(
                        "TRUCK_G_1: shift_infeasible while travelling.",
                    ),
                )
            return result

        with patch(
            "heuristics.multi_customer_heuristic_toy.evaluate_solution",
            side_effect=controlled_evaluation,
        ):
            run = construct_initial_solution(instance)

        self.assertEqual(run.status, "partial_infeasible")
        customer_diagnostic = next(
            reason
            for reason in run.evaluation.reasons
            if reason.startswith("Customer G3 rejected:")
        )
        self.assertNotIn(
            "charging_search_incomplete",
            customer_diagnostic,
        )
        self.assertIn(
            "shift_infeasible while travelling",
            customer_diagnostic,
        )

    def test_future_missing_path_keeps_structural_reason(self) -> None:
        legs = dict(self.instance.legs)
        legs.pop(("G2", DEPOT))
        candidates = dict(self.instance.customer_charger_candidates)
        candidates["G1"] = tuple()
        instance = replace(
            self.instance,
            legs=legs,
            customer_charger_candidates=candidates,
        )

        evaluation = evaluate_vehicle_schedule(
            instance,
            instance.vehicles["TRUCK_G_1"],
            [["G1", "G2"]],
        )

        self.assertFalse(evaluation.feasible)
        self.assertTrue(
            any(
                "no_legal_path G2->DEPOT" in reason
                for reason in evaluation.reasons
            )
        )
        self.assertFalse(
            any(
                "charging_infeasible before G1->G2" in reason
                for reason in evaluation.reasons
            )
        )

    def test_future_time_window_keeps_time_reason(self) -> None:
        customers = dict(self.instance.customers)
        customers["G2"] = replace(
            customers["G2"],
            earliest_minute=0.0,
            latest_minute=0.0,
        )
        candidates = dict(self.instance.customer_charger_candidates)
        candidates["G1"] = tuple()
        instance = replace(
            self.instance,
            customers=customers,
            customer_charger_candidates=candidates,
        )

        evaluation = evaluate_vehicle_schedule(
            instance,
            instance.vehicles["TRUCK_G_1"],
            [["G1", "G2"]],
        )

        self.assertFalse(evaluation.feasible)
        self.assertTrue(
            any(
                "time_window_infeasible at G2" in reason
                for reason in evaluation.reasons
            )
        )


if __name__ == "__main__":
    unittest.main()
