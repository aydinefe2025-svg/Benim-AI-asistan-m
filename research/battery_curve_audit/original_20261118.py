#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Original battery curves: provenance-pinned, no-cost CSV lineage audit.

Original publisher: BulyK47 / POLITEHNICA Bucharest, 2026
https://github.com/BulyK47/battery-datasets
DOI: https://doi.org/10.21227/cm0f-jg66
Dataset licence: CC BY 4.0, attribution required.

The 20 original published CSVs cover 10 cells, 30 charge curves and
30 discharge curves. Prevents silent train/test duplication between
nominally different cell IDs. Also handles *trailing omitted* CSV columns
safely: charge exports have 2, 4, or 6 fields, not always 6.

The 10 original discharge CSVs were independently analyzed via the
read-only GitHub connector in JavaScript (not by this offline Python run).
At 2026-11-18, 30 traces contain exactly one 3-cell duplicate group:
APR1/DC1 = APR2/DC1 = APR3/DC1 across 3764 timestamp-voltage pairs.
Another audit of 10 charge files found 6608 short/trailing-trimmed rows,
0 time/voltage-unpaired rows, and no charge-vs-charge identical traces.
This tool is designed to reproduce the *full data* check on any
Internet-connected Python 3 computer; offline fixtures are not real data.

Usage:
  python CANO_BATARYA_ORJINAL_60_EGRI_KOPYA_DENETIMI_20261118.py --download
  python CANO_BATARYA_ORJINAL_60_EGRI_KOPYA_DENETIMI_20261118.py --data-dir ./battery-data
  python CANO_BATARYA_ORJINAL_60_EGRI_KOPYA_DENETIMI_20261118.py --self-test
"""
import argparse
import csv
import hashlib
import io
import json
import math
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO = "BulyK47/battery-datasets"
ROOT = "charge-discharge-voltage-curves/csv/charge_discharge_voltage_curves__"
SUFFIXES = [
    "apreh171000701957", "apreh171000707901", "apreh171000711199",
    "apreh171000711443", "apreh171000714657",
    "bse001", "bse002", "bse003", "bse004", "bse005",
]
PIN = {
    "dchg": [
        "3dd10b5624fe2a7fdb409cfbb8d878d8edb3b291",
        "8ede443892f69af904f1c3a313c62adb52f61d24",
        "777c09f97fa60ee87a26f75d6e8c85ed11072b02",
        "ac2ccd349969314c37e9a2ba2eb231dfd0fbf4e4",
        "87e0d16c3ad871f90f9340664b24711fdd7fec45",
        "44ed376035647639628f69c277067fe7ccb11e1f",
        "f77ebf2f3a18fea2bd34ba52bd0f04d198f7d5f4",
        "8383708ab00ff65c62d00afa1f232164d2b2160c",
        "990a8e149ea7f1c6f9cf4f9b9dc3b2e823edc1ae",
        "363f554e36bc85ebcb775f1739f54733df2f39c6",
    ],
    "chg": [
        "83c642c1372fb77f0d97f0bfe4aeba7fa823e31b",
        "133698af11125ed2845ca86ce6844ab642f62fce",
        "dfd7f120b47b0673664d271890a011aed3f46468",
        "ffbef48e06195cedc237b4b2c78fb8e96259c6bd",
        "766646c119b717424b486586662b41393e79a8ac",
        "51358869bbd6a34b0c27a78c7143cf08cd310fae",
        "51d742be91191680bd6f6ba91bda80e578d23c85",
        "c39e4c44b84816bc89a4f4441e50c485c050546d",
        "50a6ba720f5c6136ff3d5ed838f5da90a454dd42",
        "ba24764cd99391f69cdc77aa1dc32fd9c81b4737",
    ],
}
GOAL = "battery-20261118-30-discharge-exact-cross-cell-duplicates"


def git_blob_sha(content: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()


def fetch_original(directory: Path, kind: str, idx: int, *, download: bool) -> bytes:
    relative = f"{ROOT}{kind}_{SUFFIXES[idx]}.csv"
    expected = PIN[kind][idx]
    dest = directory / relative
    if download:
        url = f"https://raw.githubusercontent.com/{REPO}/main/{relative}"
        with urllib.request.urlopen(url, timeout=90) as response:
            raw = response.read(6_000_000)
        if git_blob_sha(raw) != expected:
            raise ValueError(f"REJECT: Git blob mismatch for {relative}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    else:
        raw = dest.read_bytes()
    got = git_blob_sha(raw)
    if got != expected:
        raise ValueError(f"REJECT: original CSV identity {relative}: {got} != {expected}")
    return raw


def parse_six_columns(raw: bytes, *, kind: str, file_name: str):
    """Read independently sized timestamp-voltage pairs, preserving strings.

    Data with 2 or 4 fields is accepted only as missing trailing whole
    timestamp-voltage pairs. Never invent values, and never fill missing
    voltage with zero.
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as e:
        raise ValueError(f"REJECT: text encoding for {file_name}") from e
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader)
    if len(header) != 6 or any("Timestamp" not in header[j] for j in (0, 2, 4)):
        raise ValueError(f"REJECT: six-column timestamp/voltage schema for {file_name}")
    curves = [[], [], []]
    widths = defaultdict(int)
    last_times = [None, None, None]
    rows = 0
    for number, row in enumerate(reader, start=2):
        if not row:
            continue
        rows += 1
        if len(row) not in (2, 4, 6):
            raise ValueError(f"REJECT: invalid field count {len(row)} at {file_name}:{number}")
        widths[len(row)] += 1
        if kind == "dchg" and len(row) != 6:
            raise ValueError(f"REJECT: unexpected discharge short row at {file_name}:{number}")
        row += [""] * (6 - len(row))
        for col in range(3):
            t, v = row[2*col:2*col+2]
            if not t and not v:
                continue
            if not t or not v:
                raise ValueError(f"REJECT: incomplete time-voltage pair {file_name}:{number}")
            try:
                tf, vf = float(t), float(v)
            except ValueError as e:
                raise ValueError(f"REJECT: nonnumeric pair {file_name}:{number}") from e
            if not math.isfinite(tf) or not math.isfinite(vf) or vf < 0:
                raise ValueError(f"REJECT: invalid physical value {file_name}:{number}")
            if last_times[col] is not None and tf <= last_times[col]:
                raise ValueError(f"REJECT: nonincreasing time {file_name}:{number}")
            last_times[col] = tf
            # Exact published source text, not float-rounded equality.
            curves[col].append((t, v))
    if any(not x for x in curves):
        raise ValueError(f"REJECT: missing entire curve in {file_name}")
    return {"rows": rows, "width_counts": dict(widths), "traces": curves,
            "voltage_headers": header[1::2]}


