"""Read published LCO reference performance tests, not a synthetic cell or Graz copy."""
import hashlib, json, math, pathlib, sys, urllib.request, csv
import numpy as np
from scipy.io import loadmat, whosmat
from scipy.stats import spearmanr

DOI="10.5281/zenodo.14914172"
URL="https://zenodo.org/records/14914172/files/Aging_Dataset_Cycling.mat?download=1"
MD5="9187ee3b770a3fdb59aad32b0f007a52"
FIELDS=("Time","I_EL","I_PS","V_batt","T_batt","T_amb","Las1","Las2","Dthk")
def unwrap(x):
    while isinstance(x,np.ndarray) and x.size==1 and x.dtype.kind=="O":
        x=x.flat[0]
    return x

def vector(x):
    return np.asarray(unwrap(x),dtype=float).ravel()

def field(s,k):
    return vector(getattr(unwrap(s),k))

def measure(s):
    s=unwrap(s)
    if not all(hasattr(s,k) for k in FIELDS):
        raise ValueError("missing fields "+str(getattr(s,"_fieldnames",[])))
    a={k:field(s,k) for k in FIELDS}
    n=len(a["Time"])
    if n<2 or any(len(v)!=n or not np.all(np.isfinite(v)) for v in a.values()):
        raise ValueError("nonfinite, misaligned or short recorded signals")
    t=a["Time"]; dt=np.diff(t)
    if (dt<0).any() or t[-1]<=t[0]:raise ValueError("nonmonotonic time")
    i=a["I_EL"]; charge=a["I_PS"]
    q=float(np.trapezoid(np.abs(i),t)/3600)
    q_signed=float(np.trapezoid(i,t)/3600)
    q2=math.fsum(float(x)*float(y+z)*0.5 for x,y,z in zip(dt,np.abs(i[:-1]),np.abs(i[1:])))/3600
    if not math.isclose(q,q2,rel_tol=1e-11,abs_tol=1e-11):raise ValueError("integration disagreement")
    if q<=0:raise ValueError("nonpositive discharge integral")
    laser=a["Las1"]+a["Las2"]
    derived=laser-laser[0]
    stored=a["Dthk"]-a["Dthk"][0]
    residual=stored-derived
    return {"samples":n,"duration_s":float(t[-1]-t[0]),"zero_time_intervals":int((dt==0).sum()),
      "max_time_gap_s":float(dt.max()),"capacity_abs_discharge_Ah":q,"capacity_signed_discharge_Ah":q_signed,
      "capacity_manual_Ah":q2,"charge_channel_abs_integral_Ah":float(np.trapezoid(np.abs(charge),t)/3600),
      "discharge_current_min_A":float(i.min()),"discharge_current_max_A":float(i.max()),
      "initial_voltage_V":float(a["V_batt"][0]),"final_voltage_V":float(a["V_batt"][-1]),
      "initial_laser_sum_V":float(laser[0]),"final_laser_sum_V":float(laser[-1]),
      "laser_range_mm":float(np.ptp(derived)),"stored_deformation_range_mm":float(np.ptp(stored)),
      "laser_endpoint_mm":float(derived[-1]),"stored_deformation_endpoint_mm":float(stored[-1]),
      "max_laser_identity_error_mm":float(np.max(np.abs(residual))),
      "rms_laser_identity_error_mm":float(np.sqrt(np.mean(residual**2))),
      "ambient_median_C":float(np.median(a["T_amb"])),
      "battery_median_C":float(np.median(a["T_batt"])),
      "capacity_numeric_integrators_agree":True}

def selftest():
    from types import SimpleNamespace
    s=SimpleNamespace(Time=np.array([0.,1800.,3600.]),I_EL=np.array([2.,2.,2.]),I_PS=np.zeros(3),
       V_batt=np.array([4.,3.8,3.]),T_batt=np.ones(3)*20,T_amb=np.ones(3)*20,
       Las1=np.array([2.,2.1,2.2]),Las2=np.array([3.,3.1,3.2]),Dthk=np.array([0.,.2,.4]))
    d=measure(s);assert math.isclose(d["capacity_abs_discharge_Ah"],2)
    assert math.isclose(d["laser_range_mm"],.4)
    assert d["max_laser_identity_error_mm"]<1e-12
    s.Dthk=np.array([0.,.2,.5]);assert measure(s)["max_laser_identity_error_mm"]>.09
    s.Time=np.array([0.,2.,1.])
    try:measure(s)
    except ValueError:pass
    else:raise AssertionError("reversed time accepted")
    print("SYNTHETIC_CHECK_PASS",flush=True)

def hashfile(p):
    m=hashlib.md5();h=hashlib.sha256();size=0
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            m.update(b);h.update(b);size+=len(b)
    return {"bytes":size,"md5":m.hexdigest(),"sha256":h.hexdigest()}

