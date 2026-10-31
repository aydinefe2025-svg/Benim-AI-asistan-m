"""Pure-Python toy digital twins, not a real robot or biological cell system.

Grid robot: bounded deterministic motion, obstacle collision halt.
Cell pattern: Conway's Life binary cellular automaton, not living cells.
No hardware, network, laboratory, or external actions.
"""
from __future__ import annotations


def _check_shape(width: int, height: int) -> None:
    if type(width) is not int or type(height) is not int or width < 1 or height < 1:
        raise ValueError("Grid dimensions must be positive integers")


def _inside(pos: tuple[int, int], width: int, height: int) -> bool:
    return 0 <= pos[0] < width and 0 <= pos[1] < height


def move_grid_robot(
    start: tuple[int, int],
    moves: list[tuple[int, int]],
    *,
    width: int,
    height: int,
    obstacles: set[tuple[int, int]] | None = None,
) -> dict:
    """Apply only adjacent integer movement deltas to a virtual grid robot."""
    _check_shape(width, height)
    blocked = set(obstacles or set())
    if not _inside(start, width, height) or start in blocked:
        raise ValueError("Invalid robot starting location")
    if any(not _inside(p, width, height) for p in blocked):
        raise ValueError("Obstacle outside simulation")
    position = start
    successful_steps = blocked_steps = 0
    for dx, dy in moves:
        if (type(dx) is not int or type(dy) is not int or
                abs(dx) + abs(dy) != 1):
            raise ValueError("Each move must be exactly one axis-aligned grid step")
        candidate = (position[0] + dx, position[1] + dy)
        if not _inside(candidate, width, height) or candidate in blocked:
            blocked_steps += 1
            continue
        position = candidate
        successful_steps += 1
    return {
        "position": position,
        "successful_steps": successful_steps,
        "blocked_steps": blocked_steps,
        "simulation_only": True,
        "physical_robot_controlled": False,
    }


def life_step(
    alive: set[tuple[int, int]], *, width: int, height: int
) -> set[tuple[int, int]]:
    """One bounded Conway Game of Life step (illustrative, non-biological)."""
    _check_shape(width, height)
    if any(not _inside(point, width, height) for point in alive):
        raise ValueError("Cell-pattern coordinate outside grid")
    neighbor_counts: dict[tuple[int, int], int] = {}
    for x, y in alive:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                point = (x + dx, y + dy)
                if _inside(point, width, height):
                    neighbor_counts[point] = neighbor_counts.get(point, 0) + 1
    return {
        point for point, count in neighbor_counts.items()
        if count == 3 or (count == 2 and point in alive)
    }
