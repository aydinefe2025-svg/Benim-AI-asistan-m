"""Independently compare the published Stroebl notebook's DCIR OCV axis
against a dimensionally consistent percentage-to-fraction conversion.

MIT-licensed author source references:
* author notebook basic_analyses.ipynb Git blob 0a7cf309311a9c05dd37d4d24098f1fc75896c54
* author src/feature_extraction.py Git blob e6d699223a1df79bf10869f608951c32a0e66c15
* paper DOI 10.1038/s41597-024-03859-z; Figshare 10.6084/m9.figshare.25975315.

This is an independent method audit of a PUBLIC EXAMPLE NOTEBOOK, not proof
that its source typo affected the paper's published figures or measurements.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.interpolate import griddata, interp1d

SOURCES = (
    ("TP_k01_04", "TP_k01_04_FIGSHARE_47639005_ORJINAL.zip", 7150834, "8e4f64b05547738d52f8e34a53c578d9"),
    ("TP_k01_05", "TP_k01_05_FIGSHARE_47627092_ORJINAL.zip", 7042134, "fe9d2c2d84050af909926795a55a0e58"),
    ("TP_k04_05", "TP_k04_05_FIGSHARE_47627110_ORIGINAL.zip", 11468262, "93956f361b84a623b258c53e0193225c"),
    ("TP_k04_06", "TP_k04_06_FIGSHARE_47627104_ORIGINAL.zip", 11660912, "17c9445e56c1d3ed6292ac0cf5046fc8"),
)
TEMPS=(10,23,45)
AUTHOR_NOTEBOOK_SHA="0a7cf309311a9c05dd37d4d24098f1fc75896c54"
AUTHOR_FEATURE_SHA="e6d699223a1df79bf10869f608951c32a0e66c15"


def check_soc_capacity_axis(soc:np.ndarray,q_dch_Ah:float,scale:int):
    """Source demo uses scale=1; physically correct percent conversion scale=100."""
    if scale not in (1,100):raise ValueError("scale must be 1 or 100")
    if not np.isfinite(q_dch_Ah) or not 3 < q_dch_Ah < 6.5:
        raise ValueError("invalid capacity")
    soc=np.asarray(soc,dtype=float)
    if len(soc)<3 or not np.all(np.isfinite(soc)) or abs(soc[0])>1e-9 or abs(soc[-1]-100)>1e-9 or np.any(np.diff(soc)<=0):
        raise ValueError("SOC must be sorted percent domain 0..100")
    return soc*q_dch_Ah/scale


def check_csv_source(z:zipfile.ZipFile,n:str):
    with z.open(n) as raw:
        frame=pd.read_csv(raw,usecols=["run_time","c_cur","c_vol","step_type","c_surf_temp"],low_memory=False)
    if len(frame)<200_000:raise ValueError("too few original rows")
    if set(frame.columns)!={"run_time","c_cur","c_vol","step_type","c_surf_temp"}:raise ValueError("source columns")
    frame["run_time"]=pd.to_timedelta(frame.run_time.str.strip()).dt.total_seconds()
    if frame["run_time"].isna().any() or frame["run_time"].iloc[0]<0 or np.any(np.diff(frame.run_time.values)<0):
        raise ValueError(f"bad original source time {n}: first={frame.run_time.iloc[0]} negatives={(np.diff(frame.run_time.values)<0).sum()}")
    if not np.isfinite(frame[["c_cur","c_vol","c_surf_temp"]].values).all():raise ValueError("nonfinite original source")
    return frame


def source_ocv_and_capacity(df:pd.DataFrame):
    # Numerical conventions duplicated from the author-published feature_extraction.py
    dch=df[(df.step_type==22)&(df.c_cur<0)]
    if len(dch)<100:raise ValueError("missing capacity discharge")
    qd=np.cumsum((dch.run_time.diff()*dch.c_cur).fillna(0).values)
    q_dch=float((qd[0]-qd[-1])/3600)
    ch=df[df.step_type==31]
    ocvd=df[df.step_type==32]
    if len(ch)<1000 or len(ocvd)<1000:raise ValueError("missing source OCV")
    soc=np.linspace(0,100,1001).round(2)
    v_ch=griddata(np.linspace(0,100,len(ch)),ch.c_vol.to_numpy(),soc,method="nearest")
    v_dch=griddata(np.linspace(100,0,len(ocvd)),ocvd.c_vol.to_numpy(),soc,method="nearest")
    ocv=((v_ch+v_dch)/2).round(4)
    if not np.isfinite(ocv).all() or not np.all(np.diff(soc)>0):raise ValueError("invalid source OCV")
    return soc,ocv,q_dch


def author_pulse_view(df:pd.DataFrame):
    """Recreate the author's index and time selection for df_single_pulse(step=5032)."""
    match=df.index[df.step_type==5032]
    if len(match)<1000 or match[-1]-match[0]+1!=len(match):raise ValueError("noncontiguous 50% pulse")
    t_start=df.loc[match[0],"run_time"]
    t_stop=df.loc[match[-1],"run_time"]
    lo=df.index[df.run_time >= t_start - 1][0]
    hi=df.index[df.run_time <= t_stop + 1][-1]
    pulse=df[lo:hi].reset_index(drop=True)
    return pulse