def main():
    selftest()
    out=pathlib.Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    p=pathlib.Path("/tmp/Aging_Dataset_Cycling.mat")
    if not p.exists():
        req=urllib.request.Request(URL,headers={"User-Agent":"CANO public scientific reproducibility audit"})
        with urllib.request.urlopen(req,timeout=90) as r,p.open("wb") as f:
            for b in iter(lambda:r.read(1024*1024),b""):f.write(b)
    identity=hashfile(p)
    print("ORIGINAL_SOURCE",identity,flush=True)
    if identity["md5"]!=MD5:raise ValueError("publisher MD5 mismatch")
    info=whosmat(p);print("MAT_SCHEMA",info,flush=True)
    (out/"source_schema.json").write_text(json.dumps({"doi":DOI,"file":identity,"mat_variables":info},indent=2))
    cand=[name for name,shape,kind in info if len(shape)==2 and shape[0]==2 and shape[1]>=6 and kind=="cell"]
    if len(cand)!=1:raise ValueError("ambiguous documented main MATLAB 2x6 cell "+str(cand))
    d=loadmat(p,variable_names=cand,struct_as_record=False,squeeze_me=False)[cand[0]]
    rows=[];excluded=[];stage=[]
    for rate,row in (("RPT-A-high",0),("RPT-B-low",1)):
        a=unwrap(d[row,0]);ages=vector(d[row,5])
        print("RPT_STRUCTURE",rate,a.shape,ages.shape,ages.tolist(),flush=True)
        if not isinstance(a,np.ndarray) or a.ndim!=2 or a.shape[0]!=len(ages) or not np.isfinite(ages).all():
            raise ValueError("discharge matrix does not match documented cycle-vector axis")
        if np.any(np.diff(ages)<=0):raise ValueError("nonunique or unordered stage labels")
        for j,age in enumerate(ages):
            group=[]
            for k in range(a.shape[1]):
                s=unwrap(a[j,k])
                if isinstance(s,np.ndarray) and s.size==0:
                    excluded.append({"rate":rate,"cycle":float(age),"repeat":k+1,"reason":"empty original repeat slot"})
                    continue
                try:r=measure(s)
                except ValueError as e:
                    excluded.append({"rate":rate,"cycle":float(age),"repeat":k+1,"reason":str(e)})
                    continue
                r.update(rate=rate,cycle=float(age),repeat=k+1)
                rows.append(r);group.append(r)
            if group:
                stage.append({"rate":rate,"cycle":float(age),"repeat_count":len(group),
                  **{key:float(np.median([r[key] for r in group])) for key in (
                    "capacity_abs_discharge_Ah","laser_range_mm","stored_deformation_range_mm",
                    "initial_laser_sum_V","initial_voltage_V","final_voltage_V","ambient_median_C",
                    "charge_channel_abs_integral_Ah")},
                  "capacity_repeat_min_Ah":min(r["capacity_abs_discharge_Ah"] for r in group),
                  "capacity_repeat_max_Ah":max(r["capacity_abs_discharge_Ah"] for r in group)})
    if not rows or len(stage)<5:raise ValueError("insufficient actual source discharge data")
    for rate in ("RPT-A-high","RPT-B-low"):
        g=[x for x in stage if x["rate"]==rate]
        if len(g)<2:raise ValueError("one of the documented rate groups lacks stages")
        base=g[0]
        for s in g:
            s["relative_capacity_to_first_stage_pct"]=100*s["capacity_abs_discharge_Ah"]/base["capacity_abs_discharge_Ah"]
            s["initial_laser_sum_change_from_first_stage_mm"]=s["initial_laser_sum_V"]-base["initial_laser_sum_V"]
    summaries={}
    for rate in ("RPT-A-high","RPT-B-low"):
        g=[x for x in stage if x["rate"]==rate]
        rr=[x for x in rows if x["rate"]==rate]
        def rho(x,y):
            z=float(spearmanr([s[x] for s in g],[s[y] for s in g]).statistic)
            return z if math.isfinite(z) else None
        summaries[rate]={"stages":len(g),"valid_discharge_runs":len(rr),"samples":sum(x["samples"] for x in rr),
            "first":g[0],"last":g[-1],
            "rho_capacity_vs_laser_range_descriptive":rho("capacity_abs_discharge_Ah","laser_range_mm"),
            "rho_capacity_vs_stage_descriptive":rho("capacity_abs_discharge_Ah","cycle"),
            "rho_capacity_vs_initial_laser_sum_descriptive":rho("capacity_abs_discharge_Ah","initial_laser_sum_V"),
            "max_laser_identity_error_mm":max(x["max_laser_identity_error_mm"] for x in rr),
            "runs_laser_identity_within_1um":sum(x["max_laser_identity_error_mm"]<=.001 for x in rr),
            "runs_charge_channel_over_0p01Ah":sum(x["charge_channel_abs_integral_Ah"]>.01 for x in rr)}
    receipt={"goal":"lco-20261124-native-units-capacity-laser-identity","source_doi":DOI,
      "original":identity,"publisher_md5_match":True,"mat_variable":cand[0],
      "physical_cells":1,"data":"published RPT discharge tests only",
      "capacity_method":"absolute I_EL trapezoid with source seconds /3600; compare independently with math.fsum",
      "laser_method":"publisher 1 V per mm; sum of Las1+Las2 relative to segment first sample; compare with Dthk similarly centered",
      "stage_median_not_independent_cells":True,"full_physical_calibration_certificate_verified":False,
      "causal_or_population_claim":False,"production_release":False,
      "summary":summaries,"excluded_slots":excluded,"valid_discharge_runs":len(rows),
      "total_valid_samples":sum(x["samples"] for x in rows)}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2,allow_nan=False))
    for n,ar in (("discharge_runs.csv",rows),("stage_medians.csv",stage)):
        with (out/n).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(ar[0]));w.writeheader();w.writerows(ar)
    print("REAL_LCO_SOURCE_RESULT",json.dumps(receipt,allow_nan=False),flush=True)

if __name__=="__main__":main()
