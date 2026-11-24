#!/usr/bin/env python3
"""AGV observed-duration robustness: common support and day-cluster resampling.

This does NOT estimate battery SoH, capacity fade, causal aging, or temperature
causality. Day resampling also assumes exchangeability across days within each
year/month/temperature stratum and does not remove longer-range serial dependence.
"""
import collections
import datetime
import hashlib
import json
import random
import statistics
from pathlib import Path

from agv_temp_stratified_qc import MD5_AGV,parse_verified
from tsuru_agv_real_source_ci import AGV_URLS,get

MIN_EVENTS=20
MIN_DAYS=3
BOOT_DRAWS=300
SEED=20261123


def flatten(day_dict):
    return [v for values in day_dict.values() for v in values]


def support_by_pack(rows, min_events=MIN_EVENTS, min_days=MIN_DAYS):
    pools=collections.defaultdict(lambda:collections.defaultdict(
        lambda:collections.defaultdict(lambda:collections.defaultdict(list))))
    for r in rows:
        year=r["date"].year
        if year not in (2020,2021):
            continue
        key=(r["date"].month,r["temp_band"])
        pools[r["battery"]][key][year][r["date"]].append(r["cycle"])
    result={}
    excluded=collections.Counter()
    for pack in sorted({r["battery"] for r in rows}):
        good={}
        for key,years in pools[pack].items():
            left=years.get(2020,{})
            right=years.get(2021,{})
            if min(len(left),len(right)) < min_days:
                excluded["insufficient_unique_days"]+=1
                continue
            a,b=flatten(left),flatten(right)
            if min(len(a),len(b)) < min_events:
                excluded["insufficient_events"]+=1
                continue
            if statistics.median(a) <= 0:
                excluded["zero_baseline_median"]+=1
                continue
            good[key]={2020:dict(left),2021:dict(right)}
        result[pack]=good
    return result,dict(excluded)


def weighted_contrast(pairs):
    numer=denom=0
    for n,a,b in pairs:
        if a<=0 or n<=0:
            continue
        numer+=n*(100*(b/a-1))
        denom+=n
    return numer/denom if denom else None


def calculate(pack_support, exclude_month=None, resample=None):
    by_month=collections.defaultdict(lambda:{2020:[],2021:[]})
    pairs=[]
    deltas=[]
    for (month,band),years in sorted(pack_support.items()):
        if exclude_month==month:
            continue
        values={}
        for year in (2020,2021):
            daily=years[year]
            if resample is None:
                data=flatten(daily)
            else:
                dates=list(daily)
                data=[v for _ in dates for v in daily[resample.choice(dates)]]
            values[year]=data
            by_month[month][year].extend(data)
        a,b=values[2020],values[2021]
        if not a or not b:
            continue
        ma,mb=statistics.median(a),statistics.median(b)
        if ma<=0:
            continue
        weight=min(len(flatten(years[2020])),len(flatten(years[2021])))
        pairs.append((weight,ma,mb))
        deltas.append(100*(mb/ma-1))
    pooled=[]
    for month,years in by_month.items():
        a,b=years[2020],years[2021]
        if a and b and statistics.median(a)>0:
            pooled.append((min(len(a),len(b)),statistics.median(a),statistics.median(b)))
    return {
        "temperature_stratified_pct":weighted_contrast(pairs),
        "same_support_month_pooled_pct":weighted_contrast(pooled),
        "equal_stratum_weight_pct":statistics.mean(deltas) if deltas else None,
        "eligible_strata":len(pairs)
    }


def quantile(numbers,q):
    arr=sorted(numbers)
    if not arr:
        return None
    pos=(len(arr)-1)*q
    lo=int(pos)
    hi=min(lo+1,len(arr)-1)
    return arr[lo]+(pos-lo)*(arr[hi]-arr[lo])