def author_reproduction(df:pd.DataFrame, soc:np.ndarray, ocv:np.ndarray, qd:float, scale:int, baseline_mode:str="author"):
    if baseline_mode not in ("author","rest_65s"):
        raise ValueError("unknown baseline mode")
    """Author's notebook axis + released rdc_extract algorithm at 10 seconds.

    The OCV x-axis is the ONLY variable between scale=1 and scale=100.
    No source pulse/OCV/measurements are changed or padded.
    """
    axis=check_soc_capacity_axis(soc,qd,scale)
    ocv_of_q=interp1d(axis,ocv,kind="linear")
    q_of_ocv=interp1d(ocv,axis,kind="linear")
    pulse=author_pulse_view(df)
    v_first=float(pulse.c_vol.iloc[0])
    trigger=int(((pulse.c_vol-v_first).abs()>=0.005).idxmax())
    if baseline_mode=="author":
        if trigger<=2:raise ValueError("author_voltage_trigger_precedes_sufficient_baseline_samples")
        # original author release: voltage trigger median (not current-weighted)
        v0=float(np.median(pulse.c_vol[:trigger-1]))
    else:
        start_of_source_pulse=float(df.loc[df.step_type==5032,"run_time"].iloc[0])
        rest=df[(df.step_type==0)&(df.run_time>=start_of_source_pulse-65)&
                (df.run_time<=start_of_source_pulse-2)&(df.c_cur.abs()<0.001)]
        if len(rest)<3:
            raise ValueError("missing_stable_pre_pulse_rest_65s")
        v0=float(np.median(rest.c_vol.iloc[-5:]))
    q0=float(q_of_ocv(v0))
    changes=abs(pulse.c_cur.diff())>1
    transitions=changes.index[changes]
    if len(transitions)<2:raise ValueError("missing current state transitions")
    p0=int(transitions[0]);p1=int(transitions[-1])
    p=pulse[p0-1:p1].reset_index(drop=True)
    t=p.run_time.to_numpy()-float(p.run_time.iloc[0])
    if t[-1]<10:raise ValueError("pulse too short")
    q=np.cumsum(np.nan_to_num(np.diff(t,prepend=t[0])*p.c_cur.to_numpy()))/3600
    k=int(np.where(t<=10)[0][-1])
    if k<11:raise ValueError("pulse logger sparse")
    if abs(float(p.iloc[k-10].c_cur))<0.9*abs(float(np.median(p.c_cur[:k]))):
        raise ValueError("pulse not stable at 10s")
    delta_ocv=float(ocv_of_q(q0+q[k])-v0)
    v10=float(p.c_vol.iloc[k])
    median_current=float(np.median(p.c_cur[:k]))
    R_raw_mohm=abs((v10-v0)/median_current)*1000
    R_corr_mohm=abs((v10-delta_ocv-v0)/median_current)*1000
    if not (0<R_raw_mohm<100 and 0<R_corr_mohm<100):raise ValueError("implausible R")
    return {
        "R_mohm":round(R_corr_mohm,6),
        "R_raw_mohm":round(R_raw_mohm,6),
        "OCV_correction_mV":round(delta_ocv*1000,8),
        "pulse_10s_measured_current_A":round(median_current,6),
        "start_Rest_voltage_V":round(v0,8),
        "pulse_at_logged_10s_V":round(v10,8),
        "n_pulse_samples":len(p),
        "pulse_record_10s_seconds":round(float(t[k]),6),
        "source_10s_charge_Ah":round(float(q[k]),8),
        "SOC_axis_max_Ah":round(float(axis[-1]),6),
    }


