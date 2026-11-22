"""Four additional distinct original Bayreuth battery cells: original-source
provenance and per-step current-time integration, NOT impact testing.

Source: Roe/Plank/Danzer/Ramasubramanian, Zenodo record 15755725,
DOI 10.5281/zenodo.15755725 (CC BY 4.0). This changes measured-source
coverage from five to nine IF all source files pass in live CI. No unknown
physical measurement is estimated from another cell.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

from research.battery_curve_audit import bayreuth_two_cell_independent_integral as core
from research.battery_curve_audit import bayreuth_additional_three_originals as previous

RECORD_API = "https://zenodo.org/api/records/15755725"
# These official publisher MD5 pins are recorded in the public 2025 record,
# separate from the runtime metadata. Byte sizes are verified against the
# exact record manifest, and the full ZIP CRC/structure is checked by core.
NEW_ORIGINAL_MD5 = {
    "F0003": "4f3c7587d697b2b863b36a13a7ab8f25",
    "F0031": "85a2f4c569988219a771faae19624068",
    "F0136": "152d6ef9484c9546ad1a44a9aecb3408",
    "F0150": "e0f7fd8ab3a915deb584e1f486557a2e",
}
PRIOR_SOURCE_IDS = frozenset(core.SOURCE_FILES) | frozenset(previous.ADDITIONAL_SOURCE_FILES)


def verify_publisher_manifest(record: dict) -> dict[str, dict]:
    if str(record.get("id")) != core.RECORD_ID or record.get("doi") != core.RECORD_DOI:
        raise ValueError("different Zenodo record identity or DOI")
    files = record.get("files")
    if not isinstance(files, list):
        raise ValueError("official source file manifest missing")
    by_key = {}
    for f in files:
        key = f.get("key")
        if key in by_key:
            raise ValueError("duplicate official source filename")
        by_key[key] = f
    if len([key for key in by_key if isinstance(key, str) and
            key.startswith("F") and key.endswith(".zip")]) != 48:
        raise ValueError("expected 48 distinct original ZIP source files")
    if set(NEW_ORIGINAL_MD5) & PRIOR_SOURCE_IDS:
        raise ValueError("new source collides with five already verified source cells")
    specs = {}
    for cell, official_pin in NEW_ORIGINAL_MD5.items():
        item = by_key.get(cell + ".zip")
        if not item:
            raise ValueError("missing requested genuine publisher cell " + cell)
        digest = item.get("checksum", "").lower()
        size = item.get("size")
        if digest != "md5:" + official_pin or not isinstance(size, int) or not (1_000_000 < size < 30_000_000):
            raise ValueError("official source checksum or size mismatch: " + cell)
        specs[cell] = {"size": size, "md5": official_pin}
    return specs


def fetch_manifest() -> tuple[dict[str, dict], str]:
    req = urllib.request.Request(RECORD_API, headers={"User-Agent": "CANO-original-source-audit/2.0"})
    with urllib.request.urlopen(req, timeout=50) as response:
        raw = response.read(2_000_000 + 1)
    if len(raw) > 2_000_000:
        raise ValueError("unreasonably large official metadata response")
    record = json.loads(raw)
    return verify_publisher_manifest(record), hashlib.sha256(raw).hexdigest()


def fetch_new_original(cell: str, spec: dict) -> bytes:
    if cell not in NEW_ORIGINAL_MD5 or spec.get("md5") != NEW_ORIGINAL_MD5[cell]:
        raise ValueError("not an approved new original source")
    # Reuse exactly the previously verified size, MD5, ZIP CRC, member-path,
    # and uncompressed-size guards in the existing main-branch implementation.
    with previous.registered_original(cell, spec):
        return core.fetch_publisher(cell)


def analyze_four(originals: dict[str, bytes], specs: dict[str, dict], manifest_sha: str) -> dict:
    if set(originals) != set(NEW_ORIGINAL_MD5) or set(specs) != set(NEW_ORIGINAL_MD5):
        raise ValueError("all four distinct originals are required")
    results = {cell: previous.analyze_original_blob(cell, originals[cell], specs[cell])
               for cell in NEW_ORIGINAL_MD5}
    comparable = {phase: sum(bool(r["paired_measurement"][phase].get(
        "comparable_homologous_source_step")) for r in results.values())
                  for phase in ("discharge", "charge")}
    return {
        "goal_key": "bayreuth-20261123-four-more-distinct-publisher-original-cells",
        "source_doi": core.RECORD_DOI,
        "source_license": "CC BY 4.0",
        "official_manifest_sha256": manifest_sha,
        "previous_verified_independent_source_ids": sorted(PRIOR_SOURCE_IDS),
        "four_new_independent_source_ids": sorted(results),
        "new_independent_source_cell_count": len(results),
        "distinct_original_cell_sources_after_past_and_this_audit": len(PRIOR_SOURCE_IDS) + len(results),
        "new_checkup_numeric_rows": sum(stage["rows_parsed"] for result in results.values()
                                        for stage in result["original_checkups"].values()),
        "matched_cell_counts": comparable,
        "cells": results,
        "not_a_random_sample_of_24_aging_conditions": True,
        "not_an_impact_resistance_measurement": True,
        "not_a_calibrated_absolute_capacity_loss": True,
        "does_not_generalize_to_all_48_cells": True,
        "current_meter_not_independent_of_native_Ah_step": True,
        "original_test_program_and_sensor_calibration_unverified": True,
        "no_stroebl_physical_replication": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    specs, manifest_sha = fetch_manifest()
    originals = {cell: fetch_new_original(cell, specs[cell]) for cell in NEW_ORIGINAL_MD5}
    result = analyze_four(originals, specs, manifest_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False,
                                      allow_nan=False) + "\n", encoding="utf-8")
    for cell in result["four_new_independent_source_ids"]:
        x = result["cells"][cell]
        print("PUBLISHER_ZIP_MD5_CRC", cell, x["source_bytes"], x["source_official_md5"])
        for phase in ("discharge", "charge"):
            p = x["paired_measurement"][phase]
            print("MATCHED_SOURCE_STEP", cell, phase, bool(p.get("comparable_homologous_source_step")),
                  p.get("source_step_delta_mAh"), p.get("independently_integrated_trapezoid_delta_mAh"))
    print("NINE_SOURCE_IDS_NOT_NINE_CERTIFIED_CAPACITY_LOSSES",
          result["distinct_original_cell_sources_after_past_and_this_audit"])


if __name__ == "__main__":
    main()
