#!/usr/bin/env python3
"""Source-pinned *published experimental* time-voltage screening (not field QA).

PyBaMM Team pybamm-data v1.0.1 releases two Enertech discharge-voltage
curves attributed to Ai et al. (2020) and Rieger et al. (2016). Published
source notes say column 1 is time [s] and column 2 voltage [V].
These are release data files, not original cycler logs or two independent
physical-cell labels. Original bytes stay off our repo and artifacts.
"""
from __future__ import annotations
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sys

RELEASE = "https://github.com/pybamm-team/pybamm-data/releases/tag/v1.0.1"
SOURCE = {
    "0.5C": ("0.5C_discharge_U.txt", "9ed8368b2c6149d2a69218e7df6aaade2511c9f7f6fc7932cda153d9a3a10f39"),
    "1C": ("1C_discharge_U.txt", "8fc19de45172215d65c56522c224e6fc700ee443db236b814238a829b7a14c3a"),
}
MAX_SOURCE_BYTES = 2_000_000
MAX_POINTS = 100_000


def parse_voltage_curve(raw: bytes) -> tuple[list[float], list[float]]:
    """Read first and second publisher columns as seconds and volts, never SOC."""
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_SOURCE_BYTES:
        raise ValueError("REVIEW_REQUIRED: source invalid or over budget")
    try:
        txt = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("REVIEW_REQUIRED: source encoding incompatible") from exc
    times, volts = [], []
    header_seen = False
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not times and not header_seen and any(ch.isalpha() for ch in line):
            # Two-column optional header may contain spaces within unit labels.
            # Do not accept a swapped time/voltage or current/SOC header.
            signature = re.sub(r"[^a-z]", "", line.lower())
            if signature not in ("timesvoltagev", "timescellvoltagev",
                                 "timesuv", "timesv"):
                raise ValueError("REVIEW_REQUIRED: unknown measurement column order")
            header_seen = True
            continue
        columns = line.split(",") if "," in line else line.split()
        if len(columns) != 2:
            raise ValueError("REVIEW_REQUIRED: expected exactly time and voltage columns")
        try:
            t, v = map(float, columns)
        except ValueError as exc:
            raise ValueError("REVIEW_REQUIRED: invalid observation") from exc
        if not math.isfinite(t) or not math.isfinite(v) or not 1.5 < v < 5.0:
            raise ValueError("REVIEW_REQUIRED: impossible/nonfinite voltage or time")
        if times and t <= times[-1]:
            raise ValueError("REVIEW_REQUIRED: non-increasing measurement time")
        times.append(t)
        volts.append(v)
        if len(times) > MAX_POINTS:
            raise ValueError("REVIEW_REQUIRED: sample count exceeds budget")
    if len(times) < 100 or max(volts)-min(volts) < 0.05:
        raise ValueError("REVIEW_REQUIRED: insufficient samples or voltage span")
    return times, volts


def audit_published_curves(raws: dict[str, bytes]) -> dict:
    """Independent published source bytes + synthetic +1mV / +10mV probes."""
    if not isinstance(raws, dict) or set(raws) != set(SOURCE):
        raise ValueError("REVIEW_REQUIRED: missing or unexpected published curve")
    sibling = str(Path(__file__).resolve().parent)
    if sibling not in sys.path:
        sys.path.insert(0,sibling)
    import near_duplicate_guard as near
    records = []
    for rate in sorted(SOURCE):
        filename, expected_hash = SOURCE[rate]
        raw = raws[rate]
        digest = sha256(raw).hexdigest() if isinstance(raw,bytes) else ""
        if digest != expected_hash:
            raise ValueError("REVIEW_REQUIRED: independent published SHA256 check failed")
        times, volts = parse_voltage_curve(raw)
        original = {"cell":rate+"_PUBLISHED", "mode":rate, "run":1,
                    "n":len(times), "times":times, "volts":volts,
                    "trace_sha256":digest}
        def probe(delta:float,label:str):
            return {"cell":rate+"_"+label, "mode":rate, "run":1,"n":len(times),
                    "times":times, "volts":[x+delta for x in volts],
                    "trace_sha256":sha256((digest+label).encode()).hexdigest()}
        positive=near.compare_near(original,probe(0.001,"CONTROL_1MV"))
        negative=near.compare_near(original,probe(0.010,"CONTROL_10MV"))
        if positive is None or negative is not None:
            raise ValueError("REVIEW_REQUIRED: measured-curve controlled probe failed")
        records.append({"rate":rate,"filename":filename,"sha256":digest,
                        "samples":len(times), "time_start_s":times[0],
                        "time_end_s":times[-1],
                        "voltage_range_v":[round(min(volts),9),round(max(volts),9)],
                        "controlled_1mv_detected":True,
                        "controlled_10mv_detected":False,
                        "controlled_max_diff_mv":positive["max_abs_voltage_diff_mv"]})
    return {"schema":"cano.battery.pybamm-published-real-timevoltage.v1",
            "publisher":"PyBaMM Team / Enertech published experiment curves",
            "release":RELEASE,
            "source_license":"PyBaMM data repo BSD 3-Clause; original paper attribution required",
            "source_measure":"published discharge-voltage curves; not original cycler files",
            "time_unit":"s", "voltage_unit":"V",
            "source_curves":records,
            "decision":"PASS_CONTROLLED_RESEARCH_SCREEN_ONLY",
            "no_field_certification":True,
            "limitations":[
              "Two discharge C-rates are not two independently labeled physical cells.",
              "Controlled +1/+10mV copies reuse one published curve and are not field positives/negatives.",
              "This checks published source SHA and near-algorithm boundary, not FPR/FNR or SOH.",
              "Do not combine unequal current protocols for duplicate-cell classification.",
            ]}


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: pybamm_published_benchmark.py SOURCE_DIR REPORT_JSON",file=sys.stderr)
        return 2
    root, output = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        raws={}
        for rate,(filename,_) in SOURCE.items():
            path=root/filename
            if not path.is_file() or path.is_symlink():
                raise ValueError("REVIEW_REQUIRED: missing safe publisher file")
            raws[rate]=path.read_bytes()
        report=audit_published_curves(raws)
        if not output.parent.is_dir() or output.exists():
            raise ValueError("REVIEW_REQUIRED: output must be new file in existing directory")
        with output.open("x",encoding="utf-8") as file:
            json.dump(report,file,sort_keys=True,indent=2)
            file.write("\n")
        print("PASS_CONTROLLED_RESEARCH_SCREEN_ONLY",
              "curves",len(report["source_curves"]),
              "samples",sum(r["samples"] for r in report["source_curves"]))
        return 0
    except (OSError,ValueError,UnicodeError) as exc:
        print("REVIEW_REQUIRED:",str(exc)[:160],file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
