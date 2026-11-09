"""Deterministic, educational Mars rover path-planning *sandbox*.

No real terrain, rover command uplink or telemetry is used. NASA's published
AutoNav/global-localization concepts motivate the model; it is NOT NASA code.
The test map, energy/risk coefficients and latency reference are illustrative.
"""
from __future__ import annotations

from dataclasses import dataclass
import heapq
import math


class SafetyAbort(RuntimeError):
    """Mission cannot be certified under the simulated safety envelope."""


@dataclass(frozen=True)
class RoverConfig:
    cell_m: float = 2.0
    wh_per_m: float = 1.0
    sand_energy_multiplier: float = 2.5
    available_wh: float = 40.0
    battery_reserve_wh: float = 8.0
    risk_penalty_m: float = 6.0
    initial_localization_error_m: float = 0.4
    drift_error_per_m: float = 0.2
    max_localization_error_m: float = 5.0
    relocalized_error_m: float = 0.5
    allow_relocalization: bool = True
    one_way_latency_s: float = 682.0


DEMO_TERRAIN = (
    ".............",
    ".sssssssss...",
    ".#######.....",
    "...######....",
    ".............",
)
DEMO_START = (0, 1)
DEMO_GOAL = (12, 1)


def _validate(terrain: tuple[str, ...], start: tuple[int, int],
              goal: tuple[int, int], c: RoverConfig) -> None:
    if (not terrain or not isinstance(terrain, (tuple, list))
            or any(not isinstance(r, str) for r in terrain)):
        raise ValueError("Terrain must be a nonempty sequence of rows")
    width = len(terrain[0])
    if not width or any(len(row) != width or any(ch not in ".s#" for ch in row)
                        for row in terrain):
        raise ValueError("Terrain must be rectangular with only ., s, #")
    for point in (start, goal):
        if (not isinstance(point, tuple) or len(point) != 2
                or any(type(v) is not int for v in point)):
            raise ValueError("Coordinates must be integer (x, y) pairs")
        x, y = point
        if not (0 <= x < width and 0 <= y < len(terrain)) or terrain[y][x] == "#":
            raise ValueError("Start/goal outside traversable terrain")
    if not isinstance(c, RoverConfig):
        raise ValueError("Invalid rover configuration")
    number_names = (
        "cell_m", "wh_per_m", "sand_energy_multiplier", "available_wh",
        "battery_reserve_wh", "risk_penalty_m", "initial_localization_error_m",
        "drift_error_per_m", "max_localization_error_m", "relocalized_error_m",
        "one_way_latency_s",
    )
    if any(type(getattr(c, k)) not in (float, int)
           or not math.isfinite(getattr(c, k)) for k in number_names):
        raise ValueError("All rover safety coefficients must be finite numbers")
    if (c.cell_m <= 0 or c.wh_per_m <= 0 or c.sand_energy_multiplier < 1
            or c.available_wh <= 0 or c.battery_reserve_wh < 0
            or c.battery_reserve_wh > c.available_wh or c.risk_penalty_m < 0
            or c.initial_localization_error_m < 0 or c.drift_error_per_m < 0
            or c.max_localization_error_m <= 0 or c.relocalized_error_m < 0
            or c.relocalized_error_m > c.max_localization_error_m
            or c.initial_localization_error_m > c.max_localization_error_m
            or c.one_way_latency_s < 0 or type(c.allow_relocalization) is not bool):
        raise ValueError("Invalid rover safety envelope")


