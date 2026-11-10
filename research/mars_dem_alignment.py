"""Offline reproducibility and integrity checks for real PDS Mars 2020 DEM samples.

The 577 3x3 windows were read by HTTP 206 byte ranges from the official NASA
PDS orbital DEM, not reconstructed from the rover elevations. This module
reads pinned public evidence files ONLY; it performs no network calls and
cannot drive real equipment. DEM XML specifies DN, not a verified vertical
unit; a metres-per-DN assumption is explicit for derived gradient *angles*.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "research/data/mars2020_places_best_tactical_20260730.csv"
LABEL = ROOT / "research/data/mars2020_orbital_dem_label_20260729.xml"
PATCHES = ROOT / "research/data/mars2020_dem_3x3_rover_samples_20260729.json"
CHECK = ROOT / "research_reports/mars/2026-11-10_dem_independent_metrics.json"


def _lname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _direct(node: ET.Element, tag: str) -> str:
    found = [x for x in node if _lname(x.tag) == tag]
    if len(found) != 1 or found[0].text is None:
        raise ValueError("Invalid DEM XML field")
    return found[0].text.strip()


def _tag_value(node: ET.Element, tag: str) -> float:
    values = [x.text for x in node.iter() if _lname(x.tag) == tag]
    if len(values) != 1 or values[0] is None:
        raise ValueError("Missing or duplicate DEM geospatial coordinate")
    return float(values[0])


def _pinned_original_bytes(data: bytes, expected_sha256: str) -> bytes:
    """Only allow exact source bytes or Git's CRLF checkout conversion.

    Reject all other byte alterations. The PDS sources were archived with LF,
    but Git on Windows may expand LF to CRLF during checkout.
    """
    for candidate in (data, data.replace(b"\\r\\n", b"\\n")):
        if hashlib.sha256(candidate).hexdigest() == expected_sha256:
            return candidate
    raise ValueError("NASA PDS pinned source SHA-256 mismatch")


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Invalid " + field)
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite " + field)
    return number


def _stat(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p))]


def audit_bundle(csv_bytes: bytes, label_bytes: bytes,
                 sampled: dict, independent: dict) -> dict:
    """Validate source coordinate frame, data provenance and all 577 windows.

    This is a consistency audit, NOT a claim that every byte of the 324 MB DEM
    was downloaded, nor that the local 3x3 gradient identifies a safe route.
    """
    if not isinstance(sampled, dict) or not isinstance(independent, dict):
        raise ValueError("Missing sampled NASA evidence")
    provenance = sampled.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("Missing provenance")
    csv_bytes = _pinned_original_bytes(
        csv_bytes, provenance.get("localizations_sha256", ""))
    label_bytes = _pinned_original_bytes(
        label_bytes, provenance.get("dem_label_sha256", ""))

    root = ET.fromstring(label_bytes)
    arrays = [x for x in root.iter() if _lname(x.tag) == "Array_2D_Image"]
    if len(arrays) != 1:
        raise ValueError("Expected one DEM raster array")
    array = arrays[0]
    offset = int(_direct(array, "offset"))
    axes = [x for x in array if _lname(x.tag) == "Axis_Array"]
    dimensions = {_direct(x, "axis_name"): int(_direct(x, "elements")) for x in axes}
    dtypes = [x for x in array if _lname(x.tag) == "Element_Array"]
    if (len(axes) != 2 or len(dtypes) != 1 or
            _direct(dtypes[0], "data_type") != "IEEE754MSBSingle" or
            _direct(dtypes[0], "unit") != "DN"):
        raise ValueError("Unexpected DEM sample encoding/unit")
    nline, nsample = dimensions.get("Line"), dimensions.get("Sample")
    if (nline, nsample, offset) != (5480, 14800, 118400):
        raise ValueError("Unexpected DEM dimensions/offset")
    size = offset + nline * nsample * 4
    if (size != provenance.get("dem_binary_size_verified_via_http_206")
            or size != 324534400):
        raise ValueError("DEM byte-range header contradicts raster label")

    north_max = _tag_value(root, "x_axis_maximum")
    east_min = _tag_value(root, "y_axis_minimum")
    if abs(north_max - 1097070) > 0.001 or abs(east_min - 4340890) > 0.001:
        raise ValueError("DEM projected reference origin changed")
    if provenance.get("not_a_full_DEM_copy") is not True:
        raise ValueError("Full DEM download incorrectly claimed")
    if (provenance.get("no_real_rover_control") is not True
            or provenance.get("not_a_terrain_hazard_safety_certification") is not True):
        raise ValueError("Unsupported safety or rover-control claim")

    text = csv_bytes.decode("ascii")
    rover = [row for row in csv.DictReader(io.StringIO(text))
             if row["frame"] == "ROVER" and int(row["sol"]) >= 0
             and int(row["sclk"]) > 0]
    rover.sort(key=lambda row: int(row["sclk"]))
    observations = sampled.get("observations")
    fields = sampled.get("fields")
    if not isinstance(observations, list) or len(rover) != len(observations) or len(rover) != 577:
        raise ValueError("Incomplete PDS rover patches")
    if not isinstance(fields, list) or len(fields) != 8:
        raise ValueError("Unexpected DEM patch schema")
    checksum = hashlib.sha256(json.dumps(
        observations, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    if checksum != sampled.get("observations_sha256"):
        raise ValueError("DEM patch samples changed after authentication")
    if independent.get("source_data_sha256") != checksum:
        raise ValueError("Independent check refers to different patch samples")
    if independent.get("source_label_sha256") != provenance["dem_label_sha256"]:
        raise ValueError("Independent check refers to different DEM label")

    seen = set()
    ranges = set()
    residuals, slopes = [], []
    outliers = []
    for original, item in zip(rover, observations):
        if not isinstance(item, list) or len(item) != 8:
            raise ValueError("Malformed PDS rover patch")
        site, drive, sol, sclk, line, sample, elevation, window = item
        identifiers = [int(original[key]) for key in ("site", "drive", "sol", "sclk")]
        if [site, drive, sol, sclk] != identifiers:
            raise ValueError("DEM patch paired to wrong rover position")
        key = (site, drive)
        if key in seen:
            raise ValueError("Duplicate site/drive in DEM patch")
        seen.add(key)
        if not isinstance(line, int) or not isinstance(sample, int):
            raise ValueError("Noninteger DEM pixel index")
        if line != round(float(original["dem_pixel_line"])) or sample != round(
                float(original["dem_pixel_sample"])):
            raise ValueError("DEM patch pixel does not match PDS rover locator")
        if not (1 <= line < nline - 1 and 1 <= sample < nsample - 1):
            raise ValueError("DEM patch outside 3x3 image coverage")
        if (abs((north_max - float(original["northing"])) - float(
                original["dem_pixel_line"])) > 0.02
                or abs((float(original["easting"]) - east_min) - float(
                    original["dem_pixel_sample"])) > 0.02):
            raise ValueError("PDS rover location contradicts DEM map projection")
        elev = _finite(elevation, "reference elevation")
        if abs(elev - float(original["elevation"])) > 1e-6:
            raise ValueError("DEM reference elevation was altered")
        if not isinstance(window, list) or len(window) != 3:
            raise ValueError("Incomplete DEM patch rows")
        vals = []
        for row_num, triple in enumerate(window):
            if not isinstance(triple, list) or len(triple) != 3:
                raise ValueError("Incomplete DEM row")
            parsed = [_finite(pixel, "DEM sample") for pixel in triple]
            if any(not -5000 < value < 5000 for value in parsed):
                raise ValueError("No-data/out-of-range DEM pixel")
            vals.append(parsed)
            ranges.add(offset + ((line + row_num - 1) * nsample + sample - 1) * 4)

        diff = vals[1][1] - elev
        east_gradient = (vals[1][2] - vals[1][0]) / 2
        north_gradient = (vals[0][1] - vals[2][1]) / 2
        degrees = math.degrees(math.atan(math.hypot(east_gradient, north_gradient)))
        residuals.append(diff)
        slopes.append(degrees)
        if abs(diff) > 1:
            outliers.append({"site": site, "drive": drive, "sol": sol,
                             "delta_m": round(diff, 6),
                             "slope_deg": round(degrees, 6),
                             "northing_dem_line": line,
                             "easting_dem_sample": sample})

    absvals = [abs(x) for x in residuals]
    metrics = {
        "valid_positions": len(rover),
        "unique_three_pixel_row_ranges": len(ranges),
        "dem_3x3_pixel_values": len(rover) * 9,
        "mean_absolute_height_difference_m": round(sum(absvals) / len(absvals), 6),
        "median_absolute_height_difference_m": round(statistics.median(absvals), 6),
        "p95_absolute_height_difference_m": round(_stat(absvals, .95), 6),
        "max_absolute_height_difference_m": round(max(absvals), 6),
        "median_local_3x3_gradient_degrees": round(statistics.median(slopes), 6),
        "p90_local_3x3_gradient_degrees": round(_stat(slopes, .9), 6),
        "p95_local_3x3_gradient_degrees": round(_stat(slopes, .95), 6),
        "max_local_3x3_gradient_degrees": round(max(slopes), 6),
        "centers_over_1m_discrepancy": len(outliers),
        "local_3x3_gradients_over_15_degrees": sum(x > 15 for x in slopes),
    }
    expected = sampled.get("summary")
    if not isinstance(expected, dict):
        raise ValueError("DEM acquisition summary missing")
    for key, value in metrics.items():
        if expected.get(key) != value:
            raise ValueError("DEM acquisition metrics do not reproduce")
    check_fields = {
        "mean_abs_m": "mean_absolute_height_difference_m",
        "median_abs_m": "median_absolute_height_difference_m",
        "p95_abs_m": "p95_absolute_height_difference_m",
        "max_abs_m": "max_absolute_height_difference_m",
        "median_slope_deg": "median_local_3x3_gradient_degrees",
        "p90_slope_deg": "p90_local_3x3_gradient_degrees",
        "p95_slope_deg": "p95_local_3x3_gradient_degrees",
        "max_slope_deg": "max_local_3x3_gradient_degrees",
    }
    for key, metric in check_fields.items():
        if independent.get(key) != metrics[metric]:
            raise ValueError("Independent DEM metric did not reproduce: " + key)
    if (independent.get("outliers_abs_height_gt_1m") != outliers or
            independent.get("slope_gt_15_deg") != metrics[
                "local_3x3_gradients_over_15_degrees"]):
        raise ValueError("DEM outlier positions or gradient count changed")
    if independent.get("original_rover_positions") != 577:
        raise ValueError("Independent audit did not cover full rover set")
    return {
        "status": "offline_verified_real_pds_3x3_byte_range_samples",
        "sample_count": len(rover), "metrics": metrics,
        "outliers_gt_1m": outliers,
        "source_csv_sha256": provenance["localizations_sha256"],
        "source_dem_label_sha256": provenance["dem_label_sha256"],
        "full_binary_dem_verified": False,
        "vertical_unit_verified": False,
        "real_terrain_route_certified": False,
        "mars_life_found": False,
    }


def audit_pinned() -> dict:
    return audit_bundle(
        CSV.read_bytes(), LABEL.read_bytes(),
        json.loads(PATCHES.read_text(encoding="utf-8")),
        json.loads(CHECK.read_text(encoding="utf-8")),
    )


if __name__ == "__main__":
    print(json.dumps(audit_pinned(), indent=2, ensure_ascii=False, sort_keys=True))
