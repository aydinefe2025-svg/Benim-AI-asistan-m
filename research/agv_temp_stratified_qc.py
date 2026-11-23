#!/usr/bin/env python3
"""Exploratory month + temperature matched AGV operating-time audit.
No battery SoH, physical failure, or causal aging conclusion.
"""
import collections
import csv
import datetime
import hashlib
import io
import json
import math
import statistics
from pathlib import Path

MD5_AGV = "2faa82bd0c27763d4b12d4c58510a1f5"
FIELDS = ("counter","date","cycletime","totaldischarge","mintemperature","maxtemperature","battery")


def parse_verified(raw):
    if len(raw) != 2265463 or hashlib.md5(raw).hexdigest() != MD5_AGV:
        raise ValueError("original publisher AGV identity mismatch")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if tuple(reader.fieldnames or ()) != FIELDS:
        raise ValueError("AGV schema mismatch")
    out = []
    order_violations = 0
    for row in reader:
        date = datetime.date.fromisoformat(row["date"])
        left, right = float(row["mintemperature"]), float(row["maxtemperature"])
        cycle = int(row["cycletime"])
        if not math.isfinite(left) or not math.isfinite(right) or cycle < 0:
            raise ValueError("invalid temperature or operating duration")
        order_violations += left > right
        out.append({
            "battery":row["battery"],"date":date,"cycle":cycle,
            "temp_band":math.floor((left + right) / 10) * 5,
            "temperature_low":min(left,right),"temperature_high":max(left,right),
            "counter":int(row["counter"]),"totaldischarge":int(row["totaldischarge"])
        })
    if len(out) != 57880 or len({r["battery"] for r in out}) != 10:
        raise ValueError("record or pack count mismatch")
    return out,order_violations


def grouped_paired_year(rows, by_temp, minimum):
    groups = collections.defaultdict(lambda:collections.defaultdict(list))
    for row in rows:
        if row["date"].year not in (2020,2021):
            continue
        key = (row["date"].month,row["temp_band"]) if by_temp else (row["date"].month,)
        groups[row["battery"]][(key,row["date"].year)].append(row["cycle"])
    result = {}
    for pack in sorted({r["battery"] for r in rows}):
        bucket = groups[pack]
        weighted = []
        for key,year in bucket:
            if year != 2020:
                continue
            before = bucket[(key,2020)]
            after = bucket.get((key,2021),[])
            if min(len(before),len(after)) < minimum:
                continue
            before_median,after_median = statistics.median(before),statistics.median(after)
            if before_median <= 0:
                continue
            weight = min(len(before),len(after))
            weighted.append((weight,100*(after_median/before_median-1)))
        n = sum(w for w,v in weighted)
        result[pack] = {
            "matched_strata":len(weighted),"matched_min_pair_events":n,
            "weighted_pct":round(sum(w*v for w,v in weighted)/n,6) if n else None
        }
    return result


def run(rows,temperature_order_violations):
    comparisons = {}
    for cutoff in (10,20,30,50):
        month = grouped_paired_year(rows,False,cutoff)
        matched = grouped_paired_year(rows,True,cutoff)
        comparisons[str(cutoff)] = {
            "month_only":month,"month_and_5C_midpoint":matched,
            "month_only_negative":sum(v["weighted_pct"] is not None and v["weighted_pct"]<0 for v in month.values()),
            "month_temp_negative":sum(v["weighted_pct"] is not None and v["weighted_pct"]<0 for v in matched.values()),
            "month_temp_insufficient":sum(v["weighted_pct"] is None for v in matched.values()),
            "sign_reversals":[p for p in month if month[p]["weighted_pct"] is not None and
                              matched[p]["weighted_pct"] is not None and
                              month[p]["weighted_pct"]*matched[p]["weighted_pct"]<0]
        }
    if comparisons["20"]["month_only_negative"] != 9:
        raise ValueError("previous matched-month baseline not reproduced")
    fb5 = comparisons["20"]["month_only"].get("FB-5",{}).get("weighted_pct")
    if fb5 is None or not 0.75 < fb5 < 0.78:
        raise ValueError("FB-5 source control failed")
    return {
        "status":"REAL_AGV_TEMP_STRATIFIED_EXPLORATORY_QC",
        "source_md5":MD5_AGV,"n_records":len(rows),
        "n_batteries":len({r["battery"] for r in rows}),
        "input_columns_temperature_order_violations":temperature_order_violations,
        "documentation_inversion":"README swaps min/max temperature descriptions versus CSV names/example. Use unlabeled pair midpoint only.",
        "comparison":comparisons,
        "limitations":[
            "Partial discharge operating time is not a discharge-to-empty capacity test",
            "Temperature midpoint of two extremes is an exploratory proxy, not calibrated ambient temperature",
            "Matching does not control workload, repeated measures or missing metadata",
            "No causal aging, physical fault, or state-of-health inference"
        ]
    }


def main():
    from tsuru_agv_real_source_ci import AGV_URLS,get
    previous = json.loads(Path("TSURU_AGV_REAL_SOURCE_CI_RECEIPT.json").read_text())
    if previous.get("status") != "BOTH_ORIGINAL_BYTES_REPLAYED_AND_PINNED":
        raise ValueError("original AGV receipt prerequisite absent")
    raw = None
    for url in AGV_URLS:
        try:
            candidate = get(url)
            if len(candidate)==2265463 and hashlib.md5(candidate).hexdigest()==MD5_AGV:
                raw = candidate
                break
        except Exception:
            continue
    if raw is None:
        raise ValueError("fail closed: original AGV data unavailable")
    rows,violations = parse_verified(raw)
    result = run(rows,violations)
    result["agv_sha256"] = hashlib.sha256(raw).hexdigest()
    result["executed_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    Path("AGV_TEMP_MATCHED_REAL_SOURCE_RECEIPT.json").write_text(
        json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("AGV_TEMP_MATCHED_REAL_SOURCE_DIAGNOSTIC="+json.dumps({
        "baseline_n20_negative":result["comparison"]["20"]["month_only_negative"],
        "matched_temp_n20_negative":result["comparison"]["20"]["month_temp_negative"],
        "matched_temp_n20_insufficient":result["comparison"]["20"]["month_temp_insufficient"],
        "sign_reversals":result["comparison"]["20"]["sign_reversals"],
        "temperature_order_violations":violations
    },sort_keys=True))


if __name__ == "__main__":
    main()
