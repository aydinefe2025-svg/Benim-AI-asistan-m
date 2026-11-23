"""CANO Graz virtual laboratory: deterministic, *synthetic* stress tests.

The attached 2026 real-source manifest is a boundary/benchmark only. These are
NOT real battery capacities, measured impact events, calibrated sensor traces,
or a physical finite-element validation. No external dependencies.
"""
from __future__ import annotations
import argparse
from bisect import bisect_left
from dataclasses import dataclass
import hashlib
import json
import math
import random
import statistics
from pathlib import Path

RECORD_DOI = "10.5281/zenodo.22079387"
REAL_SOURCE_SHA256 = "5627a1606b8e378de0e4e4ced99222509bcbbcb725d26da6e7a5fad34aa42fc7"
REAL_SOURCE_SUMMARY = {
    "cell_02_original_electric_rows": 207383,
    "cell_03_original_electric_rows": 210541,
    "original_sp_rows": 93728,
    "time_matched_sp_rows": 64380,
    "out_of_window_sp_rows": 29348,
    "time_matched_sp_files": 4,
    "source_sp_files": 6,
}
PRELOADS_KN = {"01": 0.0, "02": 1.5, "03": 3.0, "04": 5.0, "05": 15.0}
MODEL_ASSUMPTIONS = {
    "spring_compliance_um_per_kN": 12.0,
    "softening_scale_kN": 40.0,
    "temperature_expansion_um_per_C": 0.15,
    "illustrative_capacity_temperature_coeff_per_C": 0.002,
    "illustrative_capacity_load_coeff_per_kN": 0.001,
    "uncertainties_calibrated": False,
    "dynamic_impact_model": False,
    "finite_element_stress_and_buckling_model": False,
}

@dataclass(frozen=True)
class Electric:
    observed_t: float
    truth_t: float
    physical_cell: str
    stage: str
    voltage_v: float
    current_a: float

@dataclass(frozen=True)
class Sensor:
    observed_t: float
    truth_t: float
    physical_cell: str
    source_cell: str
    stage: str
    source_stage: str
    sensor_um: tuple[float, float, float]


def finite(x: float) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError("finite numeric required")
    return float(x)


def illustrative_displacement_um(preload_kN: float, temp_C: float) -> float:
    """Deliberately uncalibrated example law; does not predict physical failure."""
    p, t = finite(preload_kN), finite(temp_C)
    if not (0 <= p <= 15 and 0 <= t <= 55):
        raise ValueError("outside bounded illustrative parameter domain")
    return 12.0 * p / (1.0 + p/40.0) + 0.15*(t-25.0)


def simulated_capacity_fraction(preload_kN: float, temp_C: float) -> float:
    """Assumed sensitivity, not extracted from Graz source measurements."""
    p, t = finite(preload_kN), finite(temp_C)
    if not (0 <= p <= 15 and 0 <= t <= 55):
        raise ValueError("unsupported virtual model domain")
    return 1.0 - .001*p - .002*abs(t-25.0)


