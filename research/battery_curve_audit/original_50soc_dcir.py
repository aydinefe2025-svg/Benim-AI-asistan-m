"""Figshare original 4-cell, three-temperature, 50%-SOC pulse DCIR audit.

Original study: Stroebl et al., Scientific Data 11:1020 (2024), DOI:
https://doi.org/10.1038/s41597-024-03859-z and source
https://doi.org/10.6084/m9.figshare.25975315 (CC BY 4.0).

The original public author code selects step_type=5032 for 50%-SOC -1C pulses
and uses 10-second voltage/current with OCV correction:
https://github.com/fst2112/Multi-Stage-Lithium-Ion-Battery-Aging-Dataset-Analysis
This is an INDEPENDENT, approximate source-derived proxy, not a reproduction
of the author's full OCV fitting algorithm or calibrated physical DCIR.
Only four physical source labels are examined, each at 10/23/45C.
"""
from __future__ import annotations
from bisect import bisect_left
from collections import deque
from dataclasses import dataclass
from hashlib import md5
from pathlib import Path
from statistics import median
import argparse
import csv
import io
import json
import math
import zipfile

SOURCES = (
    ("TP_k01_04", "TP_k01_04_FIGSHARE_47639005_ORJINAL.zip", 7150834, "8e4f64b05547738d52f8e34a53c578d9"),
    ("TP_k01_05", "TP_k01_05_FIGSHARE_47627092_ORJINAL.zip", 7042134, "fe9d2c2d84050af909926795a55a0e58"),
    ("TP_k04_05", "TP_k04_05_FIGSHARE_47627110_ORIGINAL.zip", 11468262, "93956f361b84a623b258c53e0193225c"),
    ("TP_k04_06", "TP_k04_06_FIGSHARE_47627104_ORIGINAL.zip", 11660912, "17c9445e56c1d3ed6292ac0cf5046fc8"),
)
TEMPERATURES = (10,23,45)
PULSE_STEP = 5032


def parse_seconds(clock: str) -> float:
    parts=clock.strip().split(":")
    if len(parts)!=3:
        raise ValueError("bad source timestamp")
    h,m,s=parts
    t=int(h)*3600+int(m)*60+float(s)
    if int(h)<0 or not 0<=int(m)<60 or not 0<=float(s)<60 or not math.isfinite(t):
        raise ValueError("invalid source time")
    return t


def lerp(x: list[float], y: list[float], point: float) -> float:
    if not x or len(x)!=len(y) or point<x[0] or point>x[-1]:
        raise ValueError("invalid/extrapolated interpolation")
    j=bisect_left(x,point)
    if j==0:return y[0]
    if j==len(x):return y[-1]
    if x[j]==point:return y[j]
    if x[j]<=x[j-1]:raise ValueError("nonincreasing abscissa")
    alpha=(point-x[j-1])/(x[j]-x[j-1])
    return y[j-1]*(1-alpha)+y[j]*alpha


def integral_capacity(series: list[tuple[float,float,float,float]]) -> tuple[list[float],list[float]]:
    if len(series)<500:raise ValueError("missing OCV trace")
    q=[0.0];volt=[series[0][1]]
    for left,right in zip(series,series[1:]):
        if right[0]<=left[0] or abs(right[2])>1.0:
            raise ValueError("invalid low-current OCV segment")
        q.append(q[-1]+(right[0]-left[0])*abs(right[2])/3600)
        volt.append(right[1])
    if q[-1]<3.0 or q[-1]>6.5:raise ValueError("implausible original pseudo-OCV throughput")
    return q,volt


def pseudo_ocv_v(ocv_ch,ocv_dch, soc: float) -> float:
    if not 0<=soc<=1:raise ValueError("SOC outside source")
    qc,vc=integral_capacity(ocv_ch)
    qd,vd=integral_capacity(ocv_dch)
    # Charging starts at low SOC, discharging at high SOC. Interpolate on
    # cumulative throughput, avoiding duplicate abscissa / extrapolation.
    v_ch=lerp(qc,vc,soc*qc[-1])
    v_dch=lerp(qd,vd,(1-soc)*qd[-1])
    return (v_ch+v_dch)/2


