#!/usr/bin/env python3
"""Paired-month block sensitivity for original AGV operational-duration data.

A calendar-month pair (2020 month m, 2021 month m) is one resampling unit;
all eligible temperature strata and dates inside that pair are kept together.
This preserves within-month dependence that day-stratum resampling omits.
Months may themselves be dependent; NO causal / battery-health inference.
"""
import datetime
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

from agv_day_cluster_common_support import support_by_pack
from agv_temp_stratified_qc import MD5_AGV, parse_verified
from tsuru_agv_real_source_ci import AGV_URLS, get

MIN_EVENTS=20
MIN_DAYS=3
MIN_MONTH_PAIRS=4
N_DRAW=2000
SEED=20261123


def flatten_days(day_map):
    return [v for values in day_map.values() for v in values]


def monthly_components(pack_support):
    """One month block includes ALL matched temperature bands for both years."""
    blocks=defaultdict(list)
    for (month,band),years in sorted(pack_support.items()):
        a=flatten_days(years[2020])
        b=flatten_days(years[2021])
        if not a or not b:
            continue
        prior,after=statistics.median(a),statistics.median(b)
        if prior<=0:
            continue
        weight=min(len(a),len(b))
        blocks[month].append((weight,100.0*(after/prior-1.0)))
    month_out={}
    for month,pairs in sorted(blocks.items()):
        w=sum(a for a,b in pairs)
        month_out[month]={
            "weight":w,
            "weighted_num":sum(a*b for a,b in pairs),
            "strata":len(pairs)
        }
    return month_out


def aggregate(blocks, selected_months=None):
    if selected_months is None:
        selected_months=sorted(blocks)
    den=sum(blocks[m]["weight"] for m in selected_months)
    return sum(blocks[m]["weighted_num"] for m in selected_months)/den if den else None


def quantile(values,prob):
    if not values:
        return None
    a=sorted(values)
    x=(len(a)-1)*prob
    low=math.floor(x)
    high=math.ceil(x)
    return a[low]*(high-x)+a[high]*(x-low) if high!=low else a[low]


def sign_test_two_sided(month_deltas):
    nonzero=[x for x in month_deltas if x!=0]
    n=len(nonzero)
    if n==0:
        return None
    successes=sum(x>0 for x in nonzero)
    extreme=min(successes,n-successes)
    return min(1.0,2*sum(math.comb(n,i) for i in range(extreme+1))/(2**n))


def evaluate(pack_support, n_draw=N_DRAW, seed=SEED, min_months=MIN_MONTH_PAIRS):
    if n_draw<1:
        raise ValueError("at least one replicate is required")
    blocks=monthly_components(pack_support)
    months=sorted(blocks)
    estimate=aggregate(blocks)
    totals=sum(blocks[m]["weight"] for m in months)
    effective=(totals*totals/sum(blocks[m]["weight"]**2 for m in months)) if months else 0
    month_est={m:blocks[m]["weighted_num"]/blocks[m]["weight"] for m in months}
    jack={m:aggregate(blocks,[k for k in months if k!=m]) for m in months}
    rng=random.Random(seed)
    samples=[]
    if len(months)>=min_months:
        for _ in range(n_draw):
            selected=[months[rng.randrange(len(months))] for _ in months]
            samples.append(aggregate(blocks,selected))
    interval=[quantile(samples,.025),quantile(samples,.975)] if samples else [None,None]
    signs={"negative":sum(x<0 for x in month_est.values()),
           "positive":sum(x>0 for x in month_est.values()),
           "zero":sum(x==0 for x in month_est.values())}
    def rnd(x):
        return round(x,6) if x is not None else None
    return {
        "estimate_pct":rnd(estimate),
        "independent_calendar_month_pair_count":len(months),
        "kish_effective_weighted_month_pairs":rnd(effective),
        "largest_month_weight_fraction":rnd(max((blocks[m]["weight"]/totals for m in months),default=0)),
        "matched_temperature_stratum_count":sum(blocks[m]["strata"] for m in months),
        "month_pair_weights":{str(m):blocks[m]["weight"] for m in months},
        "per_month_pct":{str(m):rnd(v) for m,v in month_est.items()},
        "month_signs":signs,
        "month_sign_test_two_sided_exploratory_p":rnd(sign_test_two_sided(list(month_est.values()))),
        "leave_one_month_out_pct":{str(m):rnd(v) for m,v in jack.items()},
        "leave_one_month_out_crosses_zero_sign_count":sum(
            v is not None and estimate is not None and v*estimate<0 for v in jack.values()),
        "paired_month_resampling_draws":len(samples),
        "paired_month_bootstrap_95pct_exploratory_interval":list(map(rnd,interval)),
        "paired_month_interval_excludes_zero":(
            interval[0] is not None and (interval[0]>0 or interval[1]<0)),
        "insufficient_month_pairs":len(months)<min_months,
    }


