"""Source-pinned descriptive factorial audit of the published 48 Bayreuth CF values.

DOI 10.5281/zenodo.15755725; publisher XLSX SHA-256:
ab8845b3d7e6a9aae6bfe5f73fd6173631d1ef75bfb59a4164af7302fbfdbeff
The bundled CSV was extracted from that authenticated workbook (Sheet1, B:E).
This is *not* an independent measurement, causal experiment, or impact study.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path

GOAL_KEY = "bayreuth-20261123-48-source-conditioned-factorial-interaction-v1"
SOURCE_DOI = "10.5281/zenodo.15755725"
SOURCE_XLSX_SHA256 = "ab8845b3d7e6a9aae6bfe5f73fd6173631d1ef75bfb59a4164af7302fbfdbeff"
CSV_SHA256 = "f4890eca9e50d09737b8fd1f25a7094a84e5096cf4c0fb2d021fd196604bb3b3"
TEMPS = (0, 10, 25, 30, 45, 55)
RATES = (0.5, 0.75, 1.0, 1.5)


def load_source_csv(path: str | Path, *, enforce_sha: bool = True) -> list[dict]:
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if enforce_sha and digest != CSV_SHA256:
        raise ValueError(f"Source fixture SHA256 mismatch: {digest}")
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames != ["cell_id", "temp_c", "c_rate", "cf_pct"]:
        raise ValueError("Unexpected source columns")
    rows = []
    for row in reader:
        try:
            cell_id = row["cell_id"]
            temp = int(row["temp_c"])
            rate = float(row["c_rate"])
            cf = float(row["cf_pct"])
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid numeric source cell") from exc
        if not cell_id.startswith("F") or len(cell_id) != 5 or not cell_id[1:].isdigit():
            raise ValueError("Invalid source cell identifier")
        if not all(math.isfinite(v) for v in (temp, rate, cf)):
            raise ValueError("Non-finite value in source")
        rows.append({"cell_id": cell_id, "temp_c": temp, "c_rate": rate, "cf_pct": cf})
    if len(rows) != 48 or len({r["cell_id"] for r in rows}) != 48:
        raise ValueError("Expected 48 distinct physical cell IDs")
    counts = Counter((r["temp_c"], r["c_rate"]) for r in rows)
    if set(counts) != {(t, r) for t in TEMPS for r in RATES} or set(counts.values()) != {2}:
        raise ValueError("Expected full balanced 6 temperatures x 4 C-rates x 2 cells design")
    return rows


def factorial_audit(rows: list[dict]) -> dict:
    if len(rows) != 48:
        raise ValueError("Unbalanced source sample")
    groups = defaultdict(list)
    for v in rows:
        groups[(v["temp_c"], v["c_rate"])].append(v["cf_pct"])
    if set(groups) != {(t, r) for t in TEMPS for r in RATES} or any(len(v) != 2 for v in groups.values()):
        raise ValueError("Unbalanced or unexpected factor levels")
    mean = lambda x: sum(x) / len(x)
    allvals = [r["cf_pct"] for r in rows]
    grand = mean(allvals)
    mt = {t: mean([r["cf_pct"] for r in rows if r["temp_c"] == t]) for t in TEMPS}
    mr = {rate: mean([r["cf_pct"] for r in rows if r["c_rate"] == rate]) for rate in RATES}
    mtr = {key: mean(v) for key, v in groups.items()}
    ss_temp = len(RATES) * 2 * sum((mt[t] - grand)**2 for t in TEMPS)
    ss_rate = len(TEMPS) * 2 * sum((mr[r] - grand)**2 for r in RATES)
    ss_interaction = 2 * sum((mtr[(t,r)]-mt[t]-mr[r]+grand)**2 for t in TEMPS for r in RATES)
    ss_error = sum(sum((x-mtr[key])**2 for x in values) for key, values in groups.items())
    ss_total = sum((x-grand)**2 for x in allvals)
    if not math.isclose(ss_total,ss_temp+ss_rate+ss_interaction+ss_error,rel_tol=1e-12,abs_tol=1e-9):
        raise AssertionError("ANOVA sum-of-squares identity did not close")
    if ss_error <= 0:
        raise ValueError("No valid within-group variance for exploratory F statistic")
    df_error = 24
    mse = ss_error / df_error
    components = {}
    for name, ss, df in (("temperature",ss_temp,5),("c_rate",ss_rate,3),("interaction",ss_interaction,15)):
        components[name] = {"df": df, "SS": ss, "MS": ss/df, "F_exploratory": ss/df/mse,
                            "fraction_of_sample_SS": ss/ss_total,
                            "partial_eta2_exploratory": ss/(ss+ss_error)}
    diffs = {str(rate): mtr[(0,rate)]-mtr[(25,rate)] for rate in RATES}
    max_spread_key,max_spread = max(((key, abs(v[0]-v[1])) for key,v in groups.items()),key=lambda x:x[1])
    return {
        "goal_key": GOAL_KEY,
        "source_doi": SOURCE_DOI,
        "original_publisher_xlsx_sha256": SOURCE_XLSX_SHA256,
        "canonical_48_source_csv_sha256": CSV_SHA256,
        "evidence_grain": "one publisher-derived CF per physical cell; 2 independent cells per temperature×C-rate",
        "n_physical_cells": len(rows),
        "n_conditions": len(groups),
        "n_cells_per_condition": 2,
        "aging_cycles_reported": 70,
        "grand_mean_cf_pct": grand,
        "temperature_mean_cf_pct": {str(k):v for k,v in mt.items()},
        "c_rate_mean_cf_pct": {str(k):v for k,v in mr.items()},
        "ss_total": ss_total,
        "ss_error": ss_error,
        "df_error": df_error,
        "mse_error": mse,
        "anova_fixed_effects_descriptive": components,
        "cf_difference_0C_minus_25C_by_rate_percentage_points": diffs,
        "cf_difference_0C_minus_25C_all_rates_positive": all(d>0 for d in diffs.values()),
        "max_within_condition_pair_difference_percentage_points": max_spread,
        "max_pair_difference_condition": {"temperature_C":max_spread_key[0],"C_rate":max_spread_key[1]},
        "claims": {"independent_current_calibration":False,
                   "cell_level_mechanical_impact":False,
                   "impact_capacity_correlation":False,
                   "causal_temperature_or_rate_effect":False,
                   "absolute_aging_mechanism":False,
                   "generalizes_across_cell_chemistries":False},
        "limitations": ["Publisher-extracted degradation metrics, not a 48-cell raw-current reintegration",
                        "Observational fixed-effect ANOVA F statistics are descriptive and require residual independence/normality/equal variance for classical p-values",
                        "Only two physical replicates per experimental condition; no absolute instrument calibration",
                        "None of these Bayreuth cells underwent dynamic impact: never join to Wei or Sherman impacts by arbitrary labels"]
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--csv",default=str(Path(__file__).with_name("bayreuth_48_publisher_cf.csv")))
    parser.add_argument("--output",default=None)
    args=parser.parse_args()
    result=factorial_audit(load_source_csv(args.csv))
    rendered=json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    if args.output:Path(args.output).write_text(rendered,encoding="utf-8")
    else:print(rendered)

if __name__ == "__main__":main()