def cached_ocv_from_traces(ocv_ch,ocv_dch, soc_after:float) -> tuple[float,float,float]:
    qc,vc=integral_capacity(ocv_ch)
    qd,vd=integral_capacity(ocv_dch)
    def ocv(soc):
        return (lerp(qc,vc,soc*qc[-1])+lerp(qd,vd,(1-soc)*qd[-1]))/2
    return ocv(.5),ocv(soc_after),(qc[-1]+qd[-1])/2


def pulse_metrics(pulse: list[tuple[float,float,float,float]],idle: list[tuple[float,float,float,float]],
                  ocv_ch,ocv_dch,t_after: float=10, baseline_window: tuple[float,float]=(2,65)) -> dict:
    if len(pulse)<500:raise ValueError("missing 50% SOC pulse")
    ts=[x[0] for x in pulse]
    if any(b<=a for a,b in zip(ts,ts[1:])):raise ValueError("non-monotonic pulse")
    starts=[i for i,x in enumerate(pulse) if -5.1<x[2]<-4.75]
    if not starts:raise ValueError("1C negative pulse missing")
    j=starts[0]
    t0=ts[j]; target=t0+t_after
    if target>=ts[-1] or t_after<8.5 or t_after>11.5:raise ValueError("unobserved 10s pulse")
    raw_pre=[x for x in idle if baseline_window[0] <= pulse[0][0]-x[0] <= baseline_window[1] and abs(x[2])<.001]
    if len(raw_pre)<3:raise ValueError("no stable pre-pulse rest")
    baseline=float(median([x[1] for x in raw_pre[-5:]]))
    baseline_temp=float(median([x[3] for x in raw_pre[-5:]]))
    v_at=lerp(ts,[x[1] for x in pulse],target)
    cur=lerp(ts,[x[2] for x in pulse],target)
    temp_at=lerp(ts,[x[3] for x in pulse],target)
    if not all(map(math.isfinite,[baseline,baseline_temp,v_at,cur,temp_at])):
        raise ValueError("nonfinite pulse measurement")
    if not (-5.05<cur<-4.75):raise ValueError("pulse was not 1C during 10s measurement")
    # First-order charge correction referenced to source 50%-SOC pulse:
    q_10=abs(cur)*t_after/3600
    qc,_=integral_capacity(ocv_ch);qd,_=integral_capacity(ocv_dch)
    q_full=(qc[-1]+qd[-1])/2
    soc_after=.5-q_10/q_full
    v_pre_ocv=pseudo_ocv_v(ocv_ch,ocv_dch,.5)
    v_after_ocv=pseudo_ocv_v(ocv_ch,ocv_dch,soc_after)
    dv_ocv=v_after_ocv-v_pre_ocv  # negative during the discharge pulse
    R_raw=(baseline-v_at)/abs(cur)*1000
    R_ocv=(baseline-v_at+dv_ocv)/abs(cur)*1000
    if not (8<R_ocv<80 and 8<R_raw<80 and -0.02<dv_ocv<0):
        raise ValueError("implausible R or pseudoOCV correction")
    return {
        "dcir_raw_milliohm":round(R_raw,6),
        "dcir_pseudoOCV_corrected_milliohm":round(R_ocv,6),
        "ocv_correction_mV":round(dv_ocv*1000,6),
        "pre_pulse_surface_C":round(baseline_temp,5),
        "pulse_at_t_surface_C":round(temp_at,5),
        "pulse_current_A":round(cur,6),
        "baseline_voltage_V":round(baseline,6),
        "pulse_voltage_at_10s_V":round(v_at,6),
        "pulse_1C_onset_offset_from_source_tag_s":round(t0-ts[0],6),
        "pulse_source_samples":len(pulse),
        "pseudoOCV_charge_Ah":round(qc[-1],6),
        "pseudoOCV_discharge_Ah":round(qd[-1],6),
    }


