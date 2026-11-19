#!/usr/bin/env python3
"""Independent-publisher battery SOC/voltage cross-source screening benchmark.

These 17 real *postprocessed* 51-point discharge SOC curves are NOT time/voltage
measurements. Do not put them into the customer time-based parser or near screen.
The 2 mV aligned-SOC RMSE criterion here is a *separate exploratory benchmark*;
it does not validate the operating characteristics of the time-based near guard.

Positive labels are deterministic CONTROLLED transformations of each real curve,
not 51 independent field-confirmed duplicates. Negatives are 136 comparisons of
17 documented physical cells, correlated pairwise within one publisher/cohort.
No measured FPR/FNR for heterogeneous lab field data or paying customers.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path

SCHEMA = "cano.battery.external-soc-benchmark.v1"
FIXTURE = Path(__file__).parent / "fixtures" / "external_soc_david_2026.json"
THRESHOLD_MV = 2.0


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def parse_record(record: dict) -> tuple:
    required = {"name", "git_blob_sha1", "raw_text"}
    if not isinstance(record, dict) or set(record) != required:
        raise ValueError("REVIEW_REQUIRED: invalid source record")
    name, sha, raw = record["name"], record["git_blob_sha1"], record["raw_text"]
    if (not isinstance(name, str) or not name.startswith("discharge/")
            or not name.endswith(".dat") or len(name) != len("discharge/01.dat")
            or not isinstance(raw, str) or len(raw) > 4096
            or not isinstance(sha, str) or len(sha) != 40):
        raise ValueError("REVIEW_REQUIRED: invalid source path, size or blob SHA")
    if git_blob_sha1(raw.encode("utf-8")) != sha:
        raise ValueError("REVIEW_REQUIRED: external raw-source Git blob mismatch")
    lines = raw.splitlines()
    if len(lines) != 51:
        raise ValueError("REVIEW_REQUIRED: expected 51 SOC points")
    values = []
    for i, line in enumerate(lines):
        fields = line.split()
        if len(fields) != 2:
            raise ValueError("REVIEW_REQUIRED: malformed SOC row")
        try:
            x, voltage = map(Decimal, fields)
        except InvalidOperation as exc:
            raise ValueError("REVIEW_REQUIRED: malformed Decimal reading") from exc
        if (not x.is_finite() or not voltage.is_finite()
                or x != Decimal(1) - Decimal("0.02") * i
                or not Decimal("2.0") < voltage < Decimal("5.0")):
            raise ValueError("REVIEW_REQUIRED: invalid aligned SOC/voltage reading")
        values.append((x, voltage))
    return name, tuple(values)


def load_fixture(path: Path = FIXTURE) -> list[tuple[str, tuple]]:
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    if (fixture.get("schema") != "cano.battery.external-soc-fixture.v1"
            or fixture.get("x_axis") != "state_of_charge_fraction"
            or fixture.get("x_axis_is_time") is not False
            or fixture.get("y_axis") != "voltage_V"
            or fixture.get("source_license") != "BSD-2-Clause"):
        raise ValueError("REVIEW_REQUIRED: source axis/provenance contract mismatch")
    records = fixture.get("records")
    if not isinstance(records, list) or len(records) != 17:
        raise ValueError("REVIEW_REQUIRED: expected 17 original cells")
    parsed = [parse_record(r) for r in records]
    if len({name for name, _ in parsed}) != len(parsed):
        raise ValueError("REVIEW_REQUIRED: duplicate source cells")
    expected = [f"discharge/{i:02d}.dat" for i in range(1, 18)]
    if sorted(name for name, _ in parsed) != expected:
        raise ValueError("REVIEW_REQUIRED: source cell list changed")
    return sorted(parsed)


def rmse_mv(left: tuple, right: tuple) -> float:
    if len(left) != 51 or len(right) != 51:
        raise ValueError("REVIEW_REQUIRED: incompatible SOC trace lengths")
    if any(a[0] != b[0] for a, b in zip(left, right)):
        raise ValueError("REVIEW_REQUIRED: SOC coordinates must match; never warp axes")
    return math.sqrt(sum(float(a[1] - b[1]) ** 2 for a, b in zip(left, right))
                     / 51) * 1000


def same_numeric_curve(left: tuple, right: tuple) -> bool:
    return left == right


def screen_pair(left: tuple, right: tuple, threshold_mv: float = THRESHOLD_MV) -> bool:
    if not 0.0 < threshold_mv <= 2.0:
        raise ValueError("REVIEW_REQUIRED: fixed conservative benchmark threshold exceeded")
    return same_numeric_curve(left, right) or rmse_mv(left, right) <= threshold_mv


def test_controls(curve: tuple) -> list[tuple[str, tuple]]:
    """Three known relations to the SAME original measured source, not field labels."""
    exact = tuple(curve)
    # An equivalent decimal *serialization* is not a separately measured cell.
    alias = tuple((Decimal(str(x) + "0"), Decimal(str(v) + "0")) for x, v in curve)
    # Deliberate +1 mV offset represents an injected instrument-scale perturbation.
    shifted = tuple((x, v + Decimal("0.001")) for x, v in curve)
    return [("exact", exact), ("decimal_alias", alias), ("injected_plus_1mV", shifted)]


def benchmark(fixture: Path = FIXTURE) -> dict:
    cells = load_fixture(fixture)
    distinct_pairs = []
    for i, (name_a, curve_a) in enumerate(cells):
        for name_b, curve_b in cells[i + 1:]:
            distance = rmse_mv(curve_a, curve_b)
            distinct_pairs.append((distance, name_a, name_b,
                                   screen_pair(curve_a, curve_b)))
    positives = []
    for name, curve in cells:
        for method, control in test_controls(curve):
            positives.append((name, method, screen_pair(curve, control)))
    false_alerts = sum(flagged for _, _, _, flagged in distinct_pairs)
    caught_controls = sum(caught for _, _, caught in positives)
    nearest = min(distinct_pairs)
    result = {
        "schema": SCHEMA,
        "source": "https://github.com/David-EIPI/lithium-battery-soc",
        "license": "BSD-2-Clause; notice retained in fixture directory",
        "axis_contract": {"x": "SOC_fraction_descending_not_time", "y": "voltage_V",
                          "compatible_with_customer_time_screen": False},
        "original_cells": len(cells),
        "real_measured_soc_voltage_pairs": sum(len(curve) for _, curve in cells),
        "distinct_physical_cell_comparisons": len(distinct_pairs),
        "observed_alerts_across_distinct_cells": false_alerts,
        "minimum_distinct_pair_rmse_mV": round(nearest[0], 6),
        "nearest_pair": [nearest[1], nearest[2]],
        "controlled_related_pairs": len(positives),
        "detected_controlled_related_pairs": caught_controls,
        "controlled_misses": len(positives) - caught_controls,
        "threshold": {"metric": "aligned_SOC_voltage_RMSE_mV",
                      "value_mV": THRESHOLD_MV,
                      "not_same_as_time_near_screen": True},
        "release_decision": ("CROSS_PUBLISHER_SOC_SCREEN_PASS"
                             if false_alerts == 0 and caught_controls == len(positives)
                             else "REVIEW_REQUIRED"),
        "limits": [
            "External source has 17 cells from one independent publisher, not multiple labs.",
            "Each 51-point curve was postprocessed to SOC grid; it is NOT raw time-series telemetry.",
            "136 comparisons share 17 cells, so pairwise outcomes are correlated; do not infer an independent-sample confidence interval.",
            "All 51 positive controls are derived exact/decimal/+1 mV transformations, not real independently labeled copies.",
            "This 2 mV SOC-aligned RMSE screen is not the time-aligned, endpoint-aware customer near-duplicate detector.",
            "0 observed alerts is not a validated population false-positive rate or proof of independence.",
            "No real customer consented field data, multiple labs, SOH performance, certification, or revenue."
        ],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--output", type=Path, help="Write inspectable aggregate results")
    args = parser.parse_args()
    result = benchmark(args.fixture)
    if args.output:
        if args.output.exists():
            raise ValueError("REVIEW_REQUIRED: refuse to overwrite existing report")
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result["release_decision"] != "CROSS_PUBLISHER_SOC_SCREEN_PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
