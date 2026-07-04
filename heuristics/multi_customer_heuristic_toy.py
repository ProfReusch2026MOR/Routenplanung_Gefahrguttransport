"""Multi-customer, multi-trip toy heuristic for hazardous-material routing.

This prototype is intentionally independent from the real road-network adapter.
It validates the upper-level route and schedule logic before that logic is
connected to Berlin or Germany path data.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from numbers import Integral, Real
from pprint import pformat
import time
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


DEPOT = "DEPOT"
EPSILON = 1e-9


@dataclass(frozen=True)
class Customer:
    customer_id: str
    hazard_class: str
    demand_kg: float
    service_minutes: float
    earliest_minute: float
    latest_minute: float


@dataclass(frozen=True)
class Vehicle:
    vehicle_id: str
    vehicle_type: str
    capacity_kg: float
    usable_battery_kwh: float
    initial_battery_kwh: float
    min_reserve_kwh: float
    energy_kwh_per_km: float
    max_charging_power_kw: float
    compatible_classes: Tuple[str, ...]
    activation_cost: float
    trip_cost: float
    road_cost_per_km: float
    shift_start_minute: float
    shift_end_minute: float
    initial_load_minutes: float
    reload_minutes: float
    max_daily_driving_minutes: float
    max_daily_working_minutes: float
    solver_name: Optional[str] = None


@dataclass(frozen=True)
class ChargingStation:
    station_id: str
    power_kw: float
    energy_price_per_kwh: float
    session_fee: float = 0.0


@dataclass(frozen=True)
class Leg:
    from_stop: str
    to_stop: str
    distance_km: float
    travel_minutes: float
    base_risk_rate_per_km: float
    allowed_classes: Tuple[str, ...]


@dataclass(frozen=True)
class ObjectiveWeights:
    risk: float = 0.65
    cost: float = 0.35
    time: float = 0.0


@dataclass(frozen=True)
class ObjectiveScales:
    risk: float
    cost: float
    time: float
    risk_active: bool


@dataclass(frozen=True)
class ToyInstance:
    customers: Mapping[str, Customer]
    vehicles: Mapping[str, Vehicle]
    chargers: Mapping[str, ChargingStation]
    customer_charger_candidates: Mapping[str, Tuple[str, ...]]
    legs: Mapping[Tuple[str, str], Leg]
    break_nodes: Tuple[str, ...]
    depot_charging_power_kw: float
    depot_energy_price_per_kwh: float
    continuous_driving_limit_minutes: float
    break_duration_minutes: float
    max_charging_branch_evaluations: int
    weights: ObjectiveWeights


@dataclass(frozen=True)
class LegRecord:
    from_stop: str
    to_stop: str
    loaded: bool
    distance_km: float
    travel_minutes: float
    risk: float
    energy_kwh: float
    road_operating_cost: float
    battery_before_kwh: float
    battery_after_kwh: float


@dataclass(frozen=True)
class VisitRecord:
    stop_id: str
    stop_type: str
    arrival_minute: float
    departure_minute: float
    delivered_kg: float
    remaining_load_kg: float
    battery_arrival_kwh: float
    battery_departure_kwh: float
    charged_energy_kwh: float = 0.0
    charging_minutes: float = 0.0
    break_minutes: float = 0.0


@dataclass(frozen=True)
class TripEvaluation:
    trip_index: int
    hazard_class: str
    customer_sequence: Tuple[str, ...]
    stop_sequence: Tuple[str, ...]
    visits: Tuple[VisitRecord, ...]
    legs: Tuple[LegRecord, ...]
    start_minute: float
    return_minute: float
    initial_load_kg: float
    final_battery_kwh: float
    minimum_battery_kwh: float
    total_risk: float
    road_operating_cost: float
    station_charging_cost: float
    trip_cost: float
    travel_minutes: float
    service_minutes: float
    waiting_minutes: float
    charging_minutes: float
    break_minutes: float


@dataclass(frozen=True)
class VehicleScheduleEvaluation:
    vehicle_id: str
    feasible: bool
    reasons: Tuple[str, ...]
    trips: Tuple[TripEvaluation, ...]
    activation_cost: float
    trip_cost: float
    road_operating_cost: float
    station_charging_cost: float
    end_of_day_recharge_kwh: float
    end_of_day_recharge_cost: float
    total_cost: float
    total_risk: float
    total_distance_km: float
    total_travel_minutes: float
    total_service_minutes: float
    total_waiting_minutes: float
    total_charging_minutes: float
    total_break_minutes: float
    operating_minutes: float
    first_activity_minute: Optional[float]
    last_return_minute: Optional[float]
    final_battery_kwh: float
    charging_branch_evaluations: int = 0


@dataclass(frozen=True)
class SolutionEvaluation:
    feasible: bool
    reasons: Tuple[str, ...]
    schedules: Mapping[str, Tuple[Tuple[str, ...], ...]]
    vehicle_evaluations: Mapping[str, VehicleScheduleEvaluation]
    served_customers: Tuple[str, ...]
    unserved_customers: Tuple[str, ...]
    objective: float
    total_risk: float
    total_cost: float
    total_activation_cost: float
    total_trip_cost: float
    total_road_operating_cost: float
    total_station_charging_cost: float
    total_end_of_day_recharge_cost: float
    total_distance_km: float
    total_travel_minutes: float
    total_service_minutes: float
    total_waiting_minutes: float
    total_charging_minutes: float
    total_break_minutes: float
    total_time_minutes: float
    makespan_minute: float
    charging_branch_evaluations: int = 0


@dataclass(frozen=True)
class HeuristicRun:
    status: str
    evaluation: SolutionEvaluation
    scales: ObjectiveScales
    runtime_seconds: float


@dataclass(frozen=True)
class SideTripPlan:
    station_id: str
    outward_leg: Leg
    return_leg: Leg
    charged_energy_kwh: float
    charging_minutes: float
    origin_break_before_minutes: float
    break_minutes: float
    origin_break_after_minutes: float
    stop_minutes: float
    station_charging_cost: float
    side_trip_risk: float
    side_trip_road_cost: float
    detour_distance_km: float
    objective_increment: float


@dataclass(frozen=True)
class FeasibilityState:
    current_stop: str
    battery_kwh: float
    current_time: float
    continuous_driving_minutes: float
    daily_driving_minutes: float
    remaining_load_kg: float


@dataclass(frozen=True)
class TransitionResult:
    state: Optional[FeasibilityState]
    failure_reason: Optional[str] = None


@dataclass(frozen=True)
class ContinuationResult:
    status: str
    failure_reasons: Tuple[str, ...] = tuple()


class NoFeasibleCustomerError(ValueError):
    def __init__(self, customer_id: str, reasons: Sequence[str]) -> None:
        self.customer_id = customer_id
        self.reasons = tuple(reasons)
        super().__init__(
            f"Customer {customer_id} has no feasible single-customer trip."
        )


class InputDataError(ValueError):
    pass


def _hazard_factor(hazard_class: str) -> float:
    return {
        "3": 1.0,
        "2 (TOC)": 0.8,
    }.get(hazard_class, 1.0)


def _validate_weights(weights: ObjectiveWeights) -> None:
    values = (weights.risk, weights.cost, weights.time)
    if any(value < 0 for value in values):
        raise ValueError("Objective weights must be non-negative.")
    if not math.isclose(sum(values), 1.0, abs_tol=1e-9):
        raise ValueError("Objective weights must sum to 1.0.")


def _validate_finite_number(
    value: object,
    label: str,
    errors: List[str],
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(float(value))
    ):
        errors.append(f"{label} must be a finite number.")


def validate_instance(instance: ToyInstance) -> None:
    """Reject malformed toy input before construction starts."""
    errors: List[str] = []

    for name, value in (
        ("weights.risk", instance.weights.risk),
        ("weights.cost", instance.weights.cost),
        ("weights.time", instance.weights.time),
        ("depot_charging_power_kw", instance.depot_charging_power_kw),
        ("depot_energy_price_per_kwh", instance.depot_energy_price_per_kwh),
        (
            "continuous_driving_limit_minutes",
            instance.continuous_driving_limit_minutes,
        ),
        ("break_duration_minutes", instance.break_duration_minutes),
    ):
        _validate_finite_number(value, name, errors)

    for customer_key, customer in instance.customers.items():
        for name, value in (
            ("demand_kg", customer.demand_kg),
            ("service_minutes", customer.service_minutes),
            ("earliest_minute", customer.earliest_minute),
            ("latest_minute", customer.latest_minute),
        ):
            _validate_finite_number(
                value,
                f"{customer_key}.{name}",
                errors,
            )

    for vehicle_key, vehicle in instance.vehicles.items():
        for name, value in (
            ("capacity_kg", vehicle.capacity_kg),
            ("usable_battery_kwh", vehicle.usable_battery_kwh),
            ("initial_battery_kwh", vehicle.initial_battery_kwh),
            ("min_reserve_kwh", vehicle.min_reserve_kwh),
            ("energy_kwh_per_km", vehicle.energy_kwh_per_km),
            ("max_charging_power_kw", vehicle.max_charging_power_kw),
            ("activation_cost", vehicle.activation_cost),
            ("trip_cost", vehicle.trip_cost),
            ("road_cost_per_km", vehicle.road_cost_per_km),
            ("shift_start_minute", vehicle.shift_start_minute),
            ("shift_end_minute", vehicle.shift_end_minute),
            ("initial_load_minutes", vehicle.initial_load_minutes),
            ("reload_minutes", vehicle.reload_minutes),
            (
                "max_daily_driving_minutes",
                vehicle.max_daily_driving_minutes,
            ),
            (
                "max_daily_working_minutes",
                vehicle.max_daily_working_minutes,
            ),
        ):
            _validate_finite_number(
                value,
                f"{vehicle_key}.{name}",
                errors,
            )

    for station_key, station in instance.chargers.items():
        for name, value in (
            ("power_kw", station.power_kw),
            ("energy_price_per_kwh", station.energy_price_per_kwh),
            ("session_fee", station.session_fee),
        ):
            _validate_finite_number(
                value,
                f"{station_key}.{name}",
                errors,
            )

    for (from_stop, to_stop), leg in instance.legs.items():
        for name, value in (
            ("distance_km", leg.distance_km),
            ("travel_minutes", leg.travel_minutes),
            ("base_risk_rate_per_km", leg.base_risk_rate_per_km),
        ):
            _validate_finite_number(
                value,
                f"{from_stop}->{to_stop}.{name}",
                errors,
            )

    if (
        isinstance(instance.max_charging_branch_evaluations, bool)
        or not isinstance(
            instance.max_charging_branch_evaluations,
            Integral,
        )
    ):
        errors.append(
            "max_charging_branch_evaluations must be an integer."
        )

    if errors:
        raise InputDataError(" | ".join(errors))

    try:
        _validate_weights(instance.weights)
    except ValueError as error:
        errors.append(str(error))

    if not instance.customers:
        errors.append("At least one customer is required.")
    if not instance.vehicles:
        errors.append("At least one physical vehicle is required.")

    for customer_key, customer in instance.customers.items():
        if customer_key != customer.customer_id:
            errors.append(
                f"Customer key {customer_key} does not match "
                f"customer_id {customer.customer_id}."
            )
        if customer.demand_kg <= 0:
            errors.append(
                f"{customer.customer_id}: demand_kg must be positive."
            )
        if customer.service_minutes < 0:
            errors.append(
                f"{customer.customer_id}: service_minutes cannot be negative."
            )
        if customer.earliest_minute > customer.latest_minute:
            errors.append(
                f"{customer.customer_id}: invalid time window."
            )

    for vehicle_key, vehicle in instance.vehicles.items():
        if vehicle_key != vehicle.vehicle_id:
            errors.append(
                f"Vehicle key {vehicle_key} does not match "
                f"vehicle_id {vehicle.vehicle_id}."
            )
        if vehicle.capacity_kg <= 0:
            errors.append(
                f"{vehicle.vehicle_id}: capacity_kg must be positive."
            )
        if vehicle.usable_battery_kwh <= 0:
            errors.append(
                f"{vehicle.vehicle_id}: usable battery must be positive."
            )
        if not (
            0 <= vehicle.min_reserve_kwh
            <= vehicle.initial_battery_kwh
            <= vehicle.usable_battery_kwh
        ):
            errors.append(
                f"{vehicle.vehicle_id}: invalid battery or reserve values."
            )
        if vehicle.energy_kwh_per_km < 0:
            errors.append(
                f"{vehicle.vehicle_id}: energy rate cannot be negative."
            )
        if vehicle.max_charging_power_kw <= 0:
            errors.append(
                f"{vehicle.vehicle_id}: charging power must be positive."
            )
        if any(
            value < 0
            for value in (
                vehicle.activation_cost,
                vehicle.trip_cost,
                vehicle.road_cost_per_km,
                vehicle.initial_load_minutes,
                vehicle.reload_minutes,
            )
        ):
            errors.append(
                f"{vehicle.vehicle_id}: costs and handling times "
                "cannot be negative."
            )
        if vehicle.shift_start_minute > vehicle.shift_end_minute:
            errors.append(
                f"{vehicle.vehicle_id}: invalid shift interval."
            )
        if (
            vehicle.max_daily_driving_minutes <= 0
            or vehicle.max_daily_working_minutes <= 0
        ):
            errors.append(
                f"{vehicle.vehicle_id}: daily limits must be positive."
            )
    solver_vehicle_names = [
        vehicle.solver_name or vehicle.vehicle_type
        for vehicle in instance.vehicles.values()
    ]
    if len(solver_vehicle_names) != len(set(solver_vehicle_names)):
        errors.append(
            "Solver vehicle names must be unique; set solver_name for "
            "multiple physical vehicles of the same type."
        )

    for station_key, station in instance.chargers.items():
        if station_key != station.station_id:
            errors.append(
                f"Charging-station key {station_key} does not match "
                f"station_id {station.station_id}."
            )
        if station.power_kw < 0:
            errors.append(
                f"{station.station_id}: charging power cannot be negative."
            )
        if station.energy_price_per_kwh < 0 or station.session_fee < 0:
            errors.append(
                f"{station.station_id}: charging costs cannot be negative."
            )

    for customer_id, station_ids in (
        instance.customer_charger_candidates.items()
    ):
        if customer_id not in instance.customers:
            errors.append(
                f"Unknown customer in charger candidates: {customer_id}."
            )
        if len(station_ids) > 3:
            errors.append(
                f"{customer_id}: at most three charging candidates are allowed."
            )
        if len(station_ids) != len(set(station_ids)):
            errors.append(
                f"{customer_id}: charging candidates contain duplicates."
            )
        for station_id in station_ids:
            if station_id not in instance.chargers:
                errors.append(
                    f"{customer_id}: unknown charging station {station_id}."
                )

    for (from_stop, to_stop), leg in instance.legs.items():
        if leg.from_stop != from_stop or leg.to_stop != to_stop:
            errors.append(
                f"Leg key {from_stop}->{to_stop} does not match its record."
            )
        if (
            leg.distance_km < 0
            or leg.travel_minutes < 0
            or leg.base_risk_rate_per_km < 0
        ):
            errors.append(
                f"Leg {from_stop}->{to_stop} has a negative metric."
            )

    if instance.depot_charging_power_kw <= 0:
        errors.append("Depot charging power must be positive.")
    if instance.depot_energy_price_per_kwh < 0:
        errors.append("Depot energy price cannot be negative.")
    if (
        instance.continuous_driving_limit_minutes <= 0
        or instance.break_duration_minutes <= 0
    ):
        errors.append("Driving and break limits must be positive.")
    if instance.max_charging_branch_evaluations < 0:
        errors.append(
            "Charging branch evaluation limit cannot be negative."
        )

    if errors:
        raise InputDataError(" | ".join(errors))


def _complete_legs(
    coordinates: Mapping[str, Tuple[float, float]],
    allowed_classes: Tuple[str, ...],
) -> Dict[Tuple[str, str], Leg]:
    """Build deterministic pairwise metrics for the artificial instance."""
    ordered_stops = tuple(coordinates)
    legs: Dict[Tuple[str, str], Leg] = {}
    for from_index, from_stop in enumerate(ordered_stops):
        x1, y1 = coordinates[from_stop]
        for to_index, to_stop in enumerate(ordered_stops):
            if from_stop == to_stop:
                continue
            x2, y2 = coordinates[to_stop]
            distance = math.hypot(x2 - x1, y2 - y1)
            risk_rate = 0.025 + 0.005 * ((from_index + 2 * to_index) % 5)
            legs[(from_stop, to_stop)] = Leg(
                from_stop=from_stop,
                to_stop=to_stop,
                distance_km=distance,
                travel_minutes=distance / 45.0 * 60.0,
                base_risk_rate_per_km=risk_rate,
                allowed_classes=allowed_classes,
            )
    return legs


def build_toy_instance() -> ToyInstance:
    """Create a deterministic instance that requires multi-trip and charging."""
    customers = {
        "G1": Customer("G1", "3", 5_000.0, 15.0, 480.0, 1_000.0),
        "G2": Customer("G2", "3", 4_000.0, 15.0, 480.0, 1_000.0),
        "G3": Customer("G3", "3", 5_000.0, 15.0, 480.0, 1_000.0),
        "G4": Customer("G4", "3", 4_000.0, 15.0, 480.0, 1_000.0),
        "C1": Customer("C1", "2 (TOC)", 4_000.0, 20.0, 480.0, 1_000.0),
        "C2": Customer("C2", "2 (TOC)", 4_000.0, 20.0, 480.0, 1_000.0),
    }
    vehicles = {
        "TRUCK_G_1": Vehicle(
            "TRUCK_G_1",
            "MAN_eTGX",
            10_000.0,
            16.0,
            16.0,
            2.0,
            1.0,
            80.0,
            ("3",),
            300.0,
            30.0,
            1.00,
            480.0,
            1_080.0,
            20.0,
            15.0,
            540.0,
            600.0,
        ),
        "TRUCK_C_1": Vehicle(
            "TRUCK_C_1",
            "Volvo_FH_Electric",
            8_000.0,
            20.0,
            20.0,
            2.0,
            0.8,
            70.0,
            ("2 (TOC)",),
            260.0,
            25.0,
            1.10,
            480.0,
            1_080.0,
            20.0,
            15.0,
            540.0,
            600.0,
        ),
        "TRUCK_G_BACKUP": Vehicle(
            "TRUCK_G_BACKUP",
            "Mercedes_eActros_600",
            10_000.0,
            22.0,
            22.0,
            2.0,
            1.0,
            90.0,
            ("3",),
            1_000.0,
            30.0,
            1.20,
            480.0,
            1_080.0,
            20.0,
            15.0,
            540.0,
            600.0,
        ),
    }
    chargers = {
        "FAST_CHARGE": ChargingStation("FAST_CHARGE", 160.0, 0.50, 2.0),
    }
    coordinates = {
        DEPOT: (0.0, 0.0),
        "G1": (3.0, 0.0),
        "G2": (4.0, 1.0),
        "G3": (9.0, 0.0),
        "G4": (7.0, 2.0),
        "C1": (0.0, 4.0),
        "C2": (1.0, 5.0),
        "FAST_CHARGE": (8.0, 0.0),
    }
    return ToyInstance(
        customers=customers,
        vehicles=vehicles,
        chargers=chargers,
        customer_charger_candidates={
            customer_id: ("FAST_CHARGE",)
            for customer_id in customers
        },
        legs=_complete_legs(coordinates, ("3", "2 (TOC)")),
        break_nodes=(DEPOT, "FAST_CHARGE"),
        depot_charging_power_kw=100.0,
        depot_energy_price_per_kwh=0.30,
        continuous_driving_limit_minutes=270.0,
        break_duration_minutes=45.0,
        max_charging_branch_evaluations=100,
        weights=ObjectiveWeights(),
    )


def _freeze_schedules(
    schedules: Mapping[str, Sequence[Sequence[str]]],
) -> Dict[str, Tuple[Tuple[str, ...], ...]]:
    return {
        vehicle_id: tuple(tuple(trip) for trip in trips)
        for vehicle_id, trips in schedules.items()
    }


def _copy_schedules(
    schedules: Mapping[str, Sequence[Sequence[str]]],
) -> Dict[str, List[List[str]]]:
    return {
        vehicle_id: [list(trip) for trip in trips]
        for vehicle_id, trips in schedules.items()
    }


def _leg(
    instance: ToyInstance,
    from_stop: str,
    to_stop: str,
    hazard_class: str,
) -> Optional[Leg]:
    leg = instance.legs.get((from_stop, to_stop))
    if leg is None or hazard_class not in leg.allowed_classes:
        return None
    return leg


def _departure_break_minutes(
    instance: ToyInstance,
    current_stop: str,
    next_leg: Leg,
    continuous_driving_minutes: float,
) -> Optional[float]:
    """Return required break duration, or None when departure is infeasible."""
    driving_limit = instance.continuous_driving_limit_minutes
    if next_leg.travel_minutes > driving_limit + EPSILON:
        return None
    if (
        continuous_driving_minutes + next_leg.travel_minutes
        <= driving_limit + EPSILON
    ):
        return 0.0
    if current_stop not in instance.break_nodes:
        return None
    return instance.break_duration_minutes


def _side_trip_plans(
    instance: ToyInstance,
    vehicle: Vehicle,
    current_customer: str,
    target: str,
    hazard_class: str,
    battery_kwh: float,
    current_time: float,
    continuous_driving_minutes: float,
    daily_driving_minutes: float,
    remaining_load_kg: float,
    objective_scales: Optional[ObjectiveScales],
) -> Tuple[SideTripPlan, ...]:
    """Evaluate restricted customer-station-customer charging side-trips."""
    direct = _leg(instance, current_customer, target, hazard_class)
    if direct is None:
        return tuple()

    plans: List[SideTripPlan] = []
    station_ids = instance.customer_charger_candidates.get(
        current_customer,
        tuple(),
    )[:3]
    for station_id in station_ids:
        station = instance.chargers.get(station_id)
        if station is None or station_id in (current_customer, target):
            continue
        outward = _leg(
            instance,
            current_customer,
            station_id,
            hazard_class,
        )
        return_leg = _leg(
            instance,
            station_id,
            current_customer,
            hazard_class,
        )
        if outward is None or return_leg is None:
            continue

        origin_break_before = _departure_break_minutes(
            instance,
            current_customer,
            outward,
            continuous_driving_minutes,
        )
        if origin_break_before is None:
            continue
        continuous_at_station = (
            0.0
            if origin_break_before > EPSILON
            else continuous_driving_minutes
        ) + outward.travel_minutes

        outward_energy = outward.distance_km * vehicle.energy_kwh_per_km
        battery_at_station = battery_kwh - outward_energy
        if battery_at_station < vehicle.min_reserve_kwh - EPSILON:
            continue

        effective_power = min(
            station.power_kw,
            vehicle.max_charging_power_kw,
        )
        if effective_power <= 0:
            continue
        charged_energy = vehicle.usable_battery_kwh - battery_at_station
        charging_minutes = charged_energy / effective_power * 60.0

        station_departure_break = _departure_break_minutes(
            instance,
            station_id,
            return_leg,
            continuous_at_station,
        )
        charging_qualifies_as_break = (
            station_id in instance.break_nodes
            and charging_minutes + EPSILON >= instance.break_duration_minutes
        )
        if station_departure_break is None:
            continue
        break_minutes = (
            instance.break_duration_minutes
            if (
                station_departure_break > EPSILON
                or charging_qualifies_as_break
            )
            else 0.0
        )
        continuous_after_station = (
            0.0 if break_minutes > EPSILON else continuous_at_station
        )
        continuous_back_at_customer = (
            continuous_after_station + return_leg.travel_minutes
        )
        origin_break_after = _departure_break_minutes(
            instance,
            current_customer,
            direct,
            continuous_back_at_customer,
        )
        if (
            origin_break_after is None
            and station_id in instance.break_nodes
            and break_minutes <= EPSILON
        ):
            break_minutes = instance.break_duration_minutes
            continuous_after_station = 0.0
            continuous_back_at_customer = return_leg.travel_minutes
            origin_break_after = _departure_break_minutes(
                instance,
                current_customer,
                direct,
                continuous_back_at_customer,
            )
        if origin_break_after is None:
            continue
        stop_minutes = max(charging_minutes, break_minutes)

        return_energy = return_leg.distance_km * vehicle.energy_kwh_per_km
        battery_back_at_customer = (
            vehicle.usable_battery_kwh - return_energy
        )
        direct_energy = direct.distance_km * vehicle.energy_kwh_per_km
        if (
            battery_back_at_customer
            < vehicle.min_reserve_kwh - EPSILON
            or battery_back_at_customer - direct_energy
            < vehicle.min_reserve_kwh - EPSILON
        ):
            continue

        added_driving = (
            outward.travel_minutes
            + return_leg.travel_minutes
            + direct.travel_minutes
        )
        if (
            daily_driving_minutes + added_driving
            > vehicle.max_daily_driving_minutes + EPSILON
        ):
            continue

        arrival_at_target = (
            current_time
            + origin_break_before
            + outward.travel_minutes
            + stop_minutes
            + return_leg.travel_minutes
            + origin_break_after
            + direct.travel_minutes
        )
        target_departure = arrival_at_target
        if target != DEPOT:
            customer = instance.customers[target]
            service_start = max(
                arrival_at_target,
                customer.earliest_minute,
            )
            if service_start > customer.latest_minute + EPSILON:
                continue
            target_departure = service_start + customer.service_minutes
        if target_departure > vehicle.shift_end_minute + EPSILON:
            continue

        loaded = remaining_load_kg > EPSILON
        side_trip_risk = (
            (
                outward.base_risk_rate_per_km * outward.distance_km
                + return_leg.base_risk_rate_per_km
                * return_leg.distance_km
            )
            * _hazard_factor(hazard_class)
            if loaded
            else 0.0
        )
        side_trip_road_cost = (
            outward.distance_km + return_leg.distance_km
        ) * vehicle.road_cost_per_km
        station_charging_cost = (
            charged_energy * station.energy_price_per_kwh
            + (station.session_fee if charged_energy > EPSILON else 0.0)
        )
        side_trip_minutes = (
            outward.travel_minutes
            + origin_break_before
            + stop_minutes
            + return_leg.travel_minutes
            + origin_break_after
        )
        scales = objective_scales or ObjectiveScales(
            1.0,
            1.0,
            1.0,
            True,
        )
        objective_increment = _objective(
            side_trip_risk,
            side_trip_road_cost + station_charging_cost,
            side_trip_minutes,
            scales,
            instance.weights,
        )
        plans.append(
            SideTripPlan(
                station_id=station_id,
                outward_leg=outward,
                return_leg=return_leg,
                charged_energy_kwh=charged_energy,
                charging_minutes=charging_minutes,
                origin_break_before_minutes=origin_break_before,
                break_minutes=break_minutes,
                origin_break_after_minutes=origin_break_after,
                stop_minutes=stop_minutes,
                station_charging_cost=station_charging_cost,
                side_trip_risk=side_trip_risk,
                side_trip_road_cost=side_trip_road_cost,
                detour_distance_km=(
                    outward.distance_km + return_leg.distance_km
                ),
                objective_increment=objective_increment,
            )
        )

    return tuple(
        sorted(
            plans,
            key=lambda plan: (
                plan.objective_increment,
                plan.charging_minutes,
                plan.station_charging_cost,
                plan.detour_distance_km,
                plan.station_id,
            ),
        )
    )


def _advance_direct_feasibility_state(
    instance: ToyInstance,
    vehicle: Vehicle,
    state: FeasibilityState,
    target: str,
    hazard_class: str,
) -> TransitionResult:
    direct = _leg(instance, state.current_stop, target, hazard_class)
    if direct is None:
        return TransitionResult(
            None,
            (
                f"{vehicle.vehicle_id}: no_legal_path "
                f"{state.current_stop}->{target}."
            ),
        )
    departure_break = _departure_break_minutes(
        instance,
        state.current_stop,
        direct,
        state.continuous_driving_minutes,
    )
    direct_energy = direct.distance_km * vehicle.energy_kwh_per_km
    if (
        departure_break is None
    ):
        return TransitionResult(
            None,
            (
                f"{vehicle.vehicle_id}: break_infeasible before "
                f"{state.current_stop}->{target}."
            ),
        )
    if (
        state.battery_kwh - direct_energy
        < vehicle.min_reserve_kwh - EPSILON
    ):
        return TransitionResult(
            None,
            (
                f"{vehicle.vehicle_id}: charging_infeasible before "
                f"{state.current_stop}->{target}."
            ),
        )

    continuous_after = (
        0.0
        if departure_break > EPSILON
        else state.continuous_driving_minutes
    ) + direct.travel_minutes
    daily_after = (
        state.daily_driving_minutes + direct.travel_minutes
    )
    if daily_after > vehicle.max_daily_driving_minutes + EPSILON:
        return TransitionResult(
            None,
            (
                f"{vehicle.vehicle_id}: daily_driving_infeasible "
                f"before {state.current_stop}->{target}."
            ),
        )

    current_time = (
        state.current_time
        + departure_break
        + direct.travel_minutes
    )
    remaining_load = state.remaining_load_kg
    if target != DEPOT:
        customer = instance.customers[target]
        service_start = max(
            current_time,
            customer.earliest_minute,
        )
        if service_start > customer.latest_minute + EPSILON:
            return TransitionResult(
                None,
                (
                    f"{vehicle.vehicle_id}: "
                    f"time_window_infeasible at {target}."
                ),
            )
        current_time = service_start + customer.service_minutes
        remaining_load -= customer.demand_kg
    if current_time > vehicle.shift_end_minute + EPSILON:
        return TransitionResult(
            None,
            f"{vehicle.vehicle_id}: shift_infeasible at {target}.",
        )
    if (
        current_time - vehicle.shift_start_minute
        > vehicle.max_daily_working_minutes + EPSILON
    ):
        return TransitionResult(
            None,
            (
                f"{vehicle.vehicle_id}: "
                f"daily_working_infeasible at {target}."
            ),
        )

    return TransitionResult(
        FeasibilityState(
            current_stop=target,
            battery_kwh=state.battery_kwh - direct_energy,
            current_time=current_time,
            continuous_driving_minutes=continuous_after,
            daily_driving_minutes=daily_after,
            remaining_load_kg=remaining_load,
        )
    )


def _advance_side_trip_feasibility_state(
    instance: ToyInstance,
    vehicle: Vehicle,
    state: FeasibilityState,
    target: str,
    hazard_class: str,
    plan: SideTripPlan,
) -> Optional[FeasibilityState]:
    continuous_driving = state.continuous_driving_minutes
    current_time = state.current_time
    daily_driving = state.daily_driving_minutes
    battery = state.battery_kwh

    if plan.origin_break_before_minutes > EPSILON:
        current_time += plan.origin_break_before_minutes
        continuous_driving = 0.0

    outward_energy = (
        plan.outward_leg.distance_km * vehicle.energy_kwh_per_km
    )
    battery -= outward_energy
    if battery < vehicle.min_reserve_kwh - EPSILON:
        return None
    current_time += plan.outward_leg.travel_minutes
    continuous_driving += plan.outward_leg.travel_minutes
    daily_driving += plan.outward_leg.travel_minutes

    current_time += plan.stop_minutes
    battery = vehicle.usable_battery_kwh
    if plan.break_minutes > EPSILON:
        continuous_driving = 0.0

    return_energy = (
        plan.return_leg.distance_km * vehicle.energy_kwh_per_km
    )
    battery -= return_energy
    if battery < vehicle.min_reserve_kwh - EPSILON:
        return None
    current_time += plan.return_leg.travel_minutes
    continuous_driving += plan.return_leg.travel_minutes
    daily_driving += plan.return_leg.travel_minutes

    state_back_at_customer = FeasibilityState(
        current_stop=state.current_stop,
        battery_kwh=battery,
        current_time=current_time,
        continuous_driving_minutes=continuous_driving,
        daily_driving_minutes=daily_driving,
        remaining_load_kg=state.remaining_load_kg,
    )
    return _advance_direct_feasibility_state(
        instance,
        vehicle,
        state_back_at_customer,
        target,
        hazard_class,
    ).state


def _state_dominates(
    left: FeasibilityState,
    right: FeasibilityState,
) -> bool:
    return (
        left.current_stop == right.current_stop
        and math.isclose(
            left.remaining_load_kg,
            right.remaining_load_kg,
            abs_tol=EPSILON,
        )
        and left.battery_kwh + EPSILON >= right.battery_kwh
        and left.current_time <= right.current_time + EPSILON
        and left.continuous_driving_minutes
        <= right.continuous_driving_minutes + EPSILON
        and left.daily_driving_minutes
        <= right.daily_driving_minutes + EPSILON
        and (
            left.battery_kwh > right.battery_kwh + EPSILON
            or left.current_time + EPSILON < right.current_time
            or left.continuous_driving_minutes + EPSILON
            < right.continuous_driving_minutes
            or left.daily_driving_minutes + EPSILON
            < right.daily_driving_minutes
        )
    )


def _states_equivalent(
    left: FeasibilityState,
    right: FeasibilityState,
) -> bool:
    return (
        left.current_stop == right.current_stop
        and math.isclose(
            left.battery_kwh,
            right.battery_kwh,
            abs_tol=EPSILON,
        )
        and math.isclose(
            left.current_time,
            right.current_time,
            abs_tol=EPSILON,
        )
        and math.isclose(
            left.continuous_driving_minutes,
            right.continuous_driving_minutes,
            abs_tol=EPSILON,
        )
        and math.isclose(
            left.daily_driving_minutes,
            right.daily_driving_minutes,
            abs_tol=EPSILON,
        )
        and math.isclose(
            left.remaining_load_kg,
            right.remaining_load_kg,
            abs_tol=EPSILON,
        )
    )


def _prune_feasibility_states(
    states: Sequence[FeasibilityState],
) -> Tuple[FeasibilityState, ...]:
    ordered = sorted(
        states,
        key=lambda state: (
            state.current_time,
            -state.battery_kwh,
            state.continuous_driving_minutes,
            state.daily_driving_minutes,
        ),
    )
    retained: List[FeasibilityState] = []
    for candidate in ordered:
        if any(
            _states_equivalent(existing, candidate)
            or _state_dominates(existing, candidate)
            for existing in retained
        ):
            continue
        retained = [
            existing
            for existing in retained
            if not _state_dominates(candidate, existing)
        ]
        retained.append(candidate)
    return tuple(retained)


def _select_failure_reason(reasons: Sequence[str]) -> Optional[str]:
    priorities = (
        "no_legal_path",
        "time_window_infeasible",
        "shift_infeasible",
        "daily_working_infeasible",
        "daily_driving_infeasible",
        "break_infeasible",
        "charging_infeasible",
    )
    for marker in priorities:
        for reason in reasons:
            if marker in reason:
                return reason
    return reasons[0] if reasons else None


def _select_nonrepairable_failure_reason(
    reasons: Sequence[str],
) -> Optional[str]:
    nonrepairable = tuple(
        reason
        for reason in reasons
        if (
            "charging_infeasible" not in reason
            and "break_infeasible" not in reason
        )
    )
    return _select_failure_reason(nonrepairable)


def _continuation_status(
    instance: ToyInstance,
    vehicle: Vehicle,
    initial_state: FeasibilityState,
    targets: Sequence[str],
    hazard_class: str,
    objective_scales: Optional[ObjectiveScales],
    charging_branch_counter: List[int],
) -> ContinuationResult:
    states: Tuple[FeasibilityState, ...] = (initial_state,)
    search_incomplete = False
    for target in targets:
        next_states: List[FeasibilityState] = []
        failure_reasons: List[str] = []
        for state in states:
            direct_result = _advance_direct_feasibility_state(
                instance,
                vehicle,
                state,
                target,
                hazard_class,
            )
            if direct_result.state is not None:
                next_states.append(direct_result.state)
            elif direct_result.failure_reason:
                failure_reasons.append(
                    direct_result.failure_reason
                )

            if state.current_stop not in instance.customers:
                continue
            plans = _side_trip_plans(
                instance,
                vehicle,
                state.current_stop,
                target,
                hazard_class,
                state.battery_kwh,
                state.current_time,
                state.continuous_driving_minutes,
                state.daily_driving_minutes,
                state.remaining_load_kg,
                objective_scales,
            )
            for plan in plans:
                side_trip_state = _advance_side_trip_feasibility_state(
                    instance,
                    vehicle,
                    state,
                    target,
                    hazard_class,
                    plan,
                )
                if side_trip_state is None:
                    continue
                if any(
                    _states_equivalent(existing, side_trip_state)
                    or _state_dominates(existing, side_trip_state)
                    for existing in next_states
                ):
                    continue
                if (
                    charging_branch_counter[0]
                    >= instance.max_charging_branch_evaluations
                ):
                    search_incomplete = True
                    break
                charging_branch_counter[0] += 1
                next_states.append(side_trip_state)
        states = _prune_feasibility_states(next_states)
        if not states:
            return ContinuationResult(
                "incomplete" if search_incomplete else "infeasible",
                tuple(dict.fromkeys(failure_reasons)),
            )
    return ContinuationResult("feasible")


def _proactive_repair_status(
    instance: ToyInstance,
    vehicle: Vehicle,
    current_state: FeasibilityState,
    target: str,
    remaining_targets: Sequence[str],
    hazard_class: str,
    objective_scales: Optional[ObjectiveScales],
    charging_branch_counter: List[int],
) -> ContinuationResult:
    if (
        current_state.current_stop not in instance.customers
        or not remaining_targets
    ):
        return ContinuationResult("not_needed")
    direct_result = _advance_direct_feasibility_state(
        instance,
        vehicle,
        current_state,
        target,
        hazard_class,
    )
    if direct_result.state is None:
        return ContinuationResult("not_needed")
    continuation = _continuation_status(
        instance,
        vehicle,
        direct_result.state,
        remaining_targets,
        hazard_class,
        objective_scales,
        charging_branch_counter,
    )
    if continuation.status == "feasible":
        return ContinuationResult("not_needed")
    if continuation.status == "incomplete":
        return continuation
    if any(
        marker in reason
        for reason in continuation.failure_reasons
        for marker in ("charging_infeasible", "break_infeasible")
    ):
        return ContinuationResult(
            "needed",
            continuation.failure_reasons,
        )
    return ContinuationResult(
        "terminal_failure",
        continuation.failure_reasons,
    )


def _failed_vehicle_evaluation(
    instance: ToyInstance,
    vehicle: Vehicle,
    reasons: Iterable[str],
    trips: Sequence[TripEvaluation] = (),
    charging_branch_evaluations: int = 0,
) -> VehicleScheduleEvaluation:
    completed_trips = tuple(trips)
    activation_cost = vehicle.activation_cost if completed_trips else 0.0
    trip_cost = sum(trip.trip_cost for trip in completed_trips)
    road_cost = sum(trip.road_operating_cost for trip in completed_trips)
    station_cost = sum(
        trip.station_charging_cost for trip in completed_trips
    )
    first_activity = (
        completed_trips[0].start_minute - vehicle.initial_load_minutes
        if completed_trips
        else None
    )
    last_return = (
        completed_trips[-1].return_minute if completed_trips else None
    )
    final_battery = (
        completed_trips[-1].final_battery_kwh
        if completed_trips
        else vehicle.initial_battery_kwh
    )
    end_of_day_recharge = max(
        0.0,
        vehicle.initial_battery_kwh - final_battery,
    )
    end_of_day_recharge_cost = (
        end_of_day_recharge * instance.depot_energy_price_per_kwh
    )
    return VehicleScheduleEvaluation(
        vehicle_id=vehicle.vehicle_id,
        feasible=False,
        reasons=tuple(reasons),
        trips=completed_trips,
        activation_cost=activation_cost,
        trip_cost=trip_cost,
        road_operating_cost=road_cost,
        station_charging_cost=station_cost,
        end_of_day_recharge_kwh=end_of_day_recharge,
        end_of_day_recharge_cost=end_of_day_recharge_cost,
        total_cost=(
            activation_cost
            + trip_cost
            + road_cost
            + station_cost
            + end_of_day_recharge_cost
        ),
        total_risk=sum(trip.total_risk for trip in completed_trips),
        total_distance_km=sum(
            leg.distance_km
            for trip in completed_trips
            for leg in trip.legs
        ),
        total_travel_minutes=sum(
            trip.travel_minutes for trip in completed_trips
        ),
        total_service_minutes=sum(
            trip.service_minutes for trip in completed_trips
        ),
        total_waiting_minutes=sum(
            trip.waiting_minutes for trip in completed_trips
        ),
        total_charging_minutes=sum(
            trip.charging_minutes for trip in completed_trips
        ),
        total_break_minutes=sum(
            trip.break_minutes for trip in completed_trips
        ),
        operating_minutes=(
            last_return - first_activity
            if last_return is not None and first_activity is not None
            else 0.0
        ),
        first_activity_minute=first_activity,
        last_return_minute=last_return,
        final_battery_kwh=final_battery,
        charging_branch_evaluations=charging_branch_evaluations,
    )


def evaluate_vehicle_schedule(
    instance: ToyInstance,
    vehicle: Vehicle,
    trip_sequences: Sequence[Sequence[str]],
    *,
    objective_scales: Optional[ObjectiveScales] = None,
    _charging_overrides: Optional[
        Mapping[Tuple[int, int, str, str], str]
    ] = None,
    _charging_branch_counter: Optional[List[int]] = None,
) -> VehicleScheduleEvaluation:
    """Evaluate all ordered trips of one physical vehicle."""
    charging_branch_counter = (
        _charging_branch_counter
        if _charging_branch_counter is not None
        else [0]
    )

    def failed(
        reasons: Iterable[str],
        trips: Sequence[TripEvaluation] = (),
    ) -> VehicleScheduleEvaluation:
        return _failed_vehicle_evaluation(
            instance,
            vehicle,
            reasons,
            trips,
            charging_branch_counter[0],
        )

    if not trip_sequences:
        return VehicleScheduleEvaluation(
            vehicle.vehicle_id,
            True,
            tuple(),
            tuple(),
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            None,
            None,
            vehicle.initial_battery_kwh,
        )

    if not (
        vehicle.min_reserve_kwh
        <= vehicle.initial_battery_kwh
        <= vehicle.usable_battery_kwh
    ):
        return failed(
            (f"{vehicle.vehicle_id}: invalid initial battery values.",),
        )

    current_time = vehicle.shift_start_minute
    first_activity = current_time
    battery = vehicle.initial_battery_kwh
    continuous_driving = 0.0
    daily_driving = 0.0
    day_hazard_class: Optional[str] = None
    trip_evaluations: List[TripEvaluation] = []

    total_risk = 0.0
    total_distance = 0.0
    total_travel = 0.0
    total_service = 0.0
    total_waiting = 0.0
    total_charging = 0.0
    total_break = 0.0
    total_road_cost = 0.0
    total_station_charge_cost = 0.0

    for trip_index, sequence in enumerate(trip_sequences, start=1):
        if not sequence:
            return failed(
                (f"{vehicle.vehicle_id}: trip {trip_index} has no customer.",),
                trip_evaluations,
            )

        unknown = [item for item in sequence if item not in instance.customers]
        if unknown:
            return failed(
                (f"{vehicle.vehicle_id}: unknown customer {unknown[0]}.",),
                trip_evaluations,
            )

        classes = {instance.customers[item].hazard_class for item in sequence}
        if len(classes) != 1:
            return failed(
                (f"{vehicle.vehicle_id}: commodity_incompatible on trip {trip_index}.",),
                trip_evaluations,
            )
        hazard_class = next(iter(classes))
        if hazard_class not in vehicle.compatible_classes:
            return failed(
                (f"{vehicle.vehicle_id}: incompatible with class {hazard_class}.",),
                trip_evaluations,
            )
        if day_hazard_class is None:
            day_hazard_class = hazard_class
        elif day_hazard_class != hazard_class:
            return failed(
                (f"{vehicle.vehicle_id}: class change during planning day.",),
                trip_evaluations,
            )

        initial_load = sum(instance.customers[item].demand_kg for item in sequence)
        if initial_load > vehicle.capacity_kg + EPSILON:
            return failed(
                (f"{vehicle.vehicle_id}: capacity_infeasible on trip {trip_index}.",),
                trip_evaluations,
            )

        remaining_load = initial_load
        pretrip_visits: List[VisitRecord] = []
        pretrip_charging = 0.0
        pretrip_break = 0.0
        pretrip_charge_cost = 0.0
        if trip_index == 1:
            activity_start = current_time
            current_time += vehicle.initial_load_minutes
            pretrip_visits.append(
                VisitRecord(
                    DEPOT,
                    "initial_loading",
                    activity_start,
                    current_time,
                    0.0,
                    remaining_load,
                    battery,
                    battery,
                )
            )
        else:
            reload_start = current_time
            current_time += vehicle.reload_minutes
            pretrip_visits.append(
                VisitRecord(
                    DEPOT,
                    "depot_reload",
                    reload_start,
                    current_time,
                    0.0,
                    remaining_load,
                    battery,
                    battery,
                )
            )
            charged_energy = vehicle.usable_battery_kwh - battery
            if charged_energy > EPSILON:
                effective_power = min(
                    instance.depot_charging_power_kw,
                    vehicle.max_charging_power_kw,
                )
                if effective_power <= 0:
                    return failed(
                        (f"{vehicle.vehicle_id}: invalid depot charging power.",),
                        trip_evaluations,
                    )
                charge_minutes = charged_energy / effective_power * 60.0
                charge_start = current_time
                current_time += charge_minutes
                charge_cost = (
                    charged_energy * instance.depot_energy_price_per_kwh
                )
                total_charging += charge_minutes
                total_station_charge_cost += charge_cost
                pretrip_charging = charge_minutes
                pretrip_charge_cost = charge_cost
                battery_arrival = battery
                battery = vehicle.usable_battery_kwh
                break_minutes = 0.0
                if (
                    DEPOT in instance.break_nodes
                    and charge_minutes + EPSILON >= instance.break_duration_minutes
                ):
                    continuous_driving = 0.0
                    total_break += instance.break_duration_minutes
                    pretrip_break = instance.break_duration_minutes
                    break_minutes = instance.break_duration_minutes
                pretrip_visits.append(
                    VisitRecord(
                        DEPOT,
                        "depot_charging",
                        charge_start,
                        current_time,
                        0.0,
                        remaining_load,
                        battery_arrival,
                        battery,
                        charged_energy,
                        charge_minutes,
                        break_minutes,
                    )
                )

        if current_time > vehicle.shift_end_minute + EPSILON:
            return failed(
                (f"{vehicle.vehicle_id}: shift_infeasible before trip {trip_index}.",),
                trip_evaluations,
            )

        trip_start = current_time
        current_stop = DEPOT
        route_stops: List[str] = [DEPOT]
        leg_records: List[LegRecord] = []
        visit_records: List[VisitRecord] = [
            *pretrip_visits,
            VisitRecord(
                DEPOT,
                "depot_departure",
                trip_start,
                trip_start,
                0.0,
                remaining_load,
                battery,
                battery,
            )
        ]
        trip_risk = 0.0
        trip_distance = 0.0
        trip_travel = 0.0
        trip_service = 0.0
        trip_waiting = 0.0
        trip_charging = pretrip_charging
        trip_break = pretrip_break
        trip_road_cost = 0.0
        trip_charge_cost = pretrip_charge_cost
        trip_min_battery = battery

        def take_break_if_required(next_leg: Leg) -> Optional[str]:
            nonlocal current_time, continuous_driving, total_break, trip_break
            break_minutes = _departure_break_minutes(
                instance,
                current_stop,
                next_leg,
                continuous_driving,
            )
            if break_minutes is None:
                location = (
                    f"on {current_stop}->{next_leg.to_stop}"
                    if (
                        next_leg.travel_minutes
                        > instance.continuous_driving_limit_minutes
                        + EPSILON
                    )
                    else f"at {current_stop}"
                )
                return f"{vehicle.vehicle_id}: break_infeasible {location}."
            if break_minutes <= EPSILON:
                return None
            break_start = current_time
            current_time += break_minutes
            trip_break += break_minutes
            total_break += break_minutes
            continuous_driving = 0.0
            visit_records.append(
                VisitRecord(
                    current_stop,
                    "driver_break",
                    break_start,
                    current_time,
                    0.0,
                    remaining_load,
                    battery,
                    battery,
                    break_minutes=break_minutes,
                )
            )
            return None

        def travel(to_stop: str, loaded: bool) -> Optional[str]:
            nonlocal current_stop
            nonlocal current_time
            nonlocal battery
            nonlocal continuous_driving
            nonlocal daily_driving
            nonlocal trip_risk
            nonlocal trip_distance
            nonlocal trip_travel
            nonlocal trip_road_cost
            nonlocal trip_min_battery
            nonlocal total_risk
            nonlocal total_distance
            nonlocal total_travel
            nonlocal total_road_cost

            leg = _leg(instance, current_stop, to_stop, hazard_class)
            if leg is None:
                return (
                    f"{vehicle.vehicle_id}: no_legal_path "
                    f"{current_stop}->{to_stop} for class {hazard_class}."
                )
            break_error = take_break_if_required(leg)
            if break_error:
                return break_error

            energy = leg.distance_km * vehicle.energy_kwh_per_km
            battery_after = battery - energy
            if battery_after < vehicle.min_reserve_kwh - EPSILON:
                return (
                    f"{vehicle.vehicle_id}: charging_infeasible "
                    f"{current_stop}->{to_stop}."
                )

            risk = (
                leg.base_risk_rate_per_km
                * _hazard_factor(hazard_class)
                * leg.distance_km
                if loaded
                else 0.0
            )
            road_cost = leg.distance_km * vehicle.road_cost_per_km
            leg_records.append(
                LegRecord(
                    current_stop,
                    to_stop,
                    loaded,
                    leg.distance_km,
                    leg.travel_minutes,
                    risk,
                    energy,
                    road_cost,
                    battery,
                    battery_after,
                )
            )
            battery = battery_after
            trip_min_battery = min(trip_min_battery, battery)
            current_time += leg.travel_minutes
            continuous_driving += leg.travel_minutes
            daily_driving += leg.travel_minutes
            trip_risk += risk
            total_risk += risk
            trip_distance += leg.distance_km
            total_distance += leg.distance_km
            trip_travel += leg.travel_minutes
            total_travel += leg.travel_minutes
            trip_road_cost += road_cost
            total_road_cost += road_cost
            current_stop = to_stop
            route_stops.append(to_stop)
            if daily_driving > vehicle.max_daily_driving_minutes + EPSILON:
                return f"{vehicle.vehicle_id}: daily driving limit exceeded."
            if current_time > vehicle.shift_end_minute + EPSILON:
                return f"{vehicle.vehicle_id}: shift_infeasible while travelling."
            return None

        targets = list(sequence) + [DEPOT]
        for target_index, target in enumerate(targets):
            direct = _leg(instance, current_stop, target, hazard_class)
            if direct is None:
                return failed(
                    (
                        f"{vehicle.vehicle_id}: no_legal_path "
                        f"{current_stop}->{target}.",
                    ),
                    trip_evaluations,
                )
            direct_energy = direct.distance_km * vehicle.energy_kwh_per_km
            energy_repair_needed = (
                battery - direct_energy
                < vehicle.min_reserve_kwh - EPSILON
            )
            break_repair_needed = (
                continuous_driving + direct.travel_minutes
                > instance.continuous_driving_limit_minutes + EPSILON
                and current_stop not in instance.break_nodes
            )
            remaining_targets = targets[target_index + 1:]
            proactive_status = _proactive_repair_status(
                instance,
                vehicle,
                FeasibilityState(
                    current_stop=current_stop,
                    battery_kwh=battery,
                    current_time=current_time,
                    continuous_driving_minutes=continuous_driving,
                    daily_driving_minutes=daily_driving,
                    remaining_load_kg=remaining_load,
                ),
                target,
                remaining_targets,
                hazard_class,
                objective_scales,
                charging_branch_counter,
            )
            if proactive_status.status == "incomplete":
                return failed(
                    (
                        f"{vehicle.vehicle_id}: "
                        "charging_search_incomplete before "
                        f"{current_stop}->{target}.",
                    ),
                    trip_evaluations,
                )
            if proactive_status.status == "terminal_failure":
                failure_reason = _select_failure_reason(
                    proactive_status.failure_reasons
                )
                return failed(
                    (
                        failure_reason
                        or (
                            f"{vehicle.vehicle_id}: "
                            "continuation_infeasible."
                        ),
                    ),
                    trip_evaluations,
                )
            proactive_repair_needed = (
                proactive_status.status == "needed"
            )
            proactive_fallback_reason = (
                _select_nonrepairable_failure_reason(
                    proactive_status.failure_reasons
                )
                if proactive_repair_needed
                else None
            )
            if (
                energy_repair_needed
                or break_repair_needed
                or proactive_repair_needed
            ):
                side_trip_origin = current_stop
                if side_trip_origin not in instance.customers:
                    reason = (
                        "charging_infeasible"
                        if energy_repair_needed or proactive_repair_needed
                        else "break_infeasible"
                    )
                    return failed(
                        (
                            f"{vehicle.vehicle_id}: {reason} before "
                            f"{current_stop}->{target}.",
                        ),
                        trip_evaluations,
                    )
                side_trip_plans = _side_trip_plans(
                    instance,
                    vehicle,
                    side_trip_origin,
                    target,
                    hazard_class,
                    battery,
                    current_time,
                    continuous_driving,
                    daily_driving,
                    remaining_load,
                    objective_scales,
                )
                if not side_trip_plans:
                    if proactive_fallback_reason:
                        return failed(
                            (proactive_fallback_reason,),
                            trip_evaluations,
                        )
                    reason = (
                        "charging_infeasible"
                        if energy_repair_needed or proactive_repair_needed
                        else "break_infeasible"
                    )
                    return failed(
                        (
                            f"{vehicle.vehicle_id}: {reason} before "
                            f"{current_stop}->{target}.",
                        ),
                        trip_evaluations,
                    )
                choice_key = (
                    trip_index,
                    target_index,
                    side_trip_origin,
                    target,
                )
                forced_station = (
                    _charging_overrides or {}
                ).get(choice_key)
                if forced_station is not None:
                    matching_plans = tuple(
                        plan
                        for plan in side_trip_plans
                        if plan.station_id == forced_station
                    )
                    if not matching_plans:
                        return failed(
                            (
                                f"{vehicle.vehicle_id}: forced charging "
                                f"station {forced_station} is infeasible.",
                            ),
                            trip_evaluations,
                        )
                    side_trip = matching_plans[0]
                elif len(side_trip_plans) > 1:
                    complete_alternatives = []
                    evaluated_station_ids = set()
                    scales = objective_scales or ObjectiveScales(
                        1.0,
                        1.0,
                        1.0,
                        True,
                    )
                    for plan in side_trip_plans:
                        if (
                            charging_branch_counter[0]
                            >= instance.max_charging_branch_evaluations
                        ):
                            break
                        charging_branch_counter[0] += 1
                        evaluated_station_ids.add(plan.station_id)
                        overrides = dict(_charging_overrides or {})
                        overrides[choice_key] = plan.station_id
                        alternative = evaluate_vehicle_schedule(
                            instance,
                            vehicle,
                            trip_sequences,
                            objective_scales=objective_scales,
                            _charging_overrides=overrides,
                            _charging_branch_counter=charging_branch_counter,
                        )
                        if not alternative.feasible:
                            continue
                        complete_alternatives.append(
                            (
                                _objective(
                                    alternative.total_risk,
                                    alternative.total_cost,
                                    alternative.operating_minutes,
                                    scales,
                                    instance.weights,
                                ),
                                alternative.total_risk,
                                alternative.total_cost,
                                alternative.operating_minutes,
                                plan.station_id,
                                alternative,
                            )
                        )
                    if complete_alternatives:
                        selected_alternative = min(
                            complete_alternatives,
                            key=lambda item: item[:-1],
                        )[-1]
                        return replace(
                            selected_alternative,
                            charging_branch_evaluations=(
                                charging_branch_counter[0]
                            ),
                        )
                    untested_plans = tuple(
                        plan
                        for plan in side_trip_plans
                        if plan.station_id not in evaluated_station_ids
                    )
                    if untested_plans:
                        station_ids = ", ".join(
                            plan.station_id for plan in untested_plans
                        )
                        return failed(
                            (
                                f"{vehicle.vehicle_id}: "
                                "charging_search_incomplete; "
                                f"untested stations: {station_ids}.",
                            ),
                            trip_evaluations,
                        )
                    else:
                        return failed(
                            (
                                proactive_fallback_reason
                                or (
                                    f"{vehicle.vehicle_id}: "
                                    "no complete schedule is feasible "
                                    "through a charging candidate before "
                                    f"{side_trip_origin}->{target}."
                                ),
                            ),
                            trip_evaluations,
                        )
                else:
                    side_trip = side_trip_plans[0]
                station_id = side_trip.station_id
                loaded = remaining_load > EPSILON
                travel_error = travel(station_id, loaded)
                if travel_error:
                    return failed(
                        (travel_error,),
                        trip_evaluations,
                    )

                arrival = current_time
                current_time += side_trip.stop_minutes
                battery_arrival = battery
                battery = vehicle.usable_battery_kwh
                trip_charging += side_trip.charging_minutes
                total_charging += side_trip.charging_minutes
                trip_charge_cost += side_trip.station_charging_cost
                total_station_charge_cost += (
                    side_trip.station_charging_cost
                )
                if side_trip.break_minutes > EPSILON:
                    continuous_driving = 0.0
                    trip_break += side_trip.break_minutes
                    total_break += side_trip.break_minutes
                visit_records.append(
                    VisitRecord(
                        station_id,
                        "charging_station",
                        arrival,
                        current_time,
                        0.0,
                        remaining_load,
                        battery_arrival,
                        battery,
                        side_trip.charged_energy_kwh,
                        side_trip.charging_minutes,
                        side_trip.break_minutes,
                    )
                )
                travel_error = travel(side_trip_origin, loaded)
                if travel_error:
                    return failed(
                        (travel_error,),
                        trip_evaluations,
                    )
                visit_records.append(
                    VisitRecord(
                        side_trip_origin,
                        "customer_revisit",
                        current_time,
                        current_time,
                        0.0,
                        remaining_load,
                        battery,
                        battery,
                    )
                )

            loaded = remaining_load > EPSILON
            travel_error = travel(target, loaded)
            if travel_error:
                return failed(
                    (travel_error,),
                    trip_evaluations,
                )

            if target == DEPOT:
                visit_records.append(
                    VisitRecord(
                        DEPOT,
                        "depot_return",
                        current_time,
                        current_time,
                        0.0,
                        remaining_load,
                        battery,
                        battery,
                    )
                )
                continue

            customer = instance.customers[target]
            arrival = current_time
            service_start = max(arrival, customer.earliest_minute)
            if service_start > customer.latest_minute + EPSILON:
                return failed(
                    (f"{vehicle.vehicle_id}: time_window_infeasible at {target}.",),
                    trip_evaluations,
                )
            waiting = service_start - arrival
            current_time = service_start + customer.service_minutes
            remaining_load -= customer.demand_kg
            trip_waiting += waiting
            total_waiting += waiting
            trip_service += customer.service_minutes
            total_service += customer.service_minutes
            visit_records.append(
                VisitRecord(
                    target,
                    "customer",
                    arrival,
                    current_time,
                    customer.demand_kg,
                    remaining_load,
                    battery,
                    battery,
                )
            )

        if current_time - first_activity > vehicle.max_daily_working_minutes + EPSILON:
            return failed(
                (f"{vehicle.vehicle_id}: daily working limit exceeded.",),
                trip_evaluations,
            )

        trip_evaluations.append(
            TripEvaluation(
                trip_index,
                hazard_class,
                tuple(sequence),
                tuple(route_stops),
                tuple(visit_records),
                tuple(leg_records),
                trip_start,
                current_time,
                initial_load,
                battery,
                trip_min_battery,
                trip_risk,
                trip_road_cost,
                trip_charge_cost,
                vehicle.trip_cost,
                trip_travel,
                trip_service,
                trip_waiting,
                trip_charging,
                trip_break,
            )
        )

    end_of_day_recharge = max(0.0, vehicle.initial_battery_kwh - battery)
    end_of_day_recharge_cost = (
        end_of_day_recharge * instance.depot_energy_price_per_kwh
    )
    activation_cost = vehicle.activation_cost
    trip_cost = len(trip_evaluations) * vehicle.trip_cost
    total_cost = (
        activation_cost
        + trip_cost
        + total_road_cost
        + total_station_charge_cost
        + end_of_day_recharge_cost
    )
    last_return = trip_evaluations[-1].return_minute
    return VehicleScheduleEvaluation(
        vehicle_id=vehicle.vehicle_id,
        feasible=True,
        reasons=tuple(),
        trips=tuple(trip_evaluations),
        activation_cost=activation_cost,
        trip_cost=trip_cost,
        road_operating_cost=total_road_cost,
        station_charging_cost=total_station_charge_cost,
        end_of_day_recharge_kwh=end_of_day_recharge,
        end_of_day_recharge_cost=end_of_day_recharge_cost,
        total_cost=total_cost,
        total_risk=total_risk,
        total_distance_km=total_distance,
        total_travel_minutes=total_travel,
        total_service_minutes=total_service,
        total_waiting_minutes=total_waiting,
        total_charging_minutes=total_charging,
        total_break_minutes=total_break,
        operating_minutes=last_return - first_activity,
        first_activity_minute=first_activity,
        last_return_minute=last_return,
        final_battery_kwh=battery,
        charging_branch_evaluations=charging_branch_counter[0],
    )


def _objective(
    risk: float,
    cost: float,
    operating_minutes: float,
    scales: ObjectiveScales,
    weights: ObjectiveWeights,
) -> float:
    return (
        (
            weights.risk * risk / scales.risk
            if scales.risk_active
            else 0.0
        )
        + weights.cost * cost / scales.cost
        + weights.time * operating_minutes / scales.time
    )


def evaluate_solution(
    instance: ToyInstance,
    schedules: Mapping[str, Sequence[Sequence[str]]],
    scales: ObjectiveScales,
    *,
    require_all_customers: bool,
    _charging_branch_counter: Optional[List[int]] = None,
) -> SolutionEvaluation:
    """Evaluate complete or partial physical-vehicle schedules."""
    charging_branch_counter = (
        _charging_branch_counter
        if _charging_branch_counter is not None
        else [0]
    )
    frozen = _freeze_schedules(schedules)
    reasons: List[str] = []
    vehicle_evaluations: Dict[str, VehicleScheduleEvaluation] = {}
    served: List[str] = []

    unknown_vehicles = sorted(set(frozen) - set(instance.vehicles))
    for vehicle_id in unknown_vehicles:
        reasons.append(f"Unknown physical vehicle {vehicle_id}.")

    for vehicle_id, vehicle in instance.vehicles.items():
        evaluation = evaluate_vehicle_schedule(
            instance,
            vehicle,
            frozen.get(vehicle_id, tuple()),
            objective_scales=scales,
            _charging_branch_counter=charging_branch_counter,
        )
        vehicle_evaluations[vehicle_id] = evaluation
        reasons.extend(evaluation.reasons)
        for trip in frozen.get(vehicle_id, tuple()):
            served.extend(trip)

    duplicate_customers = sorted(
        customer_id for customer_id in set(served) if served.count(customer_id) > 1
    )
    if duplicate_customers:
        reasons.append(
            "Customers served more than once: " + ", ".join(duplicate_customers)
        )

    unknown_customers = sorted(set(served) - set(instance.customers))
    if unknown_customers:
        reasons.append("Unknown customers: " + ", ".join(unknown_customers))

    served_known = sorted(set(served) & set(instance.customers))
    unserved = sorted(set(instance.customers) - set(served_known))
    if require_all_customers and unserved:
        reasons.append("Unserved customers: " + ", ".join(unserved))

    total_risk = sum(item.total_risk for item in vehicle_evaluations.values())
    total_cost = sum(item.total_cost for item in vehicle_evaluations.values())
    total_time = sum(item.operating_minutes for item in vehicle_evaluations.values())
    makespan = max(
        (
            item.last_return_minute or 0.0
            for item in vehicle_evaluations.values()
        ),
        default=0.0,
    )
    feasible = not reasons and all(
        item.feasible for item in vehicle_evaluations.values()
    )
    return SolutionEvaluation(
        feasible=feasible,
        reasons=tuple(reasons),
        schedules=frozen,
        vehicle_evaluations=vehicle_evaluations,
        served_customers=tuple(served_known),
        unserved_customers=tuple(unserved),
        objective=_objective(
            total_risk,
            total_cost,
            total_time,
            scales,
            instance.weights,
        ),
        total_risk=total_risk,
        total_cost=total_cost,
        total_activation_cost=sum(
            item.activation_cost for item in vehicle_evaluations.values()
        ),
        total_trip_cost=sum(item.trip_cost for item in vehicle_evaluations.values()),
        total_road_operating_cost=sum(
            item.road_operating_cost for item in vehicle_evaluations.values()
        ),
        total_station_charging_cost=sum(
            item.station_charging_cost for item in vehicle_evaluations.values()
        ),
        total_end_of_day_recharge_cost=sum(
            item.end_of_day_recharge_cost for item in vehicle_evaluations.values()
        ),
        total_distance_km=sum(
            item.total_distance_km for item in vehicle_evaluations.values()
        ),
        total_travel_minutes=sum(
            item.total_travel_minutes for item in vehicle_evaluations.values()
        ),
        total_service_minutes=sum(
            item.total_service_minutes for item in vehicle_evaluations.values()
        ),
        total_waiting_minutes=sum(
            item.total_waiting_minutes for item in vehicle_evaluations.values()
        ),
        total_charging_minutes=sum(
            item.total_charging_minutes for item in vehicle_evaluations.values()
        ),
        total_break_minutes=sum(
            item.total_break_minutes for item in vehicle_evaluations.values()
        ),
        total_time_minutes=total_time,
        makespan_minute=makespan,
        charging_branch_evaluations=charging_branch_counter[0],
    )


def compute_reference_scales(instance: ToyInstance) -> ObjectiveScales:
    """Build fixed scales from feasible single-customer reference trips."""
    _validate_weights(instance.weights)
    reference_risk = 0.0
    reference_cost = 0.0
    reference_time = 0.0
    temporary_scales = ObjectiveScales(1.0, 1.0, 1.0, True)
    criterion_instances = {
        "risk": replace(
            instance,
            weights=ObjectiveWeights(risk=1.0, cost=0.0, time=0.0),
        ),
        "cost": replace(
            instance,
            weights=ObjectiveWeights(risk=0.0, cost=1.0, time=0.0),
        ),
        "time": replace(
            instance,
            weights=ObjectiveWeights(risk=0.0, cost=0.0, time=1.0),
        ),
    }

    for customer_id in sorted(instance.customers):
        evaluations = {
            criterion: []
            for criterion in criterion_instances
        }
        infeasible_reasons: List[str] = []
        for vehicle in instance.vehicles.values():
            for criterion, criterion_instance in (
                criterion_instances.items()
            ):
                evaluation = evaluate_vehicle_schedule(
                    criterion_instance,
                    vehicle,
                    ((customer_id,),),
                )
                if evaluation.feasible:
                    evaluations[criterion].append(evaluation)
                elif criterion == "cost":
                    infeasible_reasons.extend(evaluation.reasons)
        if not evaluations["cost"]:
            raise NoFeasibleCustomerError(
                customer_id,
                infeasible_reasons,
            )
        reference_risk += min(
            item.total_risk for item in evaluations["risk"]
        )
        reference_cost += min(
            item.total_cost for item in evaluations["cost"]
        )
        reference_time += min(
            item.operating_minutes for item in evaluations["time"]
        )

    risk_active = reference_risk > EPSILON
    return ObjectiveScales(
        risk=reference_risk if risk_active else temporary_scales.risk,
        cost=reference_cost if reference_cost > EPSILON else temporary_scales.cost,
        time=reference_time if reference_time > EPSILON else temporary_scales.time,
        risk_active=risk_active,
    )


def _candidate_key(
    current: SolutionEvaluation,
    candidate: SolutionEvaluation,
    vehicle_id: str,
    trip_index: int,
    customer_id: str,
    insertion_position: int,
) -> Tuple[float, float, float, float, str, int, str, int]:
    return (
        candidate.objective - current.objective,
        candidate.total_risk - current.total_risk,
        candidate.total_cost - current.total_cost,
        candidate.total_time_minutes - current.total_time_minutes,
        vehicle_id,
        trip_index,
        customer_id,
        insertion_position,
    )


def _empty_failure_solution(
    instance: ToyInstance,
    reason: str,
) -> SolutionEvaluation:
    return SolutionEvaluation(
        feasible=False,
        reasons=(reason,),
        schedules={
            vehicle_id: tuple() for vehicle_id in instance.vehicles
        },
        vehicle_evaluations={},
        served_customers=tuple(),
        unserved_customers=tuple(sorted(instance.customers)),
        objective=0.0,
        total_risk=0.0,
        total_cost=0.0,
        total_activation_cost=0.0,
        total_trip_cost=0.0,
        total_road_operating_cost=0.0,
        total_station_charging_cost=0.0,
        total_end_of_day_recharge_cost=0.0,
        total_distance_km=0.0,
        total_travel_minutes=0.0,
        total_service_minutes=0.0,
        total_waiting_minutes=0.0,
        total_charging_minutes=0.0,
        total_break_minutes=0.0,
        total_time_minutes=0.0,
        makespan_minute=0.0,
    )


def _search_limit_reached(reasons: Iterable[str]) -> bool:
    return any(
        "charging_search_incomplete" in reason
        for reason in reasons
    )


def construct_initial_solution(instance: ToyInstance) -> HeuristicRun:
    """Construct deterministic vehicle trips by sequential best insertion."""
    start = time.perf_counter()
    try:
        validate_instance(instance)
        scales = compute_reference_scales(instance)
    except InputDataError as error:
        scales = ObjectiveScales(1.0, 1.0, 1.0, False)
        return HeuristicRun(
            "input_data_error",
            _empty_failure_solution(
                instance,
                f"input_data_error: {error}",
            ),
            scales,
            time.perf_counter() - start,
        )
    except NoFeasibleCustomerError as error:
        scales = ObjectiveScales(1.0, 1.0, 1.0, False)
        empty_schedules = {
            vehicle_id: [] for vehicle_id in instance.vehicles
        }
        evaluation = evaluate_solution(
            instance,
            empty_schedules,
            scales,
            require_all_customers=True,
        )
        diagnostic = (
            f"Customer {error.customer_id} has no feasible "
            "single-customer trip: "
            + " | ".join(error.reasons)
        )
        return HeuristicRun(
            (
                "search_limit_reached"
                if _search_limit_reached(error.reasons)
                else "infeasible"
            ),
            replace(
                evaluation,
                feasible=False,
                reasons=(diagnostic, *evaluation.reasons),
            ),
            scales,
            time.perf_counter() - start,
        )
    schedules: Dict[str, List[List[str]]] = {
        vehicle_id: [] for vehicle_id in instance.vehicles
    }
    unserved = set(instance.customers)
    insertion_rejections: Dict[str, set[str]] = {}
    current_evaluation = evaluate_solution(
        instance,
        schedules,
        scales,
        require_all_customers=False,
    )

    while unserved:
        seed_candidates = []
        feasible_seed_customers = set()
        rejected_reasons = {
            customer_id: set() for customer_id in unserved
        }
        for vehicle_id in sorted(instance.vehicles):
            for customer_id in sorted(unserved):
                proposal = _copy_schedules(schedules)
                proposal[vehicle_id].append([customer_id])
                evaluation = evaluate_solution(
                    instance,
                    proposal,
                    scales,
                    require_all_customers=False,
                )
                if not evaluation.feasible:
                    rejected_reasons[customer_id].update(
                        evaluation.reasons
                    )
                    continue
                key = _candidate_key(
                    current_evaluation,
                    evaluation,
                    vehicle_id,
                    len(proposal[vehicle_id]) - 1,
                    customer_id,
                    0,
                )
                feasible_seed_customers.add(customer_id)
                seed_candidates.append((key, proposal, evaluation, vehicle_id))

        for customer_id in feasible_seed_customers:
            insertion_rejections.pop(customer_id, None)

        if not seed_candidates:
            final_evaluation = evaluate_solution(
                instance,
                schedules,
                scales,
                require_all_customers=True,
            )
            diagnostics = tuple(
                f"Customer {customer_id} rejected: "
                + " | ".join(
                    sorted(
                        rejected_reasons[customer_id]
                        | insertion_rejections.get(
                            customer_id,
                            set(),
                        )
                    )
                )
                for customer_id in sorted(unserved)
                if (
                    rejected_reasons[customer_id]
                    or insertion_rejections.get(customer_id)
                )
            )
            final_evaluation = replace(
                final_evaluation,
                reasons=(*final_evaluation.reasons, *diagnostics),
            )
            return HeuristicRun(
                (
                    "search_limit_reached"
                    if _search_limit_reached(
                        final_evaluation.reasons
                    )
                    else "partial_infeasible"
                ),
                final_evaluation,
                scales,
                time.perf_counter() - start,
            )

        _, schedules, current_evaluation, current_vehicle_id = min(
            seed_candidates,
            key=lambda item: item[0],
        )
        seeded_customer = schedules[current_vehicle_id][-1][0]
        unserved.remove(seeded_customer)
        insertion_rejections.pop(seeded_customer, None)
        current_trip_index = len(schedules[current_vehicle_id]) - 1

        while unserved:
            insertion_candidates = []
            iteration_rejections = {
                customer_id: set() for customer_id in unserved
            }
            feasible_insertion_customers = set()
            current_trip = schedules[current_vehicle_id][current_trip_index]
            for customer_id in sorted(unserved):
                for position in range(len(current_trip) + 1):
                    proposal = _copy_schedules(schedules)
                    proposal[current_vehicle_id][current_trip_index].insert(
                        position,
                        customer_id,
                    )
                    evaluation = evaluate_solution(
                        instance,
                        proposal,
                        scales,
                        require_all_customers=False,
                    )
                    if not evaluation.feasible:
                        iteration_rejections[customer_id].update(
                            evaluation.reasons
                        )
                        continue
                    feasible_insertion_customers.add(customer_id)
                    key = _candidate_key(
                        current_evaluation,
                        evaluation,
                        current_vehicle_id,
                        current_trip_index,
                        customer_id,
                        position,
                    )
                    insertion_candidates.append(
                        (key, proposal, evaluation, customer_id)
                    )
            for customer_id in tuple(unserved):
                if customer_id in feasible_insertion_customers:
                    insertion_rejections.pop(customer_id, None)
                elif iteration_rejections[customer_id]:
                    insertion_rejections.setdefault(
                        customer_id,
                        set(),
                    ).update(iteration_rejections[customer_id])
            if not insertion_candidates:
                break
            _, schedules, current_evaluation, inserted_customer = min(
                insertion_candidates,
                key=lambda item: item[0],
            )
            unserved.remove(inserted_customer)
            insertion_rejections.pop(inserted_customer, None)

    final_evaluation = evaluate_solution(
        instance,
        schedules,
        scales,
        require_all_customers=True,
    )
    return HeuristicRun(
        (
            "feasible"
            if final_evaluation.feasible
            else (
                "search_limit_reached"
                if _search_limit_reached(
                    final_evaluation.reasons
                )
                else "infeasible"
            )
        ),
        final_evaluation,
        scales,
        time.perf_counter() - start,
    )


def solver_warm_start_routes(
    evaluation: SolutionEvaluation,
) -> Dict[str, Tuple[Tuple[str, ...], ...]]:
    """Return evaluated routes, including charging and technical revisits."""
    return {
        vehicle_id: tuple(
            trip.stop_sequence
            for trip in vehicle_evaluation.trips
        )
        for vehicle_id, vehicle_evaluation
        in evaluation.vehicle_evaluations.items()
        if vehicle_evaluation.trips
    }


def build_heuristic_routes(
    instance: ToyInstance,
    evaluation: SolutionEvaluation,
) -> Dict[str, List[str]]:
    """Build the solver's flat customer-and-depot warm-start dictionary."""
    if not evaluation.feasible:
        raise ValueError(
            "heuristic_routes can only be exported from a feasible solution."
        )
    routes: Dict[str, List[str]] = {}
    for vehicle_id, vehicle_evaluation in (
        evaluation.vehicle_evaluations.items()
    ):
        if not vehicle_evaluation.trips:
            continue
        vehicle = instance.vehicles[vehicle_id]
        solver_name = vehicle.solver_name or vehicle.vehicle_type
        if solver_name in routes:
            raise ValueError(
                f"Duplicate solver vehicle name: {solver_name}."
            )

        flattened: List[str] = []
        for trip in vehicle_evaluation.trips:
            stops = [DEPOT, *trip.customer_sequence, DEPOT]
            if (
                flattened
                and flattened[-1] == DEPOT
                and stops
                and stops[0] == DEPOT
            ):
                flattened.extend(stops[1:])
            else:
                flattened.extend(stops)
        routes[solver_name] = flattened
    return routes