def audit(rows, draws=BOOT_DRAWS, min_events=MIN_EVENTS, min_days=MIN_DAYS):
    support,exclusions=support_by_pack(rows,min_events,min_days)
    results={}
    for i,(pack,groups) in enumerate(sorted(support.items())):
        orig=calculate(groups)
        months=sorted({k[0] for k in groups})
        daycount=[min(len(x[2020]),len(x[2021])) for x in groups.values()]
        lomo={str(m):calculate(groups,exclude_month=m)["temperature_stratified_pct"]
              for m in months}
        rng=random.Random(SEED+i)
        sims=[]
        for _ in range(draws):
            value=calculate(groups,resample=rng)["temperature_stratified_pct"]
            if value is not None:
                sims.append(value)
        pct=orig["temperature_stratified_pct"]
        bounds=[quantile(sims,.025),quantile(sims,.975)] if sims else [None,None]
        results[pack]={
            **{key:round(val,6) if isinstance(val,float) else val for key,val in orig.items()},
            "supported_months":len(months),
            "min_independent_days_per_year_stratum":min(daycount) if daycount else 0,
            "leave_one_supported_month_out_pct":{k:round(v,6) if v is not None else None for k,v in lomo.items()},
            "leave_one_month_out_opposite_sign_count":sum(
                v is not None and pct is not None and v*pct<0 for v in lomo.values()),
            "day_stratified_bootstrap_draws_valid":len(sims),
            "day_stratified_bootstrap_95pct_interval":[round(x,6) if x is not None else None for x in bounds],
            "bootstrap_excludes_zero":bounds[0] is not None and (bounds[0]>0 or bounds[1]<0),
            "unsupported_if_no_matching_days":pct is None
        }
    return {
        "status":"OBSERVATIONAL_AGV_COMMON_SUPPORT_AND_DAY_CLUSTER_AUDIT",
        "parameters":{"min_events_per_year_stratum":min_events,"min_distinct_days_per_year_stratum":min_days,
                      "temperature_midpoint_bin_celsius":5,"bootstrap_draws":draws,"seed":SEED},
        "source_n_rows":len(rows),
        "pack_count":len(support),
        "excluded_candidate_strata":exclusions,
        "results":results,
        "negative_sign_packs":sum(v["temperature_stratified_pct"] is not None and
                                  v["temperature_stratified_pct"]<0 for v in results.values()),
        "positive_sign_packs":sum(v["temperature_stratified_pct"] is not None and
                                  v["temperature_stratified_pct"]>0 for v in results.values()),
        "no_support_packs":sum(v["temperature_stratified_pct"] is None for v in results.values()),
        "limitations":[
            "The month-pooled and temperature-stratified estimates use exactly the same eligible source rows but distinct aggregation rules.",
            "Stratum-level day resampling assumes exchangeability of days; it does not account for serial dependence between days or covariance across same-day temperature strata.",
            "Percentile bootstrap intervals are descriptive sensitivity intervals, not calibrated causal or laboratory confidence statements.",
            "No workload, duty cycle, amperage trajectory or mission labels were measured in this AGV CSV; workload confounding remains open.",
            "cycletime is an operational duration, not full-cycle measured capacity, battery state-of-health or battery physical aging.",
            "The upstream temperature columns are ambiguously described; midpoint is only an uncalibrated exploratory proxy."
        ]
    }


def main():
    original=json.loads(Path("TSURU_AGV_REAL_SOURCE_CI_RECEIPT.json").read_text(encoding="utf-8"))
    temperature=json.loads(Path("AGV_TEMP_MATCHED_REAL_SOURCE_RECEIPT.json").read_text(encoding="utf-8"))
    if original.get("status")!="BOTH_ORIGINAL_BYTES_REPLAYED_AND_PINNED" or        temperature.get("status")!="REAL_AGV_TEMP_STRATIFIED_EXPLORATORY_QC":
        raise ValueError("prior real original-source audit not established")
    raw=None
    for url in AGV_URLS:
        try:
            candidate=get(url)
            if len(candidate)==2265463 and hashlib.md5(candidate).hexdigest()==MD5_AGV:
                raw=candidate
                break
        except Exception:
            continue
    if raw is None:
        raise ValueError("original publisher AGV CSV unavailable or identity mismatch")
    rows,violations=parse_verified(raw)
    if violations!=0:
        raise ValueError("unexpected temperature field ordering inversion")
    report=audit(rows)
    if report["source_n_rows"]!=57880 or report["pack_count"]!=10:
        raise ValueError("source record counts do not match known publisher data")
    report["source_md5"]=MD5_AGV
    report["source_sha256"]=hashlib.sha256(raw).hexdigest()
    report["generated_at_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
    out=Path("AGV_DAY_CLUSTER_COMMON_SUPPORT_RECEIPT.json")
    out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("AGV_COMMON_SUPPORT_DAY_QC="+json.dumps({
        "source_rows":len(rows),"negatives":report["negative_sign_packs"],
        "positives":report["positive_sign_packs"],"unsupported":report["no_support_packs"],
        "packs":{p:{"stratified":v["temperature_stratified_pct"],
                    "same_support_month":v["same_support_month_pooled_pct"],
                    "interval":v["day_stratified_bootstrap_95pct_interval"],
                    "lomo_sign_flips":v["leave_one_month_out_opposite_sign_count"],
                    "eligible_strata":v["eligible_strata"]}
                 for p,v in report["results"].items()}
    },sort_keys=True))


if __name__=="__main__":
    main()
