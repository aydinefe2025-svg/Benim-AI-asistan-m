"""Published cohort counts only; no raw battery traces (Sherman/Bombik 2026).

DOI 10.3390/batteries12060217, Methods 2.1/2.2 and Results 3.2.
3 impact energies x 3 SOC strata x 5 cells = 45 impacted cells.
5 J: SOC=0 four fail, SOC=20 zero fail, SOC=40 two fail.
The authors also say 'half' of 5 J cells survive; exact described
strata give 9/15 = 60%. Counts are NOT capacity values.
"""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
from statistics import NormalDist

DOI="10.3390/batteries12060217"
IMPACT_ENERGIES=(3,5,7)
SOC_PERCENT=(0,20,40)
PER_STRATUM=5
SURVIVORS={3:{0:5,20:5,40:5},5:{0:1,20:5,40:3},7:{0:0,20:0,40:0}}

def wilson(k:int,n:int,confidence:float=0.95):
    if type(k)!=int or type(n)!=int or n<1 or k<0 or k>n or not 0<confidence<1:
        raise ValueError("invalid Wilson inputs")
    z=NormalDist().inv_cdf((1+confidence)/2); p=k/n; d=1+z*z/n
    c=(p+z*z/(2*n))/d
    h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return (0. if k==0 else max(0.,c-h)),(1. if k==n else min(1.,c+h))

def audit():
    if set(SURVIVORS)!=set(IMPACT_ENERGIES):
        raise AssertionError("energy mismatch")
    by_soc=[]; by_energy=[]
    for j in IMPACT_ENERGIES:
        if set(SURVIVORS[j])!=set(SOC_PERCENT):
            raise AssertionError("SOC mismatch")
        k=0
        for soc in SOC_PERCENT:
            v=SURVIVORS[j][soc]
            if type(v)!=int or not 0<=v<=PER_STRATUM:
                raise AssertionError("invalid published stratum count")
            k+=v
            lo,hi=wilson(v,PER_STRATUM)
            by_soc.append(dict(impact_j=j,soc_percent=soc,n_impacted=PER_STRATUM,
                n_survived_one_week=v,n_failed_one_week=PER_STRATUM-v,
                survival_fraction=v/PER_STRATUM,wilson_95_low=lo,wilson_95_high=hi))
        n=PER_STRATUM*len(SOC_PERCENT); lo,hi=wilson(k,n)
        by_energy.append(dict(impact_j=j,n_impacted=n,n_survived_one_week=k,
            n_failed_one_week=n-k,survival_fraction=k/n,
            wilson_95_low=lo,wilson_95_high=hi,
            post_impact_200cycle_capacity_estimate=None,
            raw_sample_ids_available_in_article=False))
    if sum(x["n_impacted"] for x in by_energy)!=45 or [x["n_survived_one_week"] for x in by_energy]!=[15,9,0]:
        raise AssertionError("published count crosscheck failed")
    return {
        "study":"Sherman and Bombik, Batteries 2026, 12(6), 217",
        "source_doi":DOI,"source_url":"https://doi.org/"+DOI,
        "source_sections":["Methods 2.1","Methods 2.2","Results 3.2","Results 3.3","Data Availability Statement"],
        "data_level":"reconstructed counts from published text; no individual raw measurements",
        "n_impacted_total":45,"n_control":None,
        "protocol":{"impact_j":list(IMPACT_ENERGIES),"soc_percent":list(SOC_PERCENT),
            "samples_per_energy_soc":PER_STRATUM,"rest_days":7,"rest_temperature_c":30,
            "discard_rule":"voltage < 3 V after one week; unsafe for further testing",
            "post_impact_cycles_for_survivors":200,
            "one_week_survival_not_equivalent_to_post_impact_capacity":True},
        "group_survival":by_energy,"soc_strata":by_soc,
        "editorial_discrepancy":"Paper says about half of 5 J survived; detailed 4+0+2 failures produce 9 of 15 = 60% survivors.",
        "hard_limit":["Seven-joule group has ZERO survivors, not zero capacity fade.",
          "Only survivors were cycled 200 times; survivorship conditioning must be explicit.",
          "Raw per-cell capacity and code available only on request to authors, per data availability statement.",
          "Do not join 2025 Wei et al. or Bayreuth cells to these subjects.",
          "Wilson intervals are small-sample sampling uncertainty, not safety certification."]
    }

def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path);args=p.parse_args()
    s=json.dumps(audit(),sort_keys=True,ensure_ascii=False,indent=2)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(s,encoding="utf8")
    else:print(s,end="")

if __name__=="__main__":main()