def make_evidence(source_data):
    all_curves = []
    widths = defaultdict(int)
    total_rows = 0
    sample_pairs = 0
    for (kind, suffix, pin_sha), raw in source_data:
        parsed = parse_six_columns(raw, kind=kind, file_name=f"{kind}_{suffix}")
        total_rows += parsed["rows"]
        for w, n in parsed["width_counts"].items():
            widths[f"{kind}_{w}"] += n
        for i, pairs in enumerate(parsed["traces"], start=1):
            sample_pairs += len(pairs)
            canonical = "".join(t + "\t" + v + "\n" for t, v in pairs)
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            all_curves.append({"cell": suffix, "mode": kind,
                "run": i, "source_git_blob": pin_sha,
                "n": len(pairs), "time_start": pairs[0][0],
                "time_last": pairs[-1][0], "trace_sha256": digest})
    digests = defaultdict(list)
    for c in all_curves:
        digests[c["trace_sha256"]].append(c)
    duplicates = [v for v in digests.values() if len(v) > 1]
    return {
        "goal_key": GOAL,
        "publisher": f"https://github.com/{REPO}",
        "dataset_doi": "10.21227/cm0f-jg66",
        "license": "CC BY 4.0; preserve attribution",
        "analysis_scope": "Original 10-cell, 20-file, 60-trace dataset, no live data",
        "source_files": len(source_data),
        "csv_data_rows": total_rows,
        "measured_time_voltage_pairs": sample_pairs,
        "trace_count": len(all_curves),
        "unique_curve_count": len(digests),
        "width_counts": dict(widths),
        "duplicate_groups": duplicates,
        "all_curve_identity": all_curves,
        "product_release_gate": "Group identical traces into the SAME train/validation/test partition; otherwise reject",
        "not_verified": ["cause of duplication", "customer field performance", "battery SOH", "commercial conversion", "payment or revenue"],
    }


def self_test():
    # Parser smoke check only. Deliberately not claimed as a real-data experiment.
    good = b"Timestamp_1 [h],DC1 [V],Timestamp_2 [h],DC2 [V],Timestamp_3 [h],DC3 [V]\n0,3.3,0,3.2,0,3.1\n0.01,3.2,0.01,3.1,0.01,3.0\n0.02,3.1\n"
    o = parse_six_columns(good, kind="chg", file_name="parser_fixture")
    assert [len(t) for t in o["traces"]] == [3, 2, 2]
    assert o["width_counts"] == {6: 2, 2: 1}
    try:
        parse_six_columns(good.replace(b"0.02,3.1", b"0.02,"), kind="chg", file_name="negative_fixture")
        raise AssertionError("should reject missing voltage")
    except ValueError:
        pass
    print("PASS: only parser fixtures; original 20-file experiment not run in --self-test")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=Path("battery-datasets"))
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--output-json", type=Path, default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        self_test(); return
    sources = []
    for kind in ("dchg", "chg"):
        for i, suffix in enumerate(SUFFIXES):
            raw = fetch_original(a.data_dir, kind, i, download=a.download)
            sources.append(((kind, suffix, PIN[kind][i]), raw))
    o = make_evidence(sources)
    print(json.dumps({k: v for k, v in o.items() if k != "all_curve_identity"}, ensure_ascii=False, indent=2))
    if a.output_json:
        a.output_json.write_text(json.dumps(o, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    expected = [
        {"apreh171000701957", "apreh171000707901", "apreh171000711199"}
    ]
    got = [{v["cell"] for v in grp} for grp in o["duplicate_groups"]]
    if len(o["all_curve_identity"]) != 60 or got != expected:
        print("REVIEW_REQUIRED: dataset differs from the audited original receipt", file=sys.stderr)
        sys.exit(2)
    print("ACCEPT: original curves scanned, matching trace group quarantined")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, UnicodeError) as e:
        print(f"REJECT: {e}", file=sys.stderr)
        sys.exit(2)