def summarize_run(run: HeuristicRun) -> str:
    """Create a compact, presentation-friendly text summary."""
    result = run.evaluation
    lines = [
        "Multi-customer HazMat heuristic toy result",
        "-" * 43,
        f"status={run.status}",
    ]
    for vehicle_id, routes in solver_warm_start_routes(result).items():
        for trip_index, route in enumerate(routes, start=1):
            lines.append(
                f"{vehicle_id} trip {trip_index}: {' -> '.join(route)}"
            )
    lines.extend(
        [
            f"served_customers={len(result.served_customers)}",
            f"unserved_customers={len(result.unserved_customers)}",
            f"total_risk={result.total_risk:.4f}",
            f"total_cost={result.total_cost:.2f}",
            f"total_time_minutes={result.total_time_minutes:.2f}",
            f"makespan_minute={result.makespan_minute:.2f}",
            f"objective={result.objective:.6f}",
            (
                "charging_branch_evaluations="
                f"{result.charging_branch_evaluations}"
            ),
            f"runtime_seconds={run.runtime_seconds:.6f}",
        ]
    )
    if result.reasons:
        lines.append("reasons=" + " | ".join(result.reasons))
    return "\n".join(lines)


def main() -> None:
    instance = build_toy_instance()
    run = construct_initial_solution(instance)
    print(summarize_run(run))
    heuristic_routes = build_heuristic_routes(instance, run.evaluation)
    print()
    print("heuristic_routes = " + pformat(heuristic_routes, sort_dicts=False))


if __name__ == "__main__":
    main()
