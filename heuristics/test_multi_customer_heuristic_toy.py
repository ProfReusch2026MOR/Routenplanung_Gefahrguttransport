from dataclasses import replace
import time
import unittest
from unittest.mock import patch

from heuristics.multi_customer_heuristic_toy import (
    ChargingStation,
    DEPOT,
    Leg,
    ObjectiveScales,
    ObjectiveWeights,
    VND_NEIGHBORHOOD_ORDER,
    build_toy_instance,
    construct_initial_solution,
    evaluate_solution,
    evaluate_vehicle_schedule,
    improve_solution_vnd,
    improve_solution_vns,
    repair_partial_solution_depth_one,
    repair_partial_solution_depth_two,
    solver_warm_start_routes,
    summarize_depth_two_repair_run,
    summarize_repair_run,
)


class MultiCustomerHeuristicToyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.instance = build_toy_instance()

    def _partial_construction_without_customer(self, customer_id):
        construction = construct_initial_solution(self.instance)
        schedules = {
            vehicle_id: [list(trip) for trip in trips]
            for vehicle_id, trips
            in construction.evaluation.schedules.items()
        }
        removed = False
        for trips in schedules.values():
            for trip in list(trips):
                if customer_id not in trip:
                    continue
                trip.remove(customer_id)
                removed = True
                if not trip:
                    trips.remove(trip)
        self.assertTrue(removed)
        evaluation = evaluate_solution(
            self.instance,
            schedules,
            construction.scales,
            require_all_customers=False,
        )
        self.assertTrue(evaluation.feasible)
        self.assertIn(customer_id, evaluation.unserved_customers)
        return replace(
            construction,
            status="partial_infeasible",
            evaluation=evaluation,
        )

    def _vnd_from_schedules(self, schedules):
        construction = construct_initial_solution(self.instance)
        evaluation = evaluate_solution(
            self.instance,
            schedules,
            construction.scales,
            require_all_customers=True,
        )
        self.assertTrue(evaluation.feasible)
        initial_run = replace(
            construction,
            evaluation=evaluation,
            runtime_seconds=0.0,
        )
        return initial_run, improve_solution_vnd(
            self.instance,
            initial_run,
        )

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

    def test_regret_2_reserves_the_only_compatible_vehicle(self) -> None:
        customers = {
            customer_id: self.instance.customers[customer_id]
            for customer_id in ("G1", "C1")
        }
        flexible_vehicle = replace(
            self.instance.vehicles["TRUCK_G_1"],
            compatible_classes=("3", "2 (TOC)"),
            activation_cost=0.0,
            trip_cost=0.0,
            road_cost_per_km=1.0,
            energy_kwh_per_km=0.1,
        )
        fallback_vehicle = replace(
            self.instance.vehicles["TRUCK_G_BACKUP"],
            compatible_classes=("3",),
            activation_cost=100.0,
            trip_cost=0.0,
            road_cost_per_km=1.0,
            energy_kwh_per_km=0.1,
        )
        allowed_classes = ("3", "2 (TOC)")
        legs = {
            (DEPOT, "G1"): Leg(
                DEPOT, "G1", 0.5, 0.5, 0.0, allowed_classes
            ),
            ("G1", DEPOT): Leg(
                "G1", DEPOT, 0.5, 0.5, 0.0, allowed_classes
            ),
            (DEPOT, "C1"): Leg(
                DEPOT, "C1", 4.0, 4.0, 0.0, allowed_classes
            ),
            ("C1", DEPOT): Leg(
                "C1", DEPOT, 4.0, 4.0, 0.0, allowed_classes
            ),
            ("G1", "C1"): Leg(
                "G1", "C1", 4.0, 4.0, 0.0, allowed_classes
            ),
            ("C1", "G1"): Leg(
                "C1", "G1", 4.0, 4.0, 0.0, allowed_classes
            ),
        }
        instance = replace(
            self.instance,
            customers=customers,
            vehicles={
                flexible_vehicle.vehicle_id: flexible_vehicle,
                fallback_vehicle.vehicle_id: fallback_vehicle,
            },
            customer_charger_candidates={
                customer_id: tuple() for customer_id in customers
            },
            legs=legs,
            weights=ObjectiveWeights(risk=0.0, cost=1.0, time=0.0),
        )

        best_insertion = construct_initial_solution(instance)
        regret_2 = construct_initial_solution(
            instance,
            construction_strategy="regret_2",
        )
        hardest_first = construct_initial_solution(
            instance,
            construction_strategy="hardest_first",
        )
        first_repair = repair_partial_solution_depth_one(
            instance,
            best_insertion,
        )
        second_repair = repair_partial_solution_depth_one(
            instance,
            best_insertion,
        )

        self.assertEqual(best_insertion.status, "partial_infeasible")
        self.assertEqual(best_insertion.evaluation.unserved_customers, ("C1",))
        self.assertEqual(regret_2.status, "feasible")
        self.assertEqual(regret_2.construction_strategy, "regret_2")
        self.assertEqual(regret_2.evaluation.unserved_customers, tuple())
        self.assertEqual(
            regret_2.evaluation.schedules["TRUCK_G_1"],
            (("C1",),),
        )
        self.assertEqual(
            regret_2.evaluation.schedules["TRUCK_G_BACKUP"],
            (("G1",),),
        )
        self.assertEqual(hardest_first.status, "feasible")
        self.assertEqual(
            hardest_first.evaluation.unserved_customers,
            tuple(),
        )
        self.assertEqual(
            hardest_first.evaluation.schedules,
            regret_2.evaluation.schedules,
        )
        self.assertEqual(first_repair.status, "feasible")
        self.assertEqual(first_repair.evaluation.unserved_customers, tuple())
        self.assertEqual(
            first_repair.evaluation.schedules,
            second_repair.evaluation.schedules,
        )
        self.assertEqual(
            first_repair.accepted_moves,
            second_repair.accepted_moves,
        )
        self.assertEqual(len(first_repair.accepted_moves), 1)
        self.assertEqual(
            first_repair.accepted_moves[0].inserted_customer,
            "C1",
        )
        self.assertEqual(
            first_repair.accepted_moves[0].ejected_customer,
            "G1",
        )

    def test_vnd_improves_suboptimal_schedule_deterministically(self) -> None:
        schedules = {
            "TRUCK_G_1": [["G1", "G2"], ["G3", "G4"]],
            "TRUCK_C_1": [["C2", "C1"]],
            "TRUCK_G_BACKUP": [],
        }
        initial_run, first = self._vnd_from_schedules(schedules)
        second = improve_solution_vnd(self.instance, initial_run)

        self.assertEqual(first.status, "locally_optimal")
        self.assertTrue(first.evaluation.feasible)
        self.assertEqual(first.evaluation.unserved_customers, tuple())
        self.assertLess(
            first.evaluation.objective,
            first.initial_evaluation.objective,
        )
        self.assertEqual(
            first.evaluation.schedules,
            second.evaluation.schedules,
        )
        self.assertEqual(first.accepted_moves, second.accepted_moves)
        self.assertEqual(
            first.evaluated_candidates,
            second.evaluated_candidates,
        )
        self.assertTrue(first.accepted_moves)
        for move in first.accepted_moves:
            self.assertIn(move.neighborhood, VND_NEIGHBORHOOD_ORDER)
            self.assertLess(move.objective_after, move.objective_before)

    def test_depth_one_repair_can_apply_two_consecutive_moves(self) -> None:
        customer_ids = ("G1", "G2", "C1", "C2")
        customers = {
            customer_id: replace(
                self.instance.customers[customer_id],
                demand_kg=4_000.0,
                service_minutes=5.0,
                earliest_minute=0.0,
                latest_minute=60.0,
            )
            for customer_id in customer_ids
        }
        base_vehicle = self.instance.vehicles["TRUCK_G_1"]

        def vehicle(
            vehicle_id,
            compatible_classes,
            activation_cost,
        ):
            return replace(
                base_vehicle,
                vehicle_id=vehicle_id,
                capacity_kg=5_000.0,
                energy_kwh_per_km=0.1,
                compatible_classes=compatible_classes,
                activation_cost=activation_cost,
                trip_cost=0.0,
                road_cost_per_km=1.0,
                shift_start_minute=0.0,
                shift_end_minute=60.0,
                initial_load_minutes=0.0,
                reload_minutes=100.0,
                max_daily_working_minutes=60.0,
                solver_name=vehicle_id,
            )

        vehicles = {
            item.vehicle_id: item
            for item in (
                vehicle("FLEX_1", ("3", "2 (TOC)"), 0.0),
                vehicle("FLEX_2", ("3", "2 (TOC)"), 0.0),
                vehicle("BACKUP_1", ("3",), 100.0),
                vehicle("BACKUP_2", ("3",), 100.0),
            )
        }
        positions = {
            DEPOT: 0.0,
            "G1": 0.5,
            "G2": 0.7,
            "C1": 4.0,
            "C2": 5.0,
        }
        allowed_classes = ("3", "2 (TOC)")
        legs = {
            (from_stop, to_stop): Leg(
                from_stop=from_stop,
                to_stop=to_stop,
                distance_km=abs(
                    positions[from_stop] - positions[to_stop]
                ),
                travel_minutes=abs(
                    positions[from_stop] - positions[to_stop]
                ),
                base_risk_rate_per_km=0.0,
                allowed_classes=allowed_classes,
            )
            for from_stop in positions
            for to_stop in positions
            if from_stop != to_stop
        }
        instance = replace(
            self.instance,
            customers=customers,
            vehicles=vehicles,
            chargers={},
            customer_charger_candidates={
                customer_id: tuple() for customer_id in customers
            },
            legs=legs,
            break_nodes=(DEPOT,),
            weights=ObjectiveWeights(risk=0.0, cost=1.0, time=0.0),
        )
        construction = construct_initial_solution(instance)

        repair = repair_partial_solution_depth_one(
            instance,
            construction,
        )

        self.assertEqual(
            construction.status,
            "partial_infeasible",
            construction.evaluation.reasons,
        )
        self.assertEqual(len(construction.evaluation.served_customers), 2)
        self.assertEqual(repair.status, "feasible")
        self.assertEqual(repair.evaluation.unserved_customers, tuple())
        self.assertEqual(len(repair.accepted_moves), 2)

    def test_depth_one_reports_candidate_limit_and_configuration(
        self,
    ) -> None:
        partial = self._partial_construction_without_customer("G4")

        run = repair_partial_solution_depth_one(
            self.instance,
            partial,
            max_candidate_evaluations=1,
            max_seconds=9,
            max_primary_candidates_per_ejection=2,
        )

        self.assertEqual(run.status, "search_limit_reached")
        self.assertEqual(run.stop_reason, "candidate_limit")
        self.assertEqual(run.evaluated_candidates, 1)
        self.assertEqual(run.max_candidate_evaluations, 1)
        self.assertEqual(run.max_seconds, 9.0)
        self.assertEqual(run.max_primary_candidates_per_ejection, 2)
        summary = summarize_repair_run(run)
        self.assertIn("stop_reason=candidate_limit", summary)
        self.assertIn("max_candidate_evaluations=1", summary)
        self.assertIn(
            "max_primary_candidates_per_ejection=2",
            summary,
        )

    def test_depth_two_reports_time_limit_and_configuration(self) -> None:
        partial = self._partial_construction_without_customer("G4")

        with patch(
            "heuristics.multi_customer_heuristic_toy.time.perf_counter",
            side_effect=(0.0, 2.0, 2.0),
        ):
            run = repair_partial_solution_depth_two(
                self.instance,
                partial,
                max_candidate_evaluations=11,
                max_seconds=1,
                max_primary_candidates=7,
                max_first_reinsertions=2,
            )

        self.assertEqual(run.status, "search_limit_reached")
        self.assertEqual(run.stop_reason, "time_limit")
        self.assertEqual(run.evaluated_candidates, 0)
        self.assertEqual(run.max_candidate_evaluations, 11)
        self.assertEqual(run.max_seconds, 1.0)
        self.assertEqual(run.max_primary_candidates, 7)
        self.assertEqual(run.max_first_reinsertions, 2)
        summary = summarize_depth_two_repair_run(run)
        self.assertIn("stop_reason=time_limit", summary)
        self.assertIn("max_primary_candidates=7", summary)
        self.assertIn("max_first_reinsertions=2", summary)

    def test_depth_one_reports_charging_search_incomplete_stop_reason(
        self,
    ) -> None:
        partial = self._partial_construction_without_customer("G4")

        def incomplete_candidate(
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
            if (
                not require_all_customers
                and schedules != partial.evaluation.schedules
            ):
                return replace(
                    result,
                    feasible=False,
                    reasons=(
                        "TRUCK_G_1: charging_search_incomplete "
                        "during repair candidate.",
                    ),
                )
            return result

        with patch(
            "heuristics.multi_customer_heuristic_toy.evaluate_solution",
            side_effect=incomplete_candidate,
        ):
            run = repair_partial_solution_depth_one(
                self.instance,
                partial,
            )

        self.assertEqual(run.status, "search_limit_reached")
        self.assertEqual(
            run.stop_reason,
            "charging_search_incomplete",
        )
        self.assertGreater(run.incomplete_candidates, 0)
        self.assertEqual(
            run.incomplete_candidates,
            run.evaluated_candidates,
        )

    def test_depth_two_repairs_case_that_depth_one_cannot(self) -> None:
        customer_ids = ("G1", "G2", "C1")
        customers = {
            customer_id: replace(
                self.instance.customers[customer_id],
                demand_kg=4_000.0,
                service_minutes=5.0,
                earliest_minute=0.0,
                latest_minute=100.0,
            )
            for customer_id in customer_ids
        }
        base_vehicle = self.instance.vehicles["TRUCK_G_1"]

        def vehicle(
            vehicle_id,
            capacity_kg,
            compatible_classes,
            activation_cost,
            road_cost_per_km=1.0,
            shift_end_minute=100.0,
        ):
            return replace(
                base_vehicle,
                vehicle_id=vehicle_id,
                capacity_kg=capacity_kg,
                energy_kwh_per_km=0.1,
                compatible_classes=compatible_classes,
                activation_cost=activation_cost,
                trip_cost=0.0,
                road_cost_per_km=road_cost_per_km,
                shift_start_minute=0.0,
                shift_end_minute=shift_end_minute,
                initial_load_minutes=0.0,
                reload_minutes=5.0,
                max_daily_working_minutes=100.0,
                solver_name=vehicle_id,
            )

        vehicles = {
            item.vehicle_id: item
            for item in (
                vehicle(
                    "FLEX",
                    8_000.0,
                    ("3", "2 (TOC)"),
                    0.0,
                ),
                vehicle(
                    "BACKUP_1",
                    4_000.0,
                    ("3",),
                    100.0,
                    shift_end_minute=7.0,
                ),
                vehicle(
                    "BACKUP_2",
                    4_000.0,
                    ("3",),
                    100.0,
                    road_cost_per_km=10.0,
                    shift_end_minute=7.0,
                ),
            )
        }
        positions = {
            DEPOT: 0.0,
            "G1": 0.5,
            "G2": 0.7,
            "C1": 4.0,
        }
        allowed_classes = ("3", "2 (TOC)")
        legs = {
            (from_stop, to_stop): Leg(
                from_stop=from_stop,
                to_stop=to_stop,
                distance_km=abs(
                    positions[from_stop] - positions[to_stop]
                ),
                travel_minutes=abs(
                    positions[from_stop] - positions[to_stop]
                ),
                base_risk_rate_per_km=0.0,
                allowed_classes=allowed_classes,
            )
            for from_stop in positions
            for to_stop in positions
            if from_stop != to_stop
        }
        instance = replace(
            self.instance,
            customers=customers,
            vehicles=vehicles,
            chargers={},
            customer_charger_candidates={
                customer_id: tuple() for customer_id in customers
            },
            legs=legs,
            break_nodes=(DEPOT,),
            weights=ObjectiveWeights(risk=0.0, cost=1.0, time=0.0),
        )
        construction = construct_initial_solution(instance)
        depth_one = repair_partial_solution_depth_one(
            instance,
            construction,
        )

        depth_two = repair_partial_solution_depth_two(
            instance,
            depth_one,
            max_first_reinsertions=1,
        )
        vnd = improve_solution_vnd(
            instance,
            depth_two,
        )

        self.assertEqual(construction.status, "partial_infeasible")
        self.assertEqual(
            construction.evaluation.unserved_customers,
            ("C1",),
        )
        self.assertFalse(depth_one.evaluation.feasible)
        self.assertEqual(depth_two.status, "feasible")
        self.assertEqual(depth_two.evaluation.unserved_customers, tuple())
        self.assertEqual(len(depth_two.accepted_moves), 1)
        self.assertEqual(
            set(depth_two.accepted_moves[0].ejected_customers),
            {"G1", "G2"},
        )
        self.assertEqual(
            depth_two.accepted_moves[0].reinsertion_order,
            ("G2", "G1"),
        )
        self.assertEqual(
            depth_two.evaluation.schedules["BACKUP_1"],
            (("G2",),),
        )
        self.assertEqual(
            depth_two.evaluation.schedules["BACKUP_2"],
            (("G1",),),
        )
        self.assertTrue(vnd.evaluation.feasible)
        self.assertEqual(vnd.evaluation.unserved_customers, tuple())

    def test_vnd_does_not_worsen_locally_optimal_construction(self) -> None:
        construction = construct_initial_solution(self.instance)

        run = improve_solution_vnd(self.instance, construction)

        self.assertEqual(run.status, "locally_optimal")
        self.assertTrue(run.evaluation.feasible)
        self.assertLessEqual(
            run.evaluation.objective,
            construction.evaluation.objective,
        )
        self.assertEqual(
            run.evaluation.served_customers,
            construction.evaluation.served_customers,
        )
        self.assertEqual(run.accepted_moves, tuple())
        self.assertEqual(run.incomplete_candidates, 0)
        self.assertEqual(run.incomplete_neighborhoods, tuple())
        self.assertEqual(
            run.neighborhood_passes,
            len(VND_NEIGHBORHOOD_ORDER),
        )

    def test_vnd_reports_incomplete_candidate_search(self) -> None:
        construction = construct_initial_solution(self.instance)

        def incomplete_evaluation(*args, **kwargs):
            return replace(
                construction.evaluation,
                feasible=False,
                reasons=(
                    "TRUCK_G_1: charging_search_incomplete "
                    "during VND candidate.",
                ),
            )

        with patch(
            "heuristics.multi_customer_heuristic_toy.evaluate_solution",
            side_effect=incomplete_evaluation,
        ):
            run = improve_solution_vnd(self.instance, construction)

        self.assertEqual(run.status, "search_limit_reached")
        self.assertIs(run.evaluation, construction.evaluation)
        self.assertEqual(run.accepted_moves, tuple())
        self.assertGreater(run.incomplete_candidates, 0)
        self.assertEqual(
            run.incomplete_candidates,
            run.evaluated_candidates,
        )
        self.assertEqual(
            run.incomplete_neighborhoods,
            VND_NEIGHBORHOOD_ORDER,
        )

    def test_vnd_resets_incomplete_evidence_after_improvement(self) -> None:
        schedules = {
            "TRUCK_G_1": [["G1", "G2"], ["G3", "G4"]],
            "TRUCK_C_1": [["C2", "C1"]],
            "TRUCK_G_BACKUP": [],
        }
        initial_run, _ = self._vnd_from_schedules(schedules)
        search_state = {"incomplete_injected": False}

        def controlled_evaluation(
            controlled_instance,
            candidate_schedules,
            scales,
            *,
            require_all_customers,
            _charging_branch_counter=None,
        ):
            result = evaluate_solution(
                controlled_instance,
                candidate_schedules,
                scales,
                require_all_customers=require_all_customers,
                _charging_branch_counter=_charging_branch_counter,
            )
            if not search_state["incomplete_injected"]:
                search_state["incomplete_injected"] = True
                return replace(
                    result,
                    feasible=False,
                    reasons=(
                        "TRUCK_G_1: charging_search_incomplete "
                        "during an earlier VND cycle.",
                    ),
                )
            return result

        with patch(
            "heuristics.multi_customer_heuristic_toy.evaluate_solution",
            side_effect=controlled_evaluation,
        ):
            run = improve_solution_vnd(self.instance, initial_run)

        self.assertTrue(run.accepted_moves)
        self.assertEqual(run.status, "locally_optimal")
        self.assertEqual(run.incomplete_candidates, 0)
        self.assertEqual(run.incomplete_neighborhoods, tuple())

    def test_vnd_inter_trip_relocate_removes_empty_trip(self) -> None:
        schedules = {
            "TRUCK_G_1": [["G1", "G2"], ["G4", "G3"]],
            "TRUCK_C_1": [["C1"], ["C2"]],
            "TRUCK_G_BACKUP": [],
        }

        _, run = self._vnd_from_schedules(schedules)

        self.assertEqual(
            run.evaluation.schedules["TRUCK_C_1"],
            (("C1", "C2"),),
        )
        self.assertTrue(
            any(
                move.neighborhood == "inter_trip_relocate"
                for move in run.accepted_moves
            )
        )

    def test_vnd_inter_trip_swap_can_repartition_customers(self) -> None:
        schedules = {
            "TRUCK_G_1": [["G1", "G3"], ["G2", "G4"]],
            "TRUCK_C_1": [["C1", "C2"]],
            "TRUCK_G_BACKUP": [],
        }

        _, run = self._vnd_from_schedules(schedules)

        self.assertTrue(
            any(
                move.neighborhood == "inter_trip_swap"
                for move in run.accepted_moves
            )
        )
        self.assertEqual(
            set(run.evaluation.served_customers),
            set(self.instance.customers),
        )

    def test_vnd_trip_reassignment_can_deactivate_expensive_vehicle(
        self,
    ) -> None:
        schedules = {
            "TRUCK_G_1": [["G4", "G3"]],
            "TRUCK_C_1": [["C1", "C2"]],
            "TRUCK_G_BACKUP": [["G1", "G2"]],
        }
        initial_run, run = self._vnd_from_schedules(schedules)

        self.assertTrue(
            any(
                move.neighborhood == "trip_reassignment"
                for move in run.accepted_moves
            )
        )
        self.assertEqual(
            run.evaluation.schedules["TRUCK_G_BACKUP"],
            tuple(),
        )
        self.assertLess(
            run.evaluation.total_cost,
            initial_run.evaluation.total_cost,
        )

    def test_vnd_does_not_search_an_infeasible_initial_solution(self) -> None:
        customers = dict(self.instance.customers)
        customers["G1"] = replace(
            customers["G1"],
            hazard_class="UNSUPPORTED",
        )
        infeasible_instance = replace(
            self.instance,
            customers=customers,
        )
        construction = construct_initial_solution(infeasible_instance)

        run = improve_solution_vnd(infeasible_instance, construction)

        self.assertEqual(run.status, "initial_solution_infeasible")
        self.assertIs(run.evaluation, construction.evaluation)
        self.assertEqual(run.accepted_moves, tuple())
        self.assertEqual(run.evaluated_candidates, 0)
        self.assertEqual(run.incomplete_candidates, 0)
        self.assertEqual(run.incomplete_neighborhoods, tuple())
        self.assertEqual(run.neighborhood_passes, 0)

    def test_vnd_rejects_invalid_neighborhood_limit(self) -> None:
        construction = construct_initial_solution(self.instance)

        for invalid_limit in (0, -1, 1.5, True):
            with self.subTest(invalid_limit=invalid_limit):
                with self.assertRaises(ValueError):
                    improve_solution_vnd(
                        self.instance,
                        construction,
                        max_neighborhood_passes=invalid_limit,
                    )

        for invalid_deadline in (True, float("inf"), "later"):
            with self.subTest(invalid_deadline=invalid_deadline):
                with self.assertRaises(ValueError):
                    improve_solution_vnd(
                        self.instance,
                        construction,
                        deadline=invalid_deadline,
                    )

    def test_vnd_deadline_stops_after_current_candidate(self) -> None:
        construction = construct_initial_solution(self.instance)

        def delayed_evaluation(*args, **kwargs):
            time.sleep(0.05)
            return evaluate_solution(*args, **kwargs)

        with patch(
            "heuristics.multi_customer_heuristic_toy.evaluate_solution",
            side_effect=delayed_evaluation,
        ) as mocked_evaluation:
            run = improve_solution_vnd(
                self.instance,
                construction,
                deadline=time.perf_counter() + 0.02,
            )

        self.assertEqual(run.status, "time_limit_reached")
        self.assertEqual(mocked_evaluation.call_count, 1)
        self.assertEqual(run.evaluated_candidates, 1)
        self.assertTrue(run.evaluation.feasible)

    def test_vns_is_deterministic_and_does_not_worsen_vnd(self) -> None:
        construction = construct_initial_solution(self.instance)
        vnd_run = improve_solution_vnd(self.instance, construction)

        first = improve_solution_vns(
            self.instance,
            vnd_run,
            random_seed=42,
            max_seconds=5.0,
        )
        second = improve_solution_vns(
            self.instance,
            vnd_run,
            random_seed=42,
            max_seconds=5.0,
        )

        self.assertEqual(first.status, "neighborhoods_exhausted")
        self.assertTrue(first.evaluation.feasible)
        self.assertLessEqual(
            first.evaluation.objective,
            vnd_run.evaluation.objective,
        )
        self.assertEqual(
            first.evaluation.schedules,
            second.evaluation.schedules,
        )
        self.assertEqual(
            first.accepted_improvements,
            second.accepted_improvements,
        )
        self.assertEqual(first.iterations, second.iterations)
        self.assertEqual(first.evaluated_shakes, second.evaluated_shakes)
        self.assertEqual(first.feasible_shakes, second.feasible_shakes)

    def test_vns_can_escape_a_vnd_local_optimum(self) -> None:
        schedules = {
            "TRUCK_G_1": [],
            "TRUCK_C_1": [["C1", "C2"]],
            "TRUCK_G_BACKUP": [["G1", "G2"], ["G4", "G3"]],
        }
        _, local_run = self._vnd_from_schedules(schedules)
        self.assertEqual(local_run.status, "locally_optimal")

        run = improve_solution_vns(
            self.instance,
            local_run,
            random_seed=3,
            max_iterations=30,
            max_seconds=5.0,
        )

        self.assertEqual(run.status, "neighborhoods_exhausted")
        self.assertTrue(run.accepted_improvements)
        self.assertLess(
            run.evaluation.objective,
            local_run.evaluation.objective,
        )
        self.assertEqual(
            run.evaluation.schedules["TRUCK_G_BACKUP"],
            tuple(),
        )
        improvement = run.accepted_improvements[0]
        self.assertEqual(improvement.neighborhood, "trip_reassignment")
        self.assertGreater(
            improvement.shaken_objective,
            improvement.objective_before,
        )
        self.assertLess(
            improvement.objective_after,
            improvement.objective_before,
        )

    def test_vns_reports_incomplete_shake_search(self) -> None:
        construction = construct_initial_solution(self.instance)
        vnd_run = improve_solution_vnd(self.instance, construction)

        def incomplete_evaluation(*args, **kwargs):
            return replace(
                vnd_run.evaluation,
                feasible=False,
                reasons=(
                    "TRUCK_G_1: charging_search_incomplete "
                    "during VNS shaking.",
                ),
            )

        with patch(
            "heuristics.multi_customer_heuristic_toy.evaluate_solution",
            side_effect=incomplete_evaluation,
        ):
            run = improve_solution_vns(
                self.instance,
                vnd_run,
                random_seed=42,
                max_seconds=5.0,
            )

        self.assertEqual(run.status, "search_limit_reached")
        self.assertIs(run.evaluation, vnd_run.evaluation)
        self.assertEqual(run.accepted_improvements, tuple())
        self.assertEqual(run.incomplete_shakes, run.evaluated_shakes)
        self.assertEqual(
            run.incomplete_neighborhoods,
            VND_NEIGHBORHOOD_ORDER,
        )
        self.assertEqual(run.vnd_runs, 0)

    def test_vns_reports_incomplete_local_search(self) -> None:
        construction = construct_initial_solution(self.instance)
        vnd_run = improve_solution_vnd(self.instance, construction)

        def incomplete_local_search(
            controlled_instance,
            shaken_run,
            *,
            max_neighborhood_passes,
            deadline,
        ):
            return replace(
                vnd_run,
                status="search_limit_reached",
                initial_evaluation=shaken_run.evaluation,
                evaluation=shaken_run.evaluation,
                accepted_moves=tuple(),
                evaluated_candidates=1,
                incomplete_candidates=1,
                incomplete_neighborhoods=("intra_trip_relocate",),
                neighborhood_passes=1,
            )

        with patch(
            "heuristics.multi_customer_heuristic_toy.improve_solution_vnd",
            side_effect=incomplete_local_search,
        ):
            run = improve_solution_vns(
                self.instance,
                vnd_run,
                random_seed=42,
                max_seconds=5.0,
            )

        self.assertEqual(run.status, "search_limit_reached")
        self.assertGreater(run.incomplete_local_searches, 0)
        self.assertIn(
            "intra_trip_relocate",
            run.incomplete_neighborhoods,
        )
        self.assertEqual(run.vnd_runs, run.feasible_shakes)

    def test_vns_preserves_initial_vnd_time_limit(self) -> None:
        construction = construct_initial_solution(self.instance)
        complete_vnd_run = improve_solution_vnd(
            self.instance,
            construction,
        )
        time_limited_vnd_run = replace(
            complete_vnd_run,
            status="time_limit_reached",
            incomplete_candidates=0,
            incomplete_neighborhoods=tuple(),
        )

        run = improve_solution_vns(
            self.instance,
            time_limited_vnd_run,
            random_seed=42,
            max_seconds=5.0,
        )

        self.assertEqual(run.status, "search_limit_reached")
        self.assertEqual(run.accepted_improvements, tuple())
        self.assertEqual(run.incomplete_local_searches, 1)
        self.assertEqual(
            run.incomplete_neighborhoods,
            ("initial_vnd",),
        )

    def test_vns_resets_incomplete_evidence_after_improvement(self) -> None:
        schedules = {
            "TRUCK_G_1": [],
            "TRUCK_C_1": [["C1", "C2"]],
            "TRUCK_G_BACKUP": [["G1", "G2"], ["G4", "G3"]],
        }
        _, local_run = self._vnd_from_schedules(schedules)
        search_state = {"incomplete_injected": False}

        def controlled_evaluation(
            controlled_instance,
            candidate_schedules,
            scales,
            *,
            require_all_customers,
            _charging_branch_counter=None,
        ):
            result = evaluate_solution(
                controlled_instance,
                candidate_schedules,
                scales,
                require_all_customers=require_all_customers,
                _charging_branch_counter=_charging_branch_counter,
            )
            if not search_state["incomplete_injected"]:
                search_state["incomplete_injected"] = True
                return replace(
                    result,
                    feasible=False,
                    reasons=(
                        "TRUCK_G_1: charging_search_incomplete "
                        "during an earlier VNS cycle.",
                    ),
                )
            return result

        with patch(
            "heuristics.multi_customer_heuristic_toy.evaluate_solution",
            side_effect=controlled_evaluation,
        ):
            run = improve_solution_vns(
                self.instance,
                local_run,
                random_seed=3,
                max_iterations=30,
                max_seconds=5.0,
            )

        self.assertTrue(run.accepted_improvements)
        self.assertEqual(run.status, "neighborhoods_exhausted")
        self.assertEqual(run.incomplete_shakes, 0)
        self.assertEqual(run.incomplete_local_searches, 0)
        self.assertEqual(run.incomplete_neighborhoods, tuple())

    def test_vns_does_not_start_vnd_after_shake_deadline(self) -> None:
        construction = construct_initial_solution(self.instance)
        vnd_run = improve_solution_vnd(self.instance, construction)

        def delayed_shake(*args, **kwargs):
            time.sleep(0.05)
            return vnd_run.evaluation

        with patch(
            "heuristics.multi_customer_heuristic_toy.evaluate_solution",
            side_effect=delayed_shake,
        ), patch(
            "heuristics.multi_customer_heuristic_toy.improve_solution_vnd",
        ) as nested_vnd:
            run = improve_solution_vns(
                self.instance,
                vnd_run,
                max_seconds=0.02,
            )

        self.assertEqual(run.status, "time_limit_reached")
        self.assertEqual(run.evaluated_shakes, 1)
        self.assertEqual(run.feasible_shakes, 1)
        self.assertEqual(run.vnd_runs, 0)
        nested_vnd.assert_not_called()

    def test_vns_honors_iteration_and_time_limits(self) -> None:
        construction = construct_initial_solution(self.instance)
        vnd_run = improve_solution_vnd(self.instance, construction)

        iteration_limited = improve_solution_vns(
            self.instance,
            vnd_run,
            max_iterations=1,
            max_seconds=5.0,
        )
        time_limited = improve_solution_vns(
            self.instance,
            vnd_run,
            max_seconds=1e-12,
        )

        self.assertEqual(
            iteration_limited.status,
            "iteration_limit_reached",
        )
        self.assertEqual(iteration_limited.iterations, 1)
        self.assertEqual(time_limited.status, "time_limit_reached")
        self.assertEqual(time_limited.iterations, 0)

    def test_vns_does_not_search_an_infeasible_initial_solution(self) -> None:
        customers = dict(self.instance.customers)
        customers["G1"] = replace(
            customers["G1"],
            hazard_class="UNSUPPORTED",
        )
        infeasible_instance = replace(
            self.instance,
            customers=customers,
        )
        construction = construct_initial_solution(infeasible_instance)
        vnd_run = improve_solution_vnd(
            infeasible_instance,
            construction,
        )

        run = improve_solution_vns(infeasible_instance, vnd_run)

        self.assertEqual(run.status, "initial_solution_infeasible")
        self.assertIs(run.evaluation, vnd_run.evaluation)
        self.assertEqual(run.iterations, 0)
        self.assertEqual(run.evaluated_shakes, 0)
        self.assertEqual(run.vnd_runs, 0)

    def test_vns_rejects_invalid_configuration(self) -> None:
        construction = construct_initial_solution(self.instance)
        vnd_run = improve_solution_vnd(self.instance, construction)
        invalid_configurations = (
            {"random_seed": True},
            {"random_seed": 1.5},
            {"max_iterations": 0},
            {"max_iterations": True},
            {"max_seconds": 0.0},
            {"max_seconds": float("inf")},
            {"max_vnd_neighborhood_passes": 0},
        )

        for configuration in invalid_configurations:
            with self.subTest(configuration=configuration):
                with self.assertRaises(ValueError):
                    improve_solution_vns(
                        self.instance,
                        vnd_run,
                        **configuration,
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
        malformed_instance = replace(
            self.instance,
            customers=customers,
        )

        construction = construct_initial_solution(
            malformed_instance
        )
        depth_one = repair_partial_solution_depth_one(
            malformed_instance,
            construction,
        )
        depth_two = repair_partial_solution_depth_two(
            malformed_instance,
            depth_one,
        )
        direct_depth_two = repair_partial_solution_depth_two(
            malformed_instance,
            construction,
        )

        self.assertEqual(construction.status, "input_data_error")
        self.assertFalse(construction.evaluation.feasible)
        self.assertIn(
            "demand_kg must be positive",
            construction.evaluation.reasons[0],
        )
        for repair in (depth_one, depth_two, direct_depth_two):
            self.assertEqual(
                repair.status,
                "initial_solution_infeasible",
            )
            self.assertEqual(
                repair.stop_reason,
                "initial_solution_infeasible",
            )
            self.assertFalse(repair.evaluation.feasible)
            self.assertEqual(
                repair.evaluation,
                construction.evaluation,
            )
            self.assertEqual(repair.evaluated_candidates, 0)
            self.assertEqual(repair.accepted_moves, tuple())

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
            / scales.cost
            + self.instance.weights.time
            * evaluation.total_time_minutes
            / scales.time,
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