def read_trace(z, name:str):
    rows={31:[],32:[],PULSE_STEP:[]}
    previous=deque(maxlen=256); before=[]; previous_step=None; segment_count={31:0,32:0,PULSE_STEP:0}; total=0
    with z.open(name) as raw:
        with io.TextIOWrapper(raw,encoding="utf-8-sig",newline="") as file:
            reader=csv.DictReader(file)
            expected={"run_time","c_vol","c_cur","c_surf_temp","step_type"}
            if not expected.issubset(set(reader.fieldnames or [])):
                raise ValueError("original waveform missing expected columns")
            for row in reader:
                total+=1;st=int(row["step_type"])
                if st in rows:
                    t=parse_seconds(row["run_time"])
                    v=float(row["c_vol"]);i=float(row["c_cur"]);temp=float(row["c_surf_temp"])
                    if not all(map(math.isfinite,[t,v,i,temp])):
                        raise ValueError("nonfinite pulse or OCV data")
                    if st!=previous_step:
                        segment_count[st]+=1
                        if st==PULSE_STEP:before=list(previous)
                    rows[st].append((t,v,i,temp))
                else:
                    # Pre-pulse rest readings are only needed around the actual
                    # 5032 step; the previous source rows are carried as raw.
                    if st==0:
                        t=parse_seconds(row["run_time"])
                        previous.append((t,float(row["c_vol"]),float(row["c_cur"]),float(row["c_surf_temp"])))
                previous_step=st
    if any(segment_count[st]!=1 for st in rows):raise ValueError("duplicate/missing OCV/pulse phases")
    if total<200000:raise ValueError("suspiciously short original RPT")
    return total,rows,before


def source_archive(a_path:Path, stem:str, size:int, expected_md5:str):
    raw=a_path.read_bytes()
    if len(raw)!=size or md5(raw).hexdigest()!=expected_md5:
        raise ValueError("publisher source MD5/size mismatch")
    z=zipfile.ZipFile(a_path)
    if z.testzip() is not None:raise ValueError("source ZIP CRC corrupted")
    names=set(z.namelist())
    expected={f"{stem}/"}
    for stage in ("01_ET","02_AT"):
        for temperature in TEMPERATURES:
            p=f"{stem}/{stem}_{stage}_T{temperature}"
            expected.update([p+".csv",p+"_meta.txt"])
    if names!=expected:raise ValueError("unexpected source archive path, missing or duplicate members")
    return z


def thermal_secant(low:dict,high:dict) -> float:
    dt=high["pre_pulse_surface_C"]-low["pre_pulse_surface_C"]
    if dt<=3:raise ValueError("temperature points too similar for secant")
    return (high["dcir_pseudoOCV_corrected_milliohm"]-low["dcir_pseudoOCV_corrected_milliohm"])/dt