def generate_synthetic(cell: str, seed: int, *, preload_kN: float, temp_C: float=25.0,
        clock_offset_s: float=.2, electric_drop: float=0.0, sensor_noise_um: float=.2,
        stage_id_valid: bool=True, cell_id_valid: bool=True, sensor_stuck: bool=False,
        duration_s: int=1200) -> tuple[list[Electric], list[Sensor]]:
    """Simulate independent clock streams with hidden ground-truth timestamps."""
    if cell not in PRELOADS_KN or PRELOADS_KN[cell] != finite(preload_kN):
        raise ValueError("explicit source identity/preload mismatch")
    for n in (clock_offset_s,electric_drop,sensor_noise_um): finite(n)
    if not(0 <= electric_drop < 1 and 0 <= sensor_noise_um <= 10 and 300 <= duration_s <= 20000):
        raise ValueError("invalid virtual injection scope")
    rng = random.Random(seed)
    base = 1000000.0 if cell=="02" else 2000000.0
    electrical=[]; n=int(duration_s/1.12)
    for k in range(n):
        t=k*1.12
        if rng.random()<electric_drop: continue
        stage="charge" if int(t // 300)%2==0 else "discharge"
        cur=5.0 if stage=="charge" else -5.0
        electrical.append(Electric(base+t,base+t,cell,stage,3.55 + .06*math.sin(t/50),cur))
    sensors=[]
    delta=illustrative_displacement_um(preload_kN,temp_C)
    for k in range(duration_s//5):
        t=float(k*5)
        stage="charge" if int(t // 300)%2==0 else "discharge"
        # Readout noise independent of clock jitter, with known hidden physics truth
        sensor1=1400.0 + delta*(1.0-math.exp(-t/400.0))+rng.gauss(0,sensor_noise_um)
        sensor2=1000.0 + .7*delta*(1.0-math.exp(-t/450.0))+rng.gauss(0,sensor_noise_um)
        sensor3=3206.761671 if sensor_stuck else 3000.0 + .5*delta*(1.0-math.exp(-t/420.0))+rng.gauss(0,sensor_noise_um)
        sensors.append(Sensor(base+t+clock_offset_s,base+t,cell,
             cell if cell_id_valid else ("03" if cell=="02" else "02"),
             stage,stage if stage_id_valid else ("discharge" if stage=="charge" else "charge"),
             (sensor1,sensor2,sensor3)))
    return electrical,sensors


def match_synthetic(electric: list[Electric], sp: list[Sensor], *,
        clock_attested: bool, phase_attested: bool, max_clock_bound_s: float=1.0,
        tolerance_s: float=.7) -> dict:
    """Fail closed without independently attested clock, physical ID and stage.

    Attestation is deliberately supplied by caller, not inferred from signal shape.
    This documents the impossibility of certifying hidden clock drift from
    apparently close timestamps alone.
    """
    if not 0 < finite(max_clock_bound_s) <= 1 or not 0 < finite(tolerance_s) <= 2.5:
        raise ValueError("unsafe matching threshold")
    indexes={}
    for e in electric:
        finite(e.observed_t);finite(e.truth_t)
        if not 0 <= finite(e.voltage_v) <= 6 or abs(finite(e.current_a))>100:
            raise ValueError("source electrical unit range invalid")
        indexes.setdefault((e.physical_cell,e.stage),[]).append(e)
    for key in indexes:
        indexes[key].sort(key=lambda e:e.observed_t)
        if any(x.observed_t>=y.observed_t for x,y in zip(indexes[key],indexes[key][1:])):
            raise ValueError("duplicate or reversed electrical source time")
    time_indexes={key:[x.observed_t for x in values] for key,values in indexes.items()}
    counts={"accepted":0,"rejected_clock":0,"rejected_stage":0,"rejected_cell":0,
            "rejected_time":0,"wrong_time_accepted":0,"ground_truth_correct":0,
            "ambiguous":0,"total_sp_samples":len(sp)}
    diffs=[]
    for s in sp:
        finite(s.observed_t);finite(s.truth_t)
        if len(s.sensor_um)!=3 or any(not math.isfinite(x) for x in s.sensor_um):
            raise ValueError("malformed sensor values")
        if s.physical_cell!=s.source_cell:
            counts["rejected_cell"]+=1;continue
        if not clock_attested:
            counts["rejected_clock"]+=1;continue
        if not phase_attested or s.stage!=s.source_stage:
            counts["rejected_stage"]+=1;continue
        xs=indexes.get((s.physical_cell,s.stage),[])
        times=time_indexes.get((s.physical_cell,s.stage),[])
        j=bisect_left(times,s.observed_t)
        near=[(abs(xs[k].observed_t-s.observed_t),k) for k in (j-1,j) if 0<=k<len(xs)]
        if not near:
            counts["rejected_time"]+=1;continue
        near.sort(key=lambda x:x[0])
        if near[0][0] > tolerance_s:
            counts["rejected_time"]+=1;continue
        if len(near)>1 and abs(near[0][0]-near[1][0])<=1e-9:
            counts["ambiguous"]+=1;continue
        chosen=xs[near[0][1]]
        counts["accepted"]+=1;diffs.append(near[0][0])
        # Here the virtual world reveals which true instant was sampled.
        # The physical laboratory does NOT have this ground truth.
        if abs(chosen.truth_t-s.truth_t)<=max_clock_bound_s:
            counts["ground_truth_correct"]+=1
        else:
            counts["wrong_time_accepted"]+=1
    counts["median_observed_timestamp_gap_s"]=statistics.median(diffs) if diffs else None
    counts["simulated_wrong_timestamp_match_fraction"]=(counts["wrong_time_accepted"]/counts["accepted"]) if counts["accepted"] else None
    counts["simulated_recall"]=(counts["ground_truth_correct"]/len(sp)) if sp else None
    counts["not_a_field_false_positive_or_negative_rate"]=True
    assert sum(counts[x] for x in ("accepted","rejected_clock","rejected_stage","rejected_cell","rejected_time","ambiguous"))==len(sp)
    return counts


def sensor_health(sp: list[Sensor], *, min_range_um: float=.001) -> dict:
    if not sp:return {"evaluated":False,"sensor_stuck":None,"not_calibrated":True}
    result=[]
    for ch in range(3):
        vals=[s.sensor_um[ch] for s in sp]
        result.append(max(vals)-min(vals)<=finite(min_range_um))
    return {"evaluated":True,"sensor_stuck":result,"not_calibrated":True}


def integrate_capacity_ah(times_s: list[float], currents: list[float], *, unit: str, phase: str) -> float:
    """Ground-truth synthetic signed trapezoidal charge. Never infer real I units."""
    if unit not in ("A","mA") or phase not in ("charge","discharge"):
        raise ValueError("explicit current unit and phase required")
    if len(times_s)!=len(currents) or len(times_s)<2:
        raise ValueError("two or more matching samples required")
    ts=[finite(v) for v in times_s];cur=[finite(v) for v in currents]
    if any(b<=a for a,b in zip(ts,ts[1:])):raise ValueError("nonmonotonic time")
    if phase=="charge" and any(c<0 for c in cur):raise ValueError("current sign inconsistent with known phase")
    if phase=="discharge" and any(c>0 for c in cur):raise ValueError("current sign inconsistent with known phase")
    scale=1 if unit=="A" else .001
    return sum((b-a)*(c+d)*.5*scale/3600 for a,b,c,d in zip(ts,ts[1:],cur,cur[1:]))


def percentage_change_same_step(before_ah: float, after_ah: float, *, same_cell:bool,
        same_phase:bool, same_temperature:bool, same_cutoffs:bool, calibrated:bool) -> float:
    for x in (before_ah,after_ah):finite(x)
    if not (same_cell and same_phase and same_temperature and same_cutoffs and calibrated):
        raise ValueError("real scientific comparability and calibration not proven")
    if before_ah<=0 or after_ah<0:raise ValueError("invalid capacity")
    return 100*(after_ah/before_ah-1)


def virtual_worsening_reject(baseline_cost:float, candidate_cost:float, *, max_worsening:float=.10)->bool:
    """Cost metric only, not battery failure certification."""
    a,b=finite(baseline_cost),finite(candidate_cost)
    if a<=0 or b<0 or not 0<=max_worsening<1:raise ValueError("invalid worsening comparison")
    return b > a*(1+max_worsening)+1e-12


def simulate(seed_start:int=20261123, seeds:int=12) -> dict:
    if not (1<=seeds<=200):raise ValueError("bounded number of deterministic seeds")
    scenarios=(
      ("nominal",.20,0.00,.2,True,True,False,True,True),
      ("dropout_20pct",.20,.20,.2,True,True,False,True,True),
      ("dropout_60pct",.20,.60,.2,True,True,False,True,True),
      ("clock_unattested_3s",3.00,.05,.2,True,True,False,False,True),
      ("clock_falsely_attested_3s",3.00,.05,.2,True,True,False,True,True),
      ("missing_phase_provenance",.20,.05,.2,True,True,False,True,False),
      ("spoofed_cell_identity",.20,.05,.2,True,False,False,True,True),
      ("spoofed_stage_identity",.20,.05,.2,False,True,False,True,True),
      ("sensor3_stuck",.20,.05,.2,True,True,True,True,True),
      ("high_sensor_noise",.20,.05,3.,True,True,False,True,True),
    )
    reports=[]
    for (name,offset,drop,noise,phasevalid,cellvalid,stuck,clockatt,phaseatt) in scenarios:
        totals={k:0 for k in ("sp","accepted","true_correct","wrong_accepted","rejected_clock","rejected_stage","rejected_cell","rejected_time","ambiguous","stuck_detected")}
        for seed in range(seed_start,seed_start+seeds):
            for cell in ("02","03"):
                el,sp=generate_synthetic(cell,seed+int(cell)*100000,
                    preload_kN=PRELOADS_KN[cell],clock_offset_s=offset,electric_drop=drop,
                    sensor_noise_um=noise,stage_id_valid=phasevalid,cell_id_valid=cellvalid,
                    sensor_stuck=stuck)
                r=match_synthetic(el,sp,clock_attested=clockatt,phase_attested=phaseatt)
                totals["sp"]+=len(sp)
                for a,b in (("accepted","accepted"),("true_correct","ground_truth_correct"),
                       ("wrong_accepted","wrong_time_accepted"),("rejected_clock","rejected_clock"),
                       ("rejected_stage","rejected_stage"),("rejected_cell","rejected_cell"),
                       ("rejected_time","rejected_time"),("ambiguous","ambiguous")):
                    totals[a]+=r[b]
                totals["stuck_detected"]+=int(sensor_health(sp)["sensor_stuck"][2])
        reports.append({"scenario":name,**totals,
         "simulated_temporal_precision":round(totals["true_correct"]/totals["accepted"],6) if totals["accepted"] else None,
         "simulation_acceptance_rate":round(totals["accepted"]/totals["sp"],6),
         "acceptance_condition":"only source/stage/clock attestation and bounded time tolerance; truth revealed by simulation"})
    virtual_grid=[{"preload_kN":PRELOADS_KN[c],"temperature_C":t,
            "illustrative_displacement_um":round(illustrative_displacement_um(PRELOADS_KN[c],t),4),
            "illustrative_capacity_fraction":round(simulated_capacity_fraction(PRELOADS_KN[c],t),6)}
           for c in PRELOADS_KN for t in (0,10,25,30,45,55)]
    # Explicit unsafe scenario demonstrates why real clock calibration is a blocker.
    fail_safes={
        "source_md5_pin_required":True,"actual_Graz_log_unit_for_current_not_independently_certified":True,
        "unobserved_original_testplan_is_a_release_blocker":True,
        "unknown_real_clock_drift_is_a_release_blocker":True,
        "cross_cell_leakage_excluded_by_source_id":True,
        "real_capacity_change_identified":False,
        "real_fea_mesh_convergence_verified":False,
        "physical_production_release_allowed":False,
    }
    result={"study":"Graz two-cell virtual lab stress test", "source_doi":RECORD_DOI,
       "real_source_archive_sha256":REAL_SOURCE_SHA256,
       "real_publisher_observations_reference_only":REAL_SOURCE_SUMMARY,
       "real_source_raw_data_included":False,
       "simulation_only":True,"sim_seed_start":seed_start,"seeds_per_scenario":seeds,
       "physical_cells_per_scenario":2,"scenarios":reports,"virtual_parameter_grid":virtual_grid,
       "virtual_model_assumptions":MODEL_ASSUMPTIONS,"release_gates":fail_safes,
       "note":"Synthetic virtual sensors; precision/recall cannot be carried over to physical field FPR/FNR."}
    assert len(virtual_grid)==30
    assert all(s["sp"]==seeds*2*240 for s in reports)
    assert any(s["scenario"]=="clock_falsely_attested_3s" and s["wrong_accepted"]>0 for s in reports)
    assert all(s["accepted"]==0 for s in reports if s["scenario"] in
             ("clock_unattested_3s","missing_phase_provenance","spoofed_cell_identity","spoofed_stage_identity"))
    return result


def main() -> None:
    p=argparse.ArgumentParser();p.add_argument("output",type=Path)
    p.add_argument("--seeds",type=int,default=12);a=p.parse_args()
    d=simulate(seeds=a.seeds)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    txt=json.dumps(d,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n"
    a.output.write_text(txt,encoding="utf-8")
    print("GRAZ_SIMULATION_ONLY",len(d["scenarios"]),"scenarios",len(d["virtual_parameter_grid"]),"hypothetical physical-law grid points")
    for s in d["scenarios"]:
        print(s["scenario"],"accepted",s["accepted"],"false-time",s["wrong_accepted"],"total",s["sp"])
    print("RELEASE_BLOCKED_REAL_CALIBRATION_AND_PROVENANCE")
    print("RESULT_SHA256",hashlib.sha256(txt.encode()).hexdigest())

if __name__=="__main__": main()