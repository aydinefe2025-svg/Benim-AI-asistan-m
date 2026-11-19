#!/usr/bin/env python3
"""Independent real time-voltage benchmark; research-only, no field certification.

University of Oxford (Reniers, Mulder, Howey 2020), DOI
10.5287/bodleian:gJPdDzvP4, ODbL 1.0; data remain publisher-hosted.
The README identifies profile time [s], current [A], voltage [V].
Never treat a dataset index or state-of-charge as measurement time.
"""
from __future__ import annotations
import csv
from hashlib import sha256
import io
import json
import math
from pathlib import Path
import sys
from urllib.request import Request, urlopen

SOURCE = {
    "BMP_cell1": ("BMP_cell1_profileData.csv", "dcc08hf70v"),
    "BMP_cell2": ("BMP_cell2_profileData.csv", "dvx021f16r"),
}
OXFORD_ROOT = "https://ora.ox.ac.uk/objects/uuid:9aae61af-2949-49f1-8ad5-6aea448979e5/files/"
DOI = "10.5287/bodleian:gJPdDzvP4"
MAX_BYTES = 12_000_000
MAX_POINTS = 200_000


def parse_profile(raw: bytes) -> tuple[list[float], list[float]]:
    """Read the publisher's measured profile time [s] and voltage [V].

    Do not sort observations, interpolate missing values, or misread the current
    and state-of-charge columns as time. The Oxford README establishes the
    physical meaning of the first three columns.
    """
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError("REVIEW_REQUIRED: invalid original source bytes")
    try:
        txt = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("REVIEW_REQUIRED: non-UTF8 Oxford CSV") from exc
    times, volts = [], []
    header_seen = False
    for lineno, row in enumerate(csv.reader(io.StringIO(txt)), 1):
        if not row or all(not part.strip() for part in row):
            raise ValueError("REVIEW_REQUIRED: empty observation row")
        if len(row) < 3:
            raise ValueError("REVIEW_REQUIRED: expected time/current/voltage columns")
        try:
            t, current, voltage = (float(part.strip()) for part in row[:3])
        except ValueError as exc:
            if lineno == 1 and not header_seen:
                header_seen = True
                continue
            raise ValueError("REVIEW_REQUIRED: unexpected nonnumeric observation") from exc
        if not all(math.isfinite(x) for x in (t, current, voltage)):
            raise ValueError("REVIEW_REQUIRED: nonfinite time/current/voltage")
        if not 1.5 < voltage < 5.0 or abs(current) > 1000:
            raise ValueError("REVIEW_REQUIRED: impossible voltage/current range")
        if times and t <= times[-1]:
            raise ValueError("REVIEW_REQUIRED: repeated or decreasing measurement time")
        times.append(t)
        volts.append(voltage)
        if len(times) > MAX_POINTS:
            raise ValueError("REVIEW_REQUIRED: measurement point budget exceeded")
    if len(times) < 100 or max(volts) - min(volts) < 0.05:
        raise ValueError("REVIEW_REQUIRED: short or flat time-voltage profile")
    return times, volts


def audit_profiles(raw_by_id: dict[str, bytes]) -> dict:
    """Check two distinct published cell measurements and a controlled clone.

    The synthetic +1mV and +10mV perturbations are algorithm probes based on
    a REAL measured curve, never independent physical cells or field labels.
    """
    if not isinstance(raw_by_id, dict) or set(raw_by_id) != set(SOURCE):
        raise ValueError("REVIEW_REQUIRED: missing or unexpected original Oxford cells")
    import sys as _sys
    sibling = str(Path(__file__).resolve().parent)
    if sibling not in _sys.path:
        _sys.path.insert(0, sibling)
    import near_duplicate_guard as near
    curves, hashes, samples = [], {}, {}
    for cell in sorted(SOURCE):
        raw = raw_by_id[cell]
        t, v = parse_profile(raw)
        digest = sha256(raw).hexdigest()
        hashes[cell] = digest
        samples[cell] = len(t)
        curves.append({"cell": cell, "mode": "BMP", "run": 1,
                       "n": len(t), "times": t, "volts": v,
                       "trace_sha256": digest})
    a,b = curves
    def controlled_clone(voltage_shift: float, label: str) -> dict:
        return {"cell": label, "mode": a["mode"], "run": 1,
                "n": a["n"], "times": a["times"],
                "volts": [v + voltage_shift for v in a["volts"]],
                "trace_sha256": sha256((hashes[a["cell"]] + label).encode()).hexdigest()}
    positive = near.compare_near(a, controlled_clone(.001, "CONTROL_1MV"))
    negative = near.compare_near(a, controlled_clone(.010, "CONTROL_10MV"))
    if positive is None or negative is not None:
        raise ValueError("REVIEW_REQUIRED: controlled real-curve screening contract failed")
    physical_pair = near.compare_near(a,b)
    equal_bytes = hashes[a["cell"]] == hashes[b["cell"]]
    return {
        "schema": "cano.battery.oxford-external-timevoltage.v1",
        "publisher": "University of Oxford / EnergyVille experimental research",
        "doi": DOI,
        "license": "Open Database License (ODbL) 1.0; attribution required",
        "file_urls": {name: OXFORD_ROOT + SOURCE[name][1] for name in sorted(SOURCE)},
        "cell_count": 2,
        "time_unit": "s",
        "voltage_unit": "V",
        "samples_by_cell": samples,
        "source_sha256": hashes,
        "source_bytes_identical": equal_bytes,
        "source_pair_near_candidate": physical_pair is not None,
        "controlled_1mv_clone_detected": positive is not None,
        "controlled_10mv_clone_detected": negative is not None,
        "decision": "REVIEW_REQUIRED" if equal_bytes or physical_pair is not None
                    else "SCREEN_ONLY_NOT_CERTIFIED",
        "limitations": [
            "Two Oxford cells are external negative-control candidates, not field truth labels.",
            "Artificial controlled clones derive from one real measured cell; they are not independent batteries.",
            "No laboratory inter-operator labels, false-positive/false-negative rate, SOH model, or product certification.",
            "A negative 2mV screen does not prove physical independence or detect all shared provenance.",
        ]
    }


def fetch_originals() -> dict[str, bytes]:
    """Download only the two named Oxford original sources, bounded per file."""
    raws = {}
    for cell, (filename, file_id) in SOURCE.items():
        url = OXFORD_ROOT + file_id
        req = Request(url, headers={"User-Agent": "CANO-science-public-source-audit/1.0"})
        with urlopen(req, timeout=25) as res:
            if res.status != 200:
                raise ValueError("SOURCE_UNAVAILABLE: Oxford original not HTTP 200")
            data = res.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES or len(data) < 1_000:
            raise ValueError("SOURCE_UNAVAILABLE: original file size outside source budget")
        raws[cell] = data
    return raws


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: oxford_external_benchmark.py output.json", file=sys.stderr)
        return 2
    try:
        result = audit_profiles(fetch_originals())
        out = Path(sys.argv[1])
        if out.exists() or not out.parent.exists():
            raise ValueError("REVIEW_REQUIRED: output exists or directory missing")
        with out.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, sort_keys=True, indent=2)
            handle.write("\n")
        print("SOURCE_VERIFIED: independent Oxford time-voltage; controlled clone screening OK; no field certification")
        return 0
    except (ValueError, OSError, UnicodeError, csv.Error, NotImplementedError) as exc:
        print(f"REVIEW_REQUIRED: {type(exc).__name__}: {str(exc)[:180]}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