def audit_source(source_dir:Path):
    results=[];total_rows=0
    for stem,filename,size,pin in SOURCES:
        z=source_archive(source_dir/filename,stem,size,pin)
        with z:
            for temperature in TEMPERATURES:
                measurements={};per_stage={}
                for stage in ("01_ET","02_AT"):
                    n=f"{stem}/{stem}_{stage}_T{temperature}.csv"
                    nrows,traces,pre=read_trace(z,n)
                    total_rows+=nrows
                    out=pulse_metrics(traces[PULSE_STEP],pre,traces[31],traces[32])
                    # Sensitivity to precisely where the 1C plateau voltage is sampled
                    # and how pre-pulse rest window is chosen (not calibration bounds).
                    variants=[]
                    for t in (9.5,10.0,10.5):
                        for win in ((2,45),(2,65)):
                            variants.append(pulse_metrics(traces[PULSE_STEP],pre,traces[31],traces[32],t,win)["dcir_pseudoOCV_corrected_milliohm"])
                    out["dcir_pseudoOCV_sensitivity_min_milliohm"]=min(variants)
                    out["dcir_pseudoOCV_sensitivity_max_milliohm"]=max(variants)
                    out["paired_sensitivity_values_milliohm"]=[round(v,6) for v in variants]
                    out["source_rows"]=nrows
                    measurements["ET" if stage=="01_ET" else "AT"]=out
                et=measurements["ET"];at=measurements["AT"]
                delta=round(at["dcir_pseudoOCV_corrected_milliohm"]-et["dcir_pseudoOCV_corrected_milliohm"],6)
                paired_delta=[round(a-b,6) for a,b in zip(
                    at["paired_sensitivity_values_milliohm"],et["paired_sensitivity_values_milliohm"])]
                results.append({"source_cell_label":stem,"temperature_setpoint_C":temperature,
                                "measured_50soc_pulse_step_type":PULSE_STEP,
                                "ET":et,"AT":at,
                                "AT_minus_ET_pseudoOCV_corrected_DCiR_milliohm":delta,
                                "AT_minus_ET_raw_DCiR_milliohm":round(at["dcir_raw_milliohm"]-et["dcir_raw_milliohm"],6),
                                "AT_minus_ET_pre_pulse_surface_C":round(at["pre_pulse_surface_C"]-et["pre_pulse_surface_C"],5),
                                "all_sensitivity_variants_AT_greater_than_ET":at["dcir_pseudoOCV_sensitivity_min_milliohm"]>et["dcir_pseudoOCV_sensitivity_max_milliohm"],
                                "paired_protocol_variants_min_delta_milliohm":min(paired_delta),
                                "paired_protocol_variants_max_delta_milliohm":max(paired_delta),
                                "paired_protocol_variant_positive_count":sum(d>0 for d in paired_delta),
                                "paired_protocol_variant_total":len(paired_delta)})
    # Thermal sensitivity is only a local secant scenario, NOT a calibrated
    # physical correction. Stage ET R(T) is compared at neighboring setpoints.
    by_cell={(r["source_cell_label"],r["temperature_setpoint_C"]):r for r in results}
    for stem,*_ in SOURCES:
        vals=[by_cell[(stem,t)] for t in TEMPERATURES]
        slope10=thermal_secant(vals[0]["ET"],vals[1]["ET"])
        slope45=thermal_secant(vals[1]["ET"],vals[2]["ET"])
        for index,obs in enumerate(vals):
            possible=(slope10,) if index==0 else (slope45,) if index==2 else (slope10,slope45)
            dt=obs["AT_minus_ET_pre_pulse_surface_C"]
            dR=obs["AT_minus_ET_pseudoOCV_corrected_DCiR_milliohm"]
            corrected=[round(dR-slope*dt,6) for slope in possible]
            obs["thermal_ET_secant_scenario_slopes_milliohm_per_C"]=[round(x,6) for x in possible]
            obs["thermal_ET_secant_scenario_after_equalization_milliohm"]=corrected
    positives=sum(r["AT_minus_ET_pseudoOCV_corrected_DCiR_milliohm"]>0 for r in results)
    return {
        "goal_key":"battery-four-original-50soc-10second-DCIR-three-temperature-measurement-20261121",
        "source_doi":"10.6084/m9.figshare.25975315",
        "author_article_doi":"10.1038/s41597-024-03859-z",
        "publisher_originals_MD5_ZIP_CRC_verified":True,
        "source_cells":len(SOURCES),"temperature_conditions_per_cell":len(TEMPERATURES),
        "original_source_measurement_CSV":len(results)*2,
        "original_rows_read":total_rows,
        "observed_pseudoOCV_corrected_AT_higher_than_ET_count":positives,
        "comparison_count":len(results),
        "independent_physical_cell_count_NOT_12":True,
        "measurement_calibration_uncertainty_quantified":False,
        "12_condition_results_NOT_12_independent_cells":True,
        "temperature_equalization_only_a_local_secant_sensitivity_not_calibration":True,
        "physical_cell_recovery_proven":False,
        "measurement_bias_excluded":False,
        "field_FPR_FNR_established":False,
        "commercial_release_allowed":False,
        "method":"Source 5032 50% SOC -1C, rest baseline median, linear 10s voltage, approx pseudo-OCV from source steps31/32. Not the author's exact reference OCV spline. Thermal ET secant equalization is a hypothetical sensitivity scenario, not independently calibrated correction.",
        "measurements":results,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("out",type=Path)
    parser.add_argument("--original-dir",type=Path,required=True)
    args=parser.parse_args()
    receipt=audit_source(args.original_dir)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(receipt,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("SOURCE_PUBLISHER_50SOC_PULSE_DCiR",receipt["source_cells"],receipt["original_source_measurement_CSV"],receipt["original_rows_read"],receipt["observed_pseudoOCV_corrected_AT_higher_than_ET_count"])
if __name__=="__main__":main()