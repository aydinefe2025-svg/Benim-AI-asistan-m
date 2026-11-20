"""Protocol-context acceptance for the 3 real original Figshare ET_T23 samples.

The author states Stage-1 calendar TP_k* cell numbers 04--06 only received
initial (ET) and final (AT) RPT. Similar ET voltage is therefore NOT proof
of a copied measurement, shared physical cell, or ML ground-truth label.

Never persist raw source CSV. This module consumes the source-verified
metadata-only output of figshare_phase_guard and records conservative results.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import sys

PAPER_DOI = "10.1038/s41597-024-03859-z"
PAPER_URL = "https://www.nature.com/articles/s41597-024-03859-z"
SOURCE_SCHEMA = "cano.battery.figshare279.original-three-phase-current-gate.v1"
EXPECTED = {
    47627092: ("TP_k01_05_01_ET_T23.csv", "d38599b1af228b1ea96c0e2ea242709dad8bfd507542ae0df08243e2ed6dae4e"),
    47627089: ("TP_k01_06_01_ET_T23.csv", "dea9bff5209298aa8bb0ab8fcfe190e40bc83aa4d5e30afc6e7879fe16d9e512"),
    47639005: ("TP_k01_04_01_ET_T23.csv", "5605f1452700e298242aa7570230597f2f8513e3a6229ca5025aa9bf543651da"),
}
MAX_RECEIPT_BYTES = 100_000
NEAR_AGREEMENT_FRACTION = Decimal("0.99")
LOW_COVERAGE_FRACTION = Decimal("0.5")


def _decimal(raw, label: str) -> Decimal:
    if isinstance(raw, bool):
        raise ValueError("REVIEW_REQUIRED: boolean instead of " + label)
    try:
        d = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("REVIEW_REQUIRED: nonnumeric " + label) from None
    if not d.is_finite():
        raise ValueError("REVIEW_REQUIRED: nonfinite " + label)
    return d


def _natural(raw, label: str) -> int:
    if type(raw) is not int or raw < 0:
        raise ValueError("REVIEW_REQUIRED: invalid count " + label)
    return raw


def inspect_source_receipt(receipt: dict) -> dict:
    """Fail closed on untrusted or inconsistent aggregate evidence."""
    if not isinstance(receipt, dict) or receipt.get("schema") != SOURCE_SCHEMA:
        raise ValueError("REVIEW_REQUIRED: incorrect original source receipt schema")
    if receipt.get("source_article_id") != 25975315 or not str(
            receipt.get("source_doi", "")).startswith("10.6084/m9.figshare.25975315"):
        raise ValueError("REVIEW_REQUIRED: wrong publisher source")
    for flag in ("field_FPR_FNR_established",
                 "publisher_meta_to_physical_cell_identity_independently_verified",
                 "independently_proven_same_test_conditions",
                 "production_release_allowed"):
        if receipt.get(flag) is not False:
            raise ValueError("REVIEW_REQUIRED: unverified source claim " + flag)
    windows = receipt.get("source_windows")
    if not isinstance(windows, list) or len(windows) != 3:
        raise ValueError("REVIEW_REQUIRED: require exactly three original archives")
    counts = {}
    for w in windows:
        if not isinstance(w, dict):
            raise ValueError("REVIEW_REQUIRED: invalid source window")
        fid = w.get("source_file_id")
        if fid not in EXPECTED or fid in counts:
            raise ValueError("REVIEW_REQUIRED: missing/duplicate archive ID")
        if (w.get("source_csv_name"), w.get("source_archive_sha256")) != EXPECTED[fid]:
            raise ValueError("REVIEW_REQUIRED: original archive/ET sample provenance mismatch")
        count = _natural(w.get("source_window_points"), "source_window_points")
        if count < 1000 or count > 20000:
            raise ValueError("REVIEW_REQUIRED: invalid bounded source window")
        counts[fid] = count
    if set(counts) != set(EXPECTED) or receipt.get("total_source_time_voltage_points") != sum(counts.values()):
        raise ValueError("REVIEW_REQUIRED: source row total mismatch")
    rows = receipt.get("pair_results")
    if not isinstance(rows, list) or len(rows) != 3 or receipt.get("pair_count") != 3:
        raise ValueError("REVIEW_REQUIRED: require all source pairs")
    seen = set()
    comparisons = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("REVIEW_REQUIRED: invalid pair row")
        a, b = row.get("left_source_id"), row.get("right_source_id")
        if a not in counts or b not in counts or a == b:
            raise ValueError("REVIEW_REQUIRED: wrong source pair")
        pair = tuple(sorted((a, b)))
        if pair in seen:
            raise ValueError("REVIEW_REQUIRED: duplicate source pair")
        seen.add(pair)
        if any(row.get(k) is not False for k in (
            "independent_cell_identity_authenticated", "physical_phase_alignment_authenticated",
            "field_FPR_FNR_established", "full_window_comparability_established")):
            raise ValueError("REVIEW_REQUIRED: unsupported physical identity or release claim")
        matched = _natural(row.get("matched_unique_elapsed_time_points"), "time matched")
        same_step = _natural(row.get("same_step_points"), "same step")
        same_regime = _natural(row.get("same_step_and_current_points"), "same current")
        if not 0 <= same_regime <= same_step <= matched <= min(counts[a], counts[b]):
            raise ValueError("REVIEW_REQUIRED: inconsistent source pair counts")
        coverage = _decimal(row.get("source_window_coverage_fraction"), "coverage")
        calculated = Decimal(same_regime) / Decimal(max(counts[a], counts[b]))
        if not 0 <= coverage <= 1 or abs(coverage-calculated) > Decimal("0.00000001"):
            raise ValueError("REVIEW_REQUIRED: source coverage inconsistent")
        near = row.get("near_2mV_voltage_pairs")
        if same_regime >= 1000:
            near = _natural(near, "near voltage")
            if near > same_regime:
                raise ValueError("REVIEW_REQUIRED: impossible near count")
            outliers = _natural(row.get("voltage_deltas_gt_50mV"), "large voltage difference")
            if outliers > same_regime:
                raise ValueError("REVIEW_REQUIRED: impossible voltage outlier count")
            near_rate = Decimal(near) / Decimal(same_regime)
            status = ("HIGH_INITIAL_TEST_NEAR_AGREEMENT_LOW_COVERAGE"
                      if near_rate >= NEAR_AGREEMENT_FRACTION and
                         coverage < LOW_COVERAGE_FRACTION
                      else "NO_STRONG_NEAR_AGREEMENT_IN_BOUNDED_SAMPLE")
            observed_rate = str(near_rate.quantize(Decimal("0.000001")))
        else:
            if near is not None:
                raise ValueError("REVIEW_REQUIRED: reported voltage similarity on insufficient data")
            outliers = None
            status = "INSUFFICIENT_COMMON_REGIME_POINTS"
            observed_rate = None
        comparisons.append({
            "source_file_ids": list(pair),
            "common_regime_observations": same_regime,
            "source_window_coverage_fraction": str(coverage),
            "near_2mV_observations": near,
            "near_fraction_of_common_regime": observed_rate,
            "gt_50mV_outlier_observations": outliers,
            "classification": status,
            "proven_duplicate_measurement": False,
            "physical_independence_proven": False,
            "field_FPR_FNR_established": False,
        })
    if seen != {(47627089, 47627092), (47627089, 47639005), (47627092, 47639005)}:
        raise ValueError("REVIEW_REQUIRED: incomplete original pair set")
    return {
        "schema": "cano.battery.figshare279.k01-initial-protocol-context.v1",
        "source_article": "10.6084/m9.figshare.25975315",
        "author_paper_doi": PAPER_DOI,
        "author_paper_url": PAPER_URL,
        "author_protocol_context": {
            "stage": "Stage_1",
            "aging_type": "calendar_k",
            "test_point": "TP_k01",
            "cell_numbers": ["04", "05", "06"],
            "measurement_type": "INITIAL_ET_T23",
            "calendar_aging_04_06_only_initial_and_final_rpt": True,
            "individual_cell_identity_independently_attested": False,
        },
        "pair_results": sorted(comparisons, key=lambda r:r["source_file_ids"]),
        "source_window_count": 3,
        "physical_duplicate_established": False,
        "field_FPR_FNR_established": False,
        "production_release_allowed": False,
        "decision": "AUTHOR_PROTOCOL_EXPLAINS_PLAUSIBLE_NEAR_AGREEMENT_NOT_COPY_PROOF",
        "next_acceptance": "Confirm whole-cell metadata identity and post-aging comparable windows; do not infer duplicate or false-match rate from initial ET alone",
    }


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) != 2 or args[0] != "--live" and not args[0].endswith(".json"):
            raise ValueError("usage: python -m research.battery_curve_audit.figshare_k01_protocol_context INPUT.json|--live OUTPUT.json")
        dest = Path(args[1])
        if dest.exists() or not dest.parent.is_dir():
            raise ValueError("REVIEW_REQUIRED: destination must not exist")
        if args[0] == "--live":
            from research.battery_curve_audit.figshare_phase_guard import run
            source = run()
            raw = (json.dumps(source, indent=2, sort_keys=True)+"\n").encode("utf-8")
        else:
            raw = Path(args[0]).read_bytes()
        if len(raw) > MAX_RECEIPT_BYTES:
            raise ValueError("REVIEW_REQUIRED: source receipt too large")
        source = json.loads(raw)
        result = inspect_source_receipt(source)
        result["input_receipt_sha256"] = sha256(raw).hexdigest()
        with dest.open("x", encoding="utf-8") as out:
            json.dump(result, out, ensure_ascii=False, sort_keys=True, indent=2)
            out.write("\n")
        print("AUTHOR_PROTOCOL_CONTEXT_ONLY", json.dumps(
            [{"pair":p["source_file_ids"],"label":p["classification"]}
             for p in result["pair_results"]], sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print("REVIEW_REQUIRED:", str(exc)[:200], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