def sha_bytes(p:Path)->str:
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def audit(originals:Path):
    results=[];by_pair={};n_rows=0
    for stem,filename,bytes_n,md5_pin in SOURCES:
        p=originals/filename
        if not p.is_file() or p.stat().st_size!=bytes_n:
            raise ValueError("missing or wrong source original size: "+stem)
        if hashlib.md5(p.read_bytes()).hexdigest()!=md5_pin:
            raise ValueError("publisher MD5 original mismatch: "+stem)
        with zipfile.ZipFile(p) as z:
            if z.testzip() is not None:raise ValueError("publisher ZIP CRC failed: "+stem)
            for temp in TEMPS:
                pair={}
                for phase in ("ET","AT"):
                    suffix="01_ET" if phase=="ET" else "02_AT"
                    name=f"{stem}/{stem}_{suffix}_T{temp}.csv"
                    if name not in z.namelist():raise ValueError("source CSV missing "+name)
                    df=check_csv_source(z,name)
                    n_rows+=len(df)
                    soc,ocv,q_dch=source_ocv_and_capacity(df)
                    try:
                        strict=author_reproduction(df,soc,ocv,q_dch,scale=1,baseline_mode="author")
                    except (ValueError, IndexError, FloatingPointError) as e:
                        strict={"status":"UNDEFINED","source_reason":str(e)}
                    a=author_reproduction(df,soc,ocv,q_dch,scale=1,baseline_mode="rest_65s")
                    b=author_reproduction(df,soc,ocv,q_dch,scale=100,baseline_mode="rest_65s")
                    for obj in (a,b):
                        obj["source_rows"]=len(df)
                        obj["Q_discharge_Ah"]=round(q_dch,6)
                    pair[phase]={"strict_published_notebook_10s_result_or_fail":strict,
                                 "stable_rest_baseline_public_notebook_100x_axis":a,
                                 "stable_rest_baseline_fixed_SOC_fraction_axis":b,
                                 "difference_fixed_minus_100x_mohm":round(b["R_mohm"]-a["R_mohm"],6)}
                def d(key):return round(pair["AT"][key]["R_mohm"]-pair["ET"][key]["R_mohm"],6)
                pair["cell_label"]=stem;pair["temp_setpoint_C"]=temp
                pair["notebook_AT_minus_ET_mohm"]=d("stable_rest_baseline_public_notebook_100x_axis")
                pair["corrected_AT_minus_ET_mohm"]=d("stable_rest_baseline_fixed_SOC_fraction_axis")
                pair["sign_changed_between_axis_choices"]=(pair["notebook_AT_minus_ET_mohm"]>0)!=(pair["corrected_AT_minus_ET_mohm"]>0)
                results.append(pair)
    if len(results)!=12 or n_rows!=7702133:
        raise ValueError(f"unexpected source total {n_rows} or {len(results)}")
    return {
        "goal_key":"battery-author-public-demo-notebook-ocv-soc-axis-units-audit-20261121",
        "source_article_doi":"10.1038/s41597-024-03859-z",
        "source_dataset_doi":"10.6084/m9.figshare.25975315",
        "author_example_notebook_git_blob":AUTHOR_NOTEBOOK_SHA,
        "author_feature_extraction_git_blob":AUTHOR_FEATURE_SHA,
        "observed_in_public_demo_code_SOC_domain_percent_0_to_100":True,
        "public_example_notebook_multiplies_SOC_0_to_100_directly_by_Q_discharge_Ah":True,
        "compared_units_consistent_divide_by_100":True,
        "source_physical_cells":4,
        "original_measurement_csv_files":24,
        "original_measurement_rows":n_rows,
        "source_archive_md5_and_zip_crc_verified":True,
        "temperature_conditions_per_cell":3,
        "comparison_count":len(results),
        "author_published_article_result_affected_proven":False,
        "cell_aging_causality_proven":False,
        "instrument_calibration_verified":False,
        "physical_sample_custody_verified":False,
        "population_FPR_FNR_proven":False,
        "commercial_release_allowed":False,
        "positive_notebook_axis":sum(r["notebook_AT_minus_ET_mohm"]>0 for r in results),
        "positive_dimensionally_consistent_axis":sum(r["corrected_AT_minus_ET_mohm"]>0 for r in results),
        "sign_changed_axis_choice":sum(r["sign_changed_between_axis_choices"] for r in results),
        "strict_author_example_undefined_measurements":sum(r[phase]["strict_published_notebook_10s_result_or_fail"].get("status")=="UNDEFINED" for r in results for phase in ("ET","AT")),
        "strict_author_example_valid_measurements":sum(r[phase]["strict_published_notebook_10s_result_or_fail"].get("status")!="UNDEFINED" for r in results for phase in ("ET","AT")),
        "stable_pre_pulse_rest_baseline_is_modification_of_author_example":True,
        "measurements":results,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--original-dir",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    report=audit(args.original_dir)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf8")
    print("AUTHOR_DEMO_SOC_UNITS_AUDIT",report["source_physical_cells"],report["original_measurement_csv_files"],report["original_measurement_rows"], report["positive_notebook_axis"],report["positive_dimensionally_consistent_axis"],report["sign_changed_axis_choice"])

if __name__=="__main__":main()