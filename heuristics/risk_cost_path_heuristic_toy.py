"""Toy prototype for the HMVRP risk-cost path heuristic.

This is not the final real-data implementation. It uses a small hardcoded
instance to show the lower-level OD logic documented in README.md:

- filter forbidden edges by hazardous-material class;
- generate candidate origin-destination paths;
- assign deliveries to electric trucks under cumulative capacity and range;
- try simple local improvements;
- print a compact, solver-comparable summary.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


ALPHA = 0.45
BETA = 0.35
GAMMA = 0.20
W_RISK = 0.65
W_COST = 0.35


@dataclass(frozen=True)
class Edge:
    edge_id: str
    from_node: str
    to_node: str
    length: float
    pop_density: float
    accident_rate: float
    nature_proximity: float
    allowed_classes: Tuple[str, ...]


@dataclass(frozen=True)
class Vehicle:
    vehicle_id: str
    capacity: float
    range_km: float
    fixed_cost: float
    variable_cost_per_km: float
    energy_kwh_per_km: float
    energy_price: float


@dataclass(frozen=True)
class Delivery:
    delivery_id: str
    origin: str
    destination: str
    demand: float
    class_id: str


@dataclass(frozen=True)
class PathCandidate:
    delivery_id: str
    edges: Tuple[str, ...]
    nodes: Tuple[str, ...]
    length: float
    risk: float


@dataclass
class Assignment:
    delivery_id: str
    vehicle_id: str
    path: PathCandidate


@dataclass
class Solution:
    assignments: Dict[str, Assignment]
    objective: float
    total_risk: float
    total_cost: float
    runtime_seconds: float
    feasible: bool
    messages: List[str]


@dataclass(frozen=True)
class Instance:
    nodes: Tuple[str, ...]
    edges: Dict[str, Edge]
    vehicles: Dict[str, Vehicle]
    deliveries: Dict[str, Delivery]


def build_toy_instance() -> Instance:
    """Create a small artificial instance with legal restrictions."""
    edges = {
        "e1": Edge("e1", "depot", "a", 35, 0.20, 0.15, 0.10, ("class_3", "class_8")),
        "e2": Edge("e2", "depot", "b", 30, 0.50, 0.20, 0.15, ("class_3", "class_8")),
        "e3": Edge("e3", "a", "c", 25, 0.25, 0.20, 0.20, ("class_3", "class_8")),
        "e4": Edge("e4", "b", "c", 20, 0.65, 0.25, 0.40, ("class_3",)),
        "e5": Edge("e5", "b", "d", 30, 0.30, 0.10, 0.15, ("class_3", "class_8")),
        "e6": Edge("e6", "c", "plant", 35, 0.55, 0.30, 0.35, ("class_3",)),
        "e7": Edge("e7", "c", "terminal", 25, 0.15, 0.15, 0.10, ("class_3", "class_8")),
        "e8": Edge("e8", "d", "plant", 25, 0.20, 0.10, 0.55, ("class_8",)),
        "e9": Edge("e9", "d", "terminal", 20, 0.25, 0.10, 0.15, ("class_3", "class_8")),
        "e10": Edge("e10", "terminal", "plant", 25, 0.30, 0.20, 0.20, ("class_3", "class_8")),
        "e11": Edge("e11", "a", "d", 45, 0.10, 0.10, 0.10, ("class_3", "class_8")),
    }
    vehicles = {
        "MAN_eTGX": Vehicle("MAN_eTGX", 18, 120, 180, 0.55, 0.96, 0.60),
        "Volvo_FH_Electric": Vehicle("Volvo_FH_Electric", 24, 150, 200, 0.60, 1.15, 0.55),
        "Mercedes_eActros_600": Vehicle("Mercedes_eActros_600", 30, 170, 220, 0.65, 1.20, 0.50),
    }
    deliveries = {
        "lief_1": Delivery("lief_1", "depot", "plant", 10, "class_3"),
        "lief_2": Delivery("lief_2", "depot", "terminal", 12, "class_8"),
        "lief_3": Delivery("lief_3", "a", "plant", 8, "class_8"),
    }
    return Instance(
        nodes=("depot", "a", "b", "c", "d", "terminal", "plant"),
        edges=edges,
        vehicles=vehicles,
        deliveries=deliveries,
    )


def edge_risk(edge: Edge, class_id: str) -> float:
    """Return a simplified class-aware edge risk index."""
    severity = {"class_3": 1.00, "class_8": 1.15}.get(class_id, 1.00)
    base_risk = (
        ALPHA * edge.pop_density
        + BETA * edge.accident_rate
        + GAMMA * edge.nature_proximity
    )
    return base_risk * severity


def edge_cost(edge: Edge, vehicle: Vehicle) -> float:
    """Return vehicle-dependent edge cost."""
    return edge.length * (
        vehicle.variable_cost_per_km
        + vehicle.energy_kwh_per_km * vehicle.energy_price
    )


def _adjacency(edges: Dict[str, Edge]) -> Dict[str, List[Edge]]:
    adjacency: Dict[str, List[Edge]] = {}
    for edge in edges.values():
        adjacency.setdefault(edge.from_node, []).append(edge)
    return adjacency


def _path_candidate(
    delivery: Delivery,
    path_edges: Sequence[Edge],
) -> PathCandidate:
    nodes = [delivery.origin]
    total_length = 0.0
    total_risk = 0.0
    for edge in path_edges:
        nodes.append(edge.to_node)
        total_length += edge.length
        total_risk += edge_risk(edge, delivery.class_id)
    return PathCandidate(
        delivery_id=delivery.delivery_id,
        edges=tuple(edge.edge_id for edge in path_edges),
        nodes=tuple(nodes),
        length=total_length,
        risk=total_risk,
    )


def generate_candidate_paths(
    delivery: Delivery,
    edges: Dict[str, Edge],
    max_paths: int = 4,
    max_depth: int = 5,
) -> List[PathCandidate]:
    """Enumerate simple legal paths and keep a small diverse candidate set."""
    allowed_edges = {
        edge_id: edge
        for edge_id, edge in edges.items()
        if delivery.class_id in edge.allowed_classes
    }
    adjacency = _adjacency(allowed_edges)
    complete_paths: List[PathCandidate] = []
    stack: List[Tuple[str, Tuple[Edge, ...], Tuple[str, ...]]] = [
        (delivery.origin, tuple(), (delivery.origin,))
    ]

    while stack:
        node, path_edges, visited = stack.pop()
        if len(path_edges) > max_depth:
            continue
        if node == delivery.destination and path_edges:
            complete_paths.append(_path_candidate(delivery, path_edges))
            continue
        for edge in adjacency.get(node, []):
            if edge.to_node in visited:
                continue
            stack.append((edge.to_node, path_edges + (edge,), visited + (edge.to_node,)))

    if not complete_paths:
        return []

    selected: List[PathCandidate] = []
    orderings = [
        sorted(complete_paths, key=lambda path: path.risk),
        sorted(complete_paths, key=lambda path: path.length),
        sorted(complete_paths, key=lambda path: W_RISK * path.risk + W_COST * path.length / 100),
    ]
    for ordering in orderings:
        for path in ordering:
            if path not in selected:
                selected.append(path)
                break

    for path in sorted(complete_paths, key=lambda candidate: (candidate.risk, candidate.length)):
        if len(selected) >= max_paths:
            break
        if path not in selected:
            selected.append(path)

    return selected[:max_paths]


def _path_cost(path: PathCandidate, vehicle: Vehicle, edges: Dict[str, Edge]) -> float:
    return sum(edge_cost(edges[edge_id], vehicle) for edge_id in path.edges)


def _objective_value(
    total_risk: float,
    total_cost: float,
    risk_scale: float,
    cost_scale: float,
) -> float:
    normalized_risk = total_risk / risk_scale if risk_scale else total_risk
    normalized_cost = total_cost / cost_scale if cost_scale else total_cost
    return W_RISK * normalized_risk + W_COST * normalized_cost


def _objective_scales(
    candidate_paths: Dict[str, List[PathCandidate]],
    instance: Instance,
) -> Tuple[float, float]:
    risk_scale = sum(max(path.risk for path in paths) for paths in candidate_paths.values())
    max_variable_cost_by_delivery = [
        max(
            _path_cost(path, vehicle, instance.edges)
            for path in paths
            for vehicle in instance.vehicles.values()
        )
        for paths in candidate_paths.values()
    ]
    cost_scale = sum(max_variable_cost_by_delivery) + sum(
        vehicle.fixed_cost for vehicle in instance.vehicles.values()
    )
    return risk_scale or 1.0, cost_scale or 1.0


def score_candidate(
    delivery: Delivery,
    vehicle: Vehicle,
    path: PathCandidate,
    edges: Dict[str, Edge],
    risk_scale: float,
    cost_scale: float,
    vehicle_is_active: bool,
) -> float:
    """Score one incremental delivery-vehicle-path combination."""
    incremental_cost = _path_cost(path, vehicle, edges)
    if not vehicle_is_active:
        incremental_cost += vehicle.fixed_cost
    return _objective_value(path.risk, incremental_cost, risk_scale, cost_scale)


def _total_solution_values(
    assignments: Dict[str, Assignment],
    instance: Instance,
    risk_scale: float,
    cost_scale: float,
) -> Tuple[float, float, float]:
    total_risk = sum(assignment.path.risk for assignment in assignments.values())
    active_vehicles = {assignment.vehicle_id for assignment in assignments.values()}
    fixed_cost = sum(instance.vehicles[vehicle_id].fixed_cost for vehicle_id in active_vehicles)
    variable_cost = sum(
        _path_cost(
            assignment.path,
            instance.vehicles[assignment.vehicle_id],
            instance.edges,
        )
        for assignment in assignments.values()
    )
    total_cost = fixed_cost + variable_cost
    objective = _objective_value(total_risk, total_cost, risk_scale, cost_scale)
    return objective, total_risk, total_cost


def construct_initial_solution(
    instance: Instance,
) -> Tuple[Solution, Dict[str, List[PathCandidate]], float, float]:
    """Build a first feasible solution by greedy risk-cost assignment."""
    start = time.perf_counter()
    candidate_paths = {
        delivery_id: generate_candidate_paths(delivery, instance.edges)
        for delivery_id, delivery in instance.deliveries.items()
    }
    messages: List[str] = []
    for delivery_id, paths in candidate_paths.items():
        if not paths:
            messages.append(f"No legal path found for {delivery_id}.")
            return (
                Solution({}, 0, 0, 0, time.perf_counter() - start, False, messages),
                candidate_paths,
                1.0,
                1.0,
            )

    risk_scale, cost_scale = _objective_scales(candidate_paths, instance)

    vehicle_loads = {vehicle_id: 0.0 for vehicle_id in instance.vehicles}
    assignments: Dict[str, Assignment] = {}
    delivery_order = sorted(
        instance.deliveries.values(),
        key=lambda delivery: (
            -delivery.demand,
            -min(path.length for path in candidate_paths[delivery.delivery_id]),
            -min(path.risk for path in candidate_paths[delivery.delivery_id]),
        ),
    )

    for delivery in delivery_order:
        best_score = float("inf")
        best_choice: Optional[Assignment] = None
        for path in candidate_paths[delivery.delivery_id]:
            for vehicle in instance.vehicles.values():
                if vehicle_loads[vehicle.vehicle_id] + delivery.demand > vehicle.capacity:
                    continue
                if path.length > vehicle.range_km:
                    continue
                score = score_candidate(
                    delivery,
                    vehicle,
                    path,
                    instance.edges,
                    risk_scale,
                    cost_scale,
                    vehicle.vehicle_id in {
                        assignment.vehicle_id for assignment in assignments.values()
                    },
                )
                if score < best_score:
                    best_score = score
                    best_choice = Assignment(delivery.delivery_id, vehicle.vehicle_id, path)
        if best_choice is None:
            messages.append(f"No feasible vehicle-path combination for {delivery.delivery_id}.")
            return (
                Solution(assignments, 0, 0, 0, time.perf_counter() - start, False, messages),
                candidate_paths,
                risk_scale,
                cost_scale,
            )
        assignments[delivery.delivery_id] = best_choice
        vehicle_loads[best_choice.vehicle_id] += delivery.demand

    objective, total_risk, total_cost = _total_solution_values(
        assignments,
        instance,
        risk_scale,
        cost_scale,
    )
    solution = Solution(
        assignments=assignments,
        objective=objective,
        total_risk=total_risk,
        total_cost=total_cost,
        runtime_seconds=time.perf_counter() - start,
        feasible=True,
        messages=messages,
    )
    return solution, candidate_paths, risk_scale, cost_scale


def validate_solution(solution: Solution, instance: Instance) -> Tuple[bool, List[str]]:
    """Check assignment, path, permission, capacity, and range feasibility."""
    errors: List[str] = []
    if set(solution.assignments) != set(instance.deliveries):
        errors.append("Not every delivery has exactly one assignment.")

    loads = {vehicle_id: 0.0 for vehicle_id in instance.vehicles}
    for delivery_id, assignment in solution.assignments.items():
        delivery = instance.deliveries[delivery_id]
        vehicle = instance.vehicles[assignment.vehicle_id]
        path = assignment.path
        current_node = delivery.origin
        nodes_from_edges = [delivery.origin]
        if not path.edges:
            errors.append(f"{delivery_id}: path has no edges.")
        for edge_id in path.edges:
            edge = instance.edges.get(edge_id)
            if edge is None:
                errors.append(f"{delivery_id}: unknown edge {edge_id}.")
                continue
            if edge.from_node != current_node:
                errors.append(f"{delivery_id}: edge sequence breaks at {edge_id}.")
            current_node = edge.to_node
            nodes_from_edges.append(current_node)
            if delivery.class_id not in edge.allowed_classes:
                errors.append(f"{delivery_id}: forbidden edge {edge_id} used.")
        if current_node != delivery.destination:
            errors.append(f"{delivery_id}: path does not connect origin to destination.")
        if tuple(nodes_from_edges) != path.nodes:
            errors.append(f"{delivery_id}: node sequence does not match edge sequence.")
        if path.length > vehicle.range_km:
            errors.append(f"{delivery_id}: path exceeds range of {vehicle.vehicle_id}.")
        loads[vehicle.vehicle_id] += delivery.demand

    for vehicle_id, load in loads.items():
        if load > instance.vehicles[vehicle_id].capacity:
            errors.append(f"{vehicle_id}: cumulative load exceeds capacity.")

    return not errors, errors


def _try_path_switch(
    solution: Solution,
    candidate_paths: Dict[str, List[PathCandidate]],
    instance: Instance,
    risk_scale: float,
    cost_scale: float,
) -> Solution:
    best_assignments = dict(solution.assignments)
    best_objective = solution.objective
    for delivery_id, assignment in solution.assignments.items():
        for path in candidate_paths[delivery_id]:
            if path == assignment.path:
                continue
            if path.length > instance.vehicles[assignment.vehicle_id].range_km:
                continue
            trial_assignments = dict(solution.assignments)
            trial_assignments[delivery_id] = Assignment(delivery_id, assignment.vehicle_id, path)
            trial_solution = _solution_from_assignments(
                trial_assignments,
                instance,
                solution.runtime_seconds,
                risk_scale,
                cost_scale,
            )
            feasible, _ = validate_solution(trial_solution, instance)
            if feasible and trial_solution.objective < best_objective:
                best_objective = trial_solution.objective
                best_assignments = trial_assignments
    return _solution_from_assignments(
        best_assignments,
        instance,
        solution.runtime_seconds,
        risk_scale,
        cost_scale,
    )


def _try_vehicle_reassignment(
    solution: Solution,
    instance: Instance,
    risk_scale: float,
    cost_scale: float,
) -> Solution:
    best_assignments = dict(solution.assignments)
    best_objective = solution.objective
    for delivery_id, assignment in solution.assignments.items():
        for vehicle_id, vehicle in instance.vehicles.items():
            if vehicle_id == assignment.vehicle_id:
                continue
            if assignment.path.length > vehicle.range_km:
                continue
            trial_assignments = dict(solution.assignments)
            trial_assignments[delivery_id] = Assignment(delivery_id, vehicle_id, assignment.path)
            trial_solution = _solution_from_assignments(
                trial_assignments,
                instance,
                solution.runtime_seconds,
                risk_scale,
                cost_scale,
            )
            feasible, _ = validate_solution(trial_solution, instance)
            if feasible and trial_solution.objective < best_objective:
                best_objective = trial_solution.objective
                best_assignments = trial_assignments
    return _solution_from_assignments(
        best_assignments,
        instance,
        solution.runtime_seconds,
        risk_scale,
        cost_scale,
    )


def _solution_from_assignments(
    assignments: Dict[str, Assignment],
    instance: Instance,
    runtime_seconds: float,
    risk_scale: float,
    cost_scale: float,
) -> Solution:
    objective, total_risk, total_cost = _total_solution_values(
        assignments,
        instance,
        risk_scale,
        cost_scale,
    )
    feasible, errors = validate_solution(
        Solution(assignments, objective, total_risk, total_cost, runtime_seconds, True, []),
        instance,
    )
    return Solution(assignments, objective, total_risk, total_cost, runtime_seconds, feasible, errors)


def improve_solution(
    solution: Solution,
    candidate_paths: Dict[str, List[PathCandidate]],
    instance: Instance,
    risk_scale: float,
    cost_scale: float,
) -> Solution:
    """Try a path switch and a vehicle reassignment improvement."""
    improved = _try_path_switch(solution, candidate_paths, instance, risk_scale, cost_scale)
    improved = _try_vehicle_reassignment(improved, instance, risk_scale, cost_scale)
    return improved


def summarize_solution(solution: Solution, instance: Instance) -> str:
    feasible, errors = validate_solution(solution, instance)
    active_vehicles = sorted({assignment.vehicle_id for assignment in solution.assignments.values()})
    loads = {vehicle_id: 0.0 for vehicle_id in instance.vehicles}
    lines = ["Toy HMVRP heuristic result", "-" * 30]
    for delivery_id in sorted(solution.assignments):
        assignment = solution.assignments[delivery_id]
        delivery = instance.deliveries[delivery_id]
        vehicle = instance.vehicles[assignment.vehicle_id]
        path = assignment.path
        loads[vehicle.vehicle_id] += delivery.demand
        lines.append(
            f"{delivery_id}: {assignment.vehicle_id}, "
            f"path {' -> '.join(path.nodes)}, "
            f"length={path.length:.1f}, risk={path.risk:.3f}, "
            f"variable_cost={_path_cost(path, vehicle, instance.edges):.2f}"
        )
    lines.extend(
        [
            "",
            f"total_risk={solution.total_risk:.3f}",
            f"total_cost={solution.total_cost:.2f}",
            f"objective={solution.objective:.3f}",
            f"active_vehicles={', '.join(active_vehicles)}",
            "capacity_usage="
            + ", ".join(
                f"{vehicle_id}: {loads[vehicle_id]:.1f}/{instance.vehicles[vehicle_id].capacity:.1f}"
                for vehicle_id in sorted(instance.vehicles)
            ),
            f"feasible={feasible}",
            f"runtime_seconds={solution.runtime_seconds:.6f}",
        ]
    )
    if errors:
        lines.append("errors=" + "; ".join(errors))
    return "\n".join(lines)


def main() -> None:
    start = time.perf_counter()
    instance = build_toy_instance()
    solution, candidate_paths, risk_scale, cost_scale = construct_initial_solution(instance)
    if solution.feasible:
        solution = improve_solution(solution, candidate_paths, instance, risk_scale, cost_scale)
    solution.runtime_seconds = time.perf_counter() - start
    print(summarize_solution(solution, instance))


if __name__ == "__main__":
    main()
