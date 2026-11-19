"""Research-only assessment of independently identified fresh/aged cell measurements.

Braun et al. 2022, Zenodo 10.5281/zenodo.6985321, CC BY-NC 4.0.
The upstream authors' algorithms carry additional patent/IP restrictions.
We use only our pre-existing voltage-shape reviewer. Do not redistribute data or
use these results in a commercial offering without appropriate permission.

The two files may be obtained independently from a pinned public GitHub mirror,
but *must* match the publisher's original 2022 MD5s before any computation.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys

SOURCE = {
    "fresh": ("Experimental_data_fresh_cell.csv", "32b57ad539a6794946eb37b3f636a58c"),
    "aged": ("Experimental_data_aged_cell.csv", "da0675c10e8bb3c3ce4c28db815309e8"),
}
MAX_BYTES = 20_000_000
WINDOW_POINTS = 4096
MIN_POINTS = 100


def parse_window(raw: bytes) -> tuple[list[float], list[float], dict]:
    """Read *first* 4096 measured rows; never synthesize missing readings."""
    if not isinstance(raw, bytes) or not 32 < len(raw) < MAX_BYTES:
        raise ValueError("REVIEW_REQUIRED: wrong size or type")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("REVIEW_REQUIRED: source is not UTF8") from exc
    tvals, vvals = [], []
    header_seen = False
    last_time = None
    for row in csv.reader(decoded.splitlines()):
        if len(tvals) >= WINDOW_POINTS:
            break
        if len(row) != 4:
            raise ValueError("REVIEW_REQUIRED: need four measured columns")
        if not header_seen and not tvals:
            try:
                float(row[0])
            except ValueError:
                names = [re.sub(r"[^a-z]", "", p.lower()) for p in row]
                if (not names[0].startswith("time")
                    or not names[1].startswith("current")
                    or not names[2].startswith("voltage")
                    or not names[3].startswith("temperature")):
                    raise ValueError("REVIEW_REQUIRED: unsupported source axes")
                header_seen = True
                continue
        try:
            t, current, voltage, temperature = map(float, row)
        except ValueError as exc:
            raise ValueError("REVIEW_REQUIRED: non-numeric measurement") from exc
        if not all(map(math.isfinite, (t,current,voltage,temperature))):
            raise ValueError("REVIEW_REQUIRED: nonfinite measurement")
        if not (1.5 < voltage < 5.0) or not (-60 < temperature < 120) or abs(current) > 500:
            raise ValueError("REVIEW_REQUIRED: implausible measured value")
        if last_time is not None and t <= last_time:
            raise ValueError("REVIEW_REQUIRED: time must rise strictly")
        last_time = t
        tvals.append(t)
        vvals.append(voltage)
    if len(tvals) < MIN_POINTS:
        raise ValueError("REVIEW_REQUIRED: insufficient original rows")
    if max(vvals)-min(vvals) < 0.05:
        raise ValueError("REVIEW_REQUIRED: measured time window is too flat to near-screen")
    return [t-tvals[0] for t in tvals], vvals, {"rows_in_window":len(tvals),"elapsed_s":tvals[-1]-tvals[0],"voltage_span_v":max(vvals)-min(vvals)}


def audit_sources(files: dict[str,bytes]) -> dict:
    if not isinstance(files,dict) or set(files) != set(SOURCE):
        raise ValueError("REVIEW_REQUIRED: exactly fresh and aged physical cells required")
    sibling = str(Path(__file__).resolve().parent)
    if sibling not in sys.path:
        sys.path.insert(0,sibling)
    import near_duplicate_guard as near
    parsed = {}
    for cell in sorted(SOURCE):
        filename, expected_md5 = SOURCE[cell]
        raw = files[cell]
        if not isinstance(raw,bytes):
            raise ValueError("REVIEW_REQUIRED: original source bytes required")
        md5 = hashlib.md5(raw).hexdigest()
        if md5 != expected_md5:
            raise ValueError("REVIEW_REQUIRED: original-publisher MD5 mismatch")
        t,v,details = parse_window(raw)
        parsed[cell]={"cell":cell,"mode":"first_4096_samples","run":1,
                      "n":len(t),"times":t,"volts":v,
                      "trace_sha256":hashlib.sha256(raw).hexdigest(),"meta":details}
    a,b=parsed['aged'],parsed['fresh']
    def perturbed(original,delta,label):
        return {**original,"cell":original['cell']+label,
                "trace_sha256":hashlib.sha256((original['trace_sha256']+label).encode()).hexdigest(),
                "volts":[x+delta for x in original['volts']]}
    checks={}
    for cell, original in parsed.items():
        positive=near.compare_near(original, perturbed(original,0.001,'_control1mv'))
        negative=near.compare_near(original, perturbed(original,0.010,'_control10mv'))
        if positive is None or negative is not None:
            raise ValueError("REVIEW_REQUIRED: controlled screen on real measurement failed")
        checks[cell]={"controlled_1mv_detected":True,"controlled_10mv_detected":False,
                      "max_abs_diff_mv":positive['max_abs_voltage_diff_mv']}
    cross=near.compare_near(a,b)
    return {
        "schema":"cano.battery.braun2022.fresh-aged-two-physical-cells.v1",
        "publisher":"Braun et al., Offenburg University of Applied Sciences",
        "doi":"10.5281/zenodo.6985321",
        "license":"CC BY-NC 4.0, noncommercial research use only",
        "original_cell_classes":["fresh","pre-aged"],
        "original_publisher_md5_verified":True,
        "measurement_axes":{"time":"s","voltage":"V","current":"A","temperature":"degC"},
        "fixed_window":"first 4096 observed rows per cell (or fewer if file shorter), independently start-normalized",
        "sources":{k:{"md5":SOURCE[k][1],"sha256":parsed[k]['trace_sha256'],**parsed[k]['meta'],**checks[k]} for k in sorted(parsed)},
        "two_distinct_source_files": a['trace_sha256']!=b['trace_sha256'],
        "cross_physical_cell_near_candidate": cross is not None,
        "decision":"REVIEW_REQUIRED" if cross is not None else "SCREEN_ONLY_NOT_CERTIFIED",
        "limitations":[
            "Two documented physical cells, not independent expert-labeled same-cell duplicates.",
            "First-window voltage comparison is not protocol-matched field validation or a field FPR/FNR estimate.",
            "A nonmatch does not establish data provenance independence beyond source metadata.",
            "Published research data has non-commercial license; never redistribute or feed into commercial product without permission.",
            "No SOH prediction or customer field acceptance.",
        ],
    }


def main(argv:list[str]) -> int:
    if len(argv)!=3:
        print('usage: braun_independent_cell_audit.py SOURCE_DIR REPORT.json',file=sys.stderr)
        return 2
    root,out=Path(argv[1]),Path(argv[2])
    try:
        files={cell:(root/filename).read_bytes() for cell,(filename,_) in SOURCE.items()}
        result=audit_sources(files)
        if out.exists() or not out.parent.is_dir():
            raise ValueError('REVIEW_REQUIRED: output file already exists or parent absent')
        with out.open('x',encoding='utf-8') as f:
            json.dump(result,f,sort_keys=True,indent=2)
            f.write('\n')
        print('SOURCE_AUTHENTICATED_TWO_CELLS; decision='+result['decision'])
        return 0
    except (ValueError,OSError,UnicodeError,csv.Error) as exc:
        print('REVIEW_REQUIRED: '+str(exc)[:170],file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main(sys.argv))