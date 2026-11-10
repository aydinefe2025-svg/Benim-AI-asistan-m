"""Audit an actual (pinned) NASA PDS Mars 2020 PLACES rover localization table.

Source: NASA PDS Geosciences Mars 2020 PLACES data_localizations/best_tactical.csv.
This script uses only Python's standard library, never sends commands to a rover,
and never labels position-only data as hazards, energy, or biological evidence.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path
import statistics

PINNED_CSV = Path(__file__).resolve().parent / "data" / "mars2020_places_best_tactical_20260730.csv"
SOURCE_URL = (
    "https://pds-geosciences.wustl.edu/m2020/"
    "urn-nasa-pds-mars2020_rover_places/data_localizations/best_tactical.csv"
)
COLUMNS = (
    "frame", "site", "drive", "pose", "landing_x", "landing_y",
    "landing_z", "northing", "easting", "planetocentric_latitude",
    "planetodetic_latitude", "longitude", "elevation", "map_pixel_line",
    "map_pixel_sample", "dem_pixel_line", "dem_pixel_sample", "roll",
    "pitch", "yaw", "quat_s", "quat_v1", "quat_v2", "quat_v3",
    "areoid", "radius", "sclk", "sol",
)
FLOAT_FIELDS = (
    "landing_x", "landing_y", "landing_z", "northing", "easting",
    "planetocentric_latitude", "longitude", "elevation", "roll",
    "pitch", "yaw", "quat_s", "quat_v1", "quat_v2", "quat_v3",
)
MAX_OFFSET_DRIFT_M = 0.003
MAX_QUATERNION_NORM_ERROR = 0.000001


def _float(row: dict[str, str], key: str) -> float:
    try:
        n = float(row[key])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Malformed PDS numeric record") from None
    if not math.isfinite(n):
        raise ValueError("Non-finite PDS position value")
    return n


def _int(row: dict[str, str], key: str) -> int:
    try:
        return int(row[key])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Malformed PDS integer record") from None


def audit_csv_text(csv_text: str) -> dict:
    """Validate source format, coordinate invariants and sparse rover chords.

    The chord sum is NOT mission odometry. Its inputs may skip many real moves;
    rover rotation, local hazard probability and traction are NOT measured here.
    """
    if not isinstance(csv_text, str) or not csv_text:
        raise ValueError("Missing PDS CSV content")
    reader = csv.DictReader(io.StringIO(csv_text, newline=""))
    if reader.fieldnames != list(COLUMNS):
        raise ValueError("PDS column header changed or incomplete")
    total = sites = rover_records = 0
    rover: list[dict] = []
    site_drive_keys: set[tuple[int, int]] = set()

    for raw in reader:
        total += 1
        if None in raw or any(v is None for v in raw.values()):
            raise ValueError("Truncated or oversized PDS CSV row")
        frame = raw["frame"]
        if frame == "SITE":
            sites += 1
            continue
        if frame != "ROVER":
            raise ValueError("Unknown PDS localization frame")
        rover_records += 1
        site, drive = _int(raw, "site"), _int(raw, "drive")
        key = (site, drive)
        if key in site_drive_keys:
            raise ValueError("Duplicate rover site/drive pose")
        site_drive_keys.add(key)
        sol, clock = _int(raw, "sol"), _int(raw, "sclk")
        # PDS uses negative sol and/or clock=0 for un-timed entries.
        if sol < 0 or clock <= 0:
            continue
        data = {name: _float(raw, name) for name in FLOAT_FIELDS}
        if not (-90 <= data["planetocentric_latitude"] <= 90
                and -360 <= data["longitude"] <= 360):
            raise ValueError("Invalid Mars geographic coordinate")
        quat_norm = math.hypot(
            data["quat_s"], data["quat_v1"],
            data["quat_v2"], data["quat_v3"],
        )
        error = abs(quat_norm - 1.0)
        if error > MAX_QUATERNION_NORM_ERROR:
            raise ValueError("Invalid PDS attitude quaternion")
        rover.append({**data, "sol": sol, "sclk": clock,
                      "site": site, "drive": drive, "quat_error": error})

    if len(rover) < 2:
        raise ValueError("At least two timed rover localization fixes required")
    rover.sort(key=lambda x: x["sclk"])
    if len({x["sclk"] for x in rover}) != len(rover):
        raise ValueError("Duplicate spacecraft clock")
    if any(b["sol"] < a["sol"] for a, b in zip(rover, rover[1:])):
        raise ValueError("Mars sol ordering contradicts spacecraft clock")

    reference = (
        rover[0]["northing"] - rover[0]["landing_x"],
        rover[0]["easting"] - rover[0]["landing_y"],
        rover[0]["elevation"] + rover[0]["landing_z"],
    )
    origin_offsets = (
        (
            x["northing"] - x["landing_x"],
            x["easting"] - x["landing_y"],
            x["elevation"] + x["landing_z"],
        )
        for x in rover
    )
    max_residual = max(
        max(abs(value - ref) for value, ref in zip(offset, reference))
        for offset in origin_offsets
    )
    if max_residual > MAX_OFFSET_DRIFT_M:
        raise ValueError("PDS local and projected position frames disagree")

    chords = [
        math.hypot(
            b["northing"] - a["northing"],
            b["easting"] - a["easting"],
        )
        for a, b in zip(rover, rover[1:])
    ]
    gaps = [b["sol"] - a["sol"] for a, b in zip(rover, rover[1:])]
    if any(not math.isfinite(n) for n in chords):
        raise ValueError("Invalid rover traverse chord")
    qerr = max(x["quat_error"] for x in rover)

    return {
        "source_kind": "NASA_PDS_MARS2020_PLACES_BEST_TACTICAL",
        "source_url": SOURCE_URL,
        "source_sha256": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
        "source_columns": len(COLUMNS),
        "total_records": total,
        "source_site_records": sites,
        "source_rover_records": rover_records,
        "excluded_rover_records_without_time": rover_records - len(rover),
        "validated_rover_positions": len(rover),
        "first_sol": rover[0]["sol"],
        "last_sol": rover[-1]["sol"],
        "distinct_martian_sols": len({x["sol"] for x in rover}),
        "chord_segment_count": len(chords),
        "chord_sum_km": round(sum(chords) / 1000, 3),
        "median_observed_chord_m": round(statistics.median(chords), 3),
        "longest_observed_chord_m": round(max(chords), 3),
        "same_sol_segments": sum(gap == 0 for gap in gaps),
        "multi_sol_gaps": sum(gap > 1 for gap in gaps),
        "largest_sol_gap": max(gaps),
        "max_origin_offset_residual_m": round(max_residual, 6),
        "max_quaternion_norm_error": qerr,
        "max_abs_roll_deg": round(max(abs(x["roll"]) for x in rover), 3),
        "max_abs_pitch_deg": round(max(abs(x["pitch"]) for x in rover), 3),
        "coordinate_reference": "landing_xyz_to_PDS_northing_easting_elevation",
        "distance_interpretation":
            "sum_of_straight_line_separations_between_sparse_localizations_not_odometry",
        "rover_telemetry_subset_only": True,
        "terrain_hazard_measured": False,
        "battery_energy_measured": False,
        "life_detected": False,
        "real_terrain_route_safety_validated": False,
    }


def audit_pinned_file(path: Path = PINNED_CSV) -> dict:
    return audit_csv_text(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    print(json.dumps(audit_pinned_file(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