def audit(rows, n_draw=N_DRAW, min_events=MIN_EVENTS,min_days=MIN_DAYS,min_months=MIN_MONTH_PAIRS):
    supported, exclusions=support_by_pack(rows,min_events,min_days)
    packs={p:evaluate(groups,n_draw=n_draw,seed=SEED+i,min_months=min_months)
           for i,(p,groups) in enumerate(sorted(supported.items()))}
    return {
        "status":"AGV_PAIRED_CALENDAR_MONTH_BLOCK_SENSITIVITY_ORIGINAL_DATA",
        "parameters":{
            "min_events_per_year_stratum":min_events,
            "min_unique_days_per_year_stratum":min_days,
            "min_month_pairs_for_interval":min_months,
            "resampling_units":"calendar-month pairs, each including all supported temperature strata and both years",
            "resampling_draws_per_battery":n_draw,"seed":SEED
        },
        "source_rows":len(rows),
        "pack_count":len(packs),
        "excluded_candidate_strata":exclusions,
        "packs":packs,
        "negative_estimate_packs":sum(
            v["estimate_pct"] is not None and v["estimate_pct"]<0 for v in packs.values()),
        "positive_estimate_packs":sum(
            v["estimate_pct"] is not None and v["estimate_pct"]>0 for v in packs.values()),
        "interval_excludes_zero_packs":[p for p,v in packs.items()
                                      if v["paired_month_interval_excludes_zero"]],
        "limits":[
            "Only 2020/2021 matching month-pair variation is resampled. Months are not proven IID; this is a sensitivity band, not validated 95 percent coverage.",
            "Calendar month blocks preserve intra-month dependences but cannot remove across-month autocorrelation, year trend, exposure shifts, workload confounding or survivorship effects.",
            "Two-sided month-sign p is exploratory: seasonal/time dependence and selected matched strata violate a simple independent-sign null.",
            "Total discharge counts are not a measured workload assignment, task type or cell-capacity test; no SoH, causal aging or hardware-fault conclusion.",
            "Temperature band is a proxy built from publisher temperature columns whose description is ambiguous."
        ]
    }


def main():
    originals=json.loads(Path("TSURU_AGV_REAL_SOURCE_CI_RECEIPT.json").read_text(encoding="utf-8"))
    prior=json.loads(Path("AGV_DAY_CLUSTER_COMMON_SUPPORT_RECEIPT.json").read_text(encoding="utf-8"))
    if originals.get("status")!="BOTH_ORIGINAL_BYTES_REPLAYED_AND_PINNED" or (
            prior.get("status")!="OBSERVATIONAL_AGV_COMMON_SUPPORT_AND_DAY_CLUSTER_AUDIT"):
        raise ValueError("source or prior day-cluster receipt missing")
    raw=None
    for url in AGV_URLS:
        try:
            b=get(url)
            if len(b)==2265463 and hashlib.md5(b).hexdigest()==MD5_AGV:
                raw=b
                break
        except Exception:
            pass
    if raw is None:
        raise ValueError("publisher source unavailable / invalid identity")
    rows,order_violations=parse_verified(raw)
    if order_violations:
        raise ValueError("unexpected min/max temperature ordering")
    result=audit(rows)
    if len(rows)!=57880 or result["pack_count"]!=10:
        raise ValueError("source size/population mismatch")
    for name,cur in result["packs"].items():
        expected=prior["results"][name]["temperature_stratified_pct"]
        observed=cur["estimate_pct"]
        if expected is None or observed is None or abs(expected-observed)>0.000002:
            raise ValueError("paired-month numerical original-source baseline mismatch: "+name)
    result["input_source_sha256"]=hashlib.sha256(raw).hexdigest()
    result["generated_at_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
    Path("AGV_PAIRED_MONTH_BLOCK_SENSITIVITY_RECEIPT.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("AGV_MONTH_PAIR_BLOCK_REAL_QC="+json.dumps({
        "source_rows":result["source_rows"],
        "negative":result["negative_estimate_packs"],
        "positive":result["positive_estimate_packs"],
        "interval_excludes_zero":result["interval_excludes_zero_packs"],
        "packs":{p:{"month_pairs":r["independent_calendar_month_pair_count"],
                    "effective":r["kish_effective_weighted_month_pairs"],
                    "pct":r["estimate_pct"],
                    "interval":r["paired_month_bootstrap_95pct_exploratory_interval"],
                    "month_signs":r["month_signs"],
                    "lomo_flips":r["leave_one_month_out_crosses_zero_sign_count"]}
                 for p,r in result["packs"].items()}
    },sort_keys=True))


if __name__=="__main__":
    main()