def plan_route(terrain: tuple[str, ...] | list[str],
               start: tuple[int, int], goal: tuple[int, int],
               config: RoverConfig = RoverConfig()) -> dict:
    """Plan a 4-neighbor risk-aware path, then check battery and localization.

    Dijkstra finds minimum distance + risk-penalty in this small toy grid.
    The path is **not** claimed globally optimal subject to energy constraints;
    when the selected path fails its safety envelope we fail closed.
    """
    _validate(terrain, start, goal, config)
    queue: list[tuple[float, int, tuple[int, int]]] = [(0., 0, start)]
    distances = {start: 0.}
    predecessor: dict[tuple[int, int], tuple[int, int]] = {}
    visited: set[tuple[int, int]] = set()
    ticket = 0
    while queue:
        cost, _, current = heapq.heappop(queue)
        if current in visited:
            continue
        visited.add(current)
        if current == goal:
            break
        x, y = current
        for xx, yy in ((x + 1, y), (x, y - 1), (x, y + 1), (x - 1, y)):
            if not (0 <= xx < len(terrain[0]) and 0 <= yy < len(terrain)):
                continue
            cell = terrain[yy][xx]
            if cell == "#":
                continue
            nxt = (xx, yy)
            new_cost = cost + config.cell_m + (config.risk_penalty_m if cell == "s" else 0.)
            if new_cost + 1e-12 < distances.get(nxt, math.inf):
                predecessor[nxt] = current
                distances[nxt] = new_cost
                ticket += 1
                heapq.heappush(queue, (new_cost, ticket, nxt))
    if goal not in visited:
        raise SafetyAbort("The simulated science target cannot be reached")
    path = [goal]
    while path[-1] != start:
        path.append(predecessor[path[-1]])
    path.reverse()

    energy_used_wh = 0.
    sand_cells = 0
    uncertainty = config.initial_localization_error_m
    max_seen = uncertainty
    relocalizations = 0
    for x, y in path[1:]:
        is_sand = terrain[y][x] == "s"
        if is_sand:
            sand_cells += 1
        energy_used_wh += config.cell_m * config.wh_per_m * (
            config.sand_energy_multiplier if is_sand else 1.)
        proposed_uncertainty = uncertainty + config.cell_m * config.drift_error_per_m
        if proposed_uncertainty > config.max_localization_error_m:
            if not config.allow_relocalization:
                raise SafetyAbort("Navigation uncertainty exceeds safe threshold")
            relocalizations += 1
            uncertainty = config.relocalized_error_m
            proposed_uncertainty = uncertainty + config.cell_m * config.drift_error_per_m
        if proposed_uncertainty > config.max_localization_error_m:
            raise SafetyAbort("Localization cannot safely support planned step")
        uncertainty = proposed_uncertainty
        max_seen = max(max_seen, uncertainty)
        if energy_used_wh + config.battery_reserve_wh > config.available_wh + 1e-12:
            raise SafetyAbort("Energy budget or protected battery reserve exceeded")
    return {
        "path": path,
        "steps": len(path) - 1,
        "distance_m": round((len(path) - 1) * config.cell_m, 3),
        "sand_cells": sand_cells,
        "energy_used_wh": round(energy_used_wh, 3),
        "battery_remaining_wh": round(config.available_wh - energy_used_wh, 3),
        "battery_reserve_wh": config.battery_reserve_wh,
        "relocalizations": relocalizations,
        "max_observed_localization_error_m": round(max_seen, 3),
        "one_way_latency_s": config.one_way_latency_s,
        "remote_teleoperation_per_step": False,
        "autonomous_navigation": True,
    }


def run_demo() -> dict:
    """Compare pure shortest-path and safer navigation on illustrative terrain."""
    from dataclasses import replace

    baseline = plan_route(DEMO_TERRAIN, DEMO_START, DEMO_GOAL,
                          replace(RoverConfig(), risk_penalty_m=0.,
                                  available_wh=120., battery_reserve_wh=8.))
    safer = plan_route(DEMO_TERRAIN, DEMO_START, DEMO_GOAL)
    assert safer["sand_cells"] < baseline["sand_cells"]
    assert safer["energy_used_wh"] < baseline["energy_used_wh"]
    assert safer["battery_remaining_wh"] >= safer["battery_reserve_wh"]
    return {
        "result": "PASS",
        "data_type": "synthetic_terrain_and_assumptions",
        "mars_life_detected": False,
        "mission_real_rover_control": False,
        "terrain": list(DEMO_TERRAIN),
        "start": DEMO_START, "goal": DEMO_GOAL,
        "baseline_shortest_path": baseline,
        "safety_aware_path": safer,
        "naive_baseline_would_exceed_safe_energy_envelope": (
            baseline["energy_used_wh"] + RoverConfig().battery_reserve_wh
            > RoverConfig().available_wh),
        "model_note": "Educational risk/energy/localization model; not NASA telemetry or flight software.",
        "historical_latency_note": "682 seconds is NASA's 2021 landing light-time reference, not current Earth-Mars delay.",
    }