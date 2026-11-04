"""Validate data for the existing grid simulation; never control hardware."""
from __future__ import annotations


def validate_grid_point(point: object, *, width: int, height: int) -> tuple[int, int]:
    """Reject malformed, boolean, fractional and out-of-bounds coordinates."""
    if (not isinstance(point, (tuple, list)) or len(point) != 2 or
            any(type(value) is not int for value in point)):
        raise ValueError("Grid coordinates must be a pair of integers")
    x, y = point
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError("Grid coordinate outside simulation")
    return x, y


def validate_grid_moves(moves: object) -> list[tuple[int, int]]:
    """Validate the entire command batch before executing any simulated step."""
    if not isinstance(moves, (tuple, list)):
        raise ValueError("Moves must be a list or tuple")
    result = []
    for move in moves:
        if (not isinstance(move, (tuple, list)) or len(move) != 2 or
                any(type(value) is not int for value in move) or
                abs(move[0]) + abs(move[1]) != 1):
            raise ValueError("Each move must be exactly one axis-aligned grid step")
        result.append(tuple(move))
    return result
