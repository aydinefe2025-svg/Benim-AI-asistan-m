"""Source-native measured terminal-voltage cutoff sensitivity (not impact data)."""
import csv, hashlib, io, json, math, sys, zipfile
from pathlib import Path
from research.battery_curve_audit import bayreuth_two_cell_independent_integral as core

CUTS=(3.5,3.4,3.3,3.2,3.1,3.0,2.9,2.8,2.7,2.6,2.5)

def crossing(rows, threshold):
    """First observed falling crossing. No extrapolation. Time is hours."""
    if len(rows)<2 or rows[0]["v"]<=threshold:
        return None
    q=0.0
    for a,b in zip(rows,rows[1:]):
        dt=b["time_h"]-a["time_h"]
        ia,ib=-a["i"],-b["i"]
        if dt<=0 or min(ia,ib)<0:
            raise ValueError("non-discharge or non-monotone time")
        dq=dt*(ia+ib)/2
        if a["v"]>threshold>=b["v"]:
            f=(a["v"]-threshold)/(a["v"]-b["v"])
            qx=q+dt*f*(ia+ia+(ib-ia)*f)/2
            return {"integral_mAh":1000*qx,"bracket_low_mAh":1000*q,"bracket_high_mAh":1000*(q+dq),
                    "native_increment_mAh":1000*(-(a["ah"]+(b["ah"]-a["ah"])*f-rows[0]["ah"])),
                    "sample_interval_s":dt*3600}
        q+=dq
    return None

def segments(arc, name):
    current=[]
    for r in core.native_rows(arc,name):
        if r["cmd"]!="discharge" or r["i"]>0:
            if current:
                yield current
                current=[]
            continue
        if current:
            p=current[-1]
            if (r["line"],r["cycle"])!=(p["line"],p["cycle"]) or r["time_h"]<=p["time_h"] or r["step_h"]<p["step_h"]-1e-8:
                yield current
                current=[]
        current.append(r)
    if current:
        yield current

def select(arc,name):
    # Select largest observed contiguous discharge throughput, constrained to
    # broad voltage coverage; no cross-stage protocol equivalence assumption.
    eligible=[]
    for rows in segments(arc,name):
        if len(rows)>=20 and rows[0]["v"]>=3.7 and rows[-1]["v"]<=3.1 and rows[-1]["time_h"]-rows[0]["time_h"]<5:
            q=-(rows[-1]["ah"]-rows[0]["ah"])
            if q>=0.03:  # same minimum measured throughput as original core pairing guard
                eligible.append((q,rows))
    if not eligible:
        return None
    return max(eligible,key=lambda x:x[0])[1]

def audit(out):
    out.mkdir(parents=True,exist_ok=True)
    result={"goal":"bayreuth-20261124-measured-terminal-cutoff-v1","source_doi":core.RECORD_DOI,
            "source_license":"CC BY 4.0","cells":{},"not_OCV":True,"not_impact":True,
            "not_module_measurement":True,"not_calibration":True}
    for cell,spec in core.SOURCE_FILES.items():
        blob=core.fetch_publisher(cell)
        cell_out={"bytes":len(blob),"md5":hashlib.md5(blob).hexdigest(),"sha256":hashlib.sha256(blob).hexdigest(),"stages":{}}
        with zipfile.ZipFile(io.BytesIO(blob)) as arc:
            for stage,suffix in (("beginning","m0001_checkup.txt"),("ending","m0003_checkup.txt")):
                name,=[n for n in arc.namelist() if n.lower().endswith(suffix)]
                rows=select(arc,name)
                if rows is None:
                    cell_out["stages"][stage]={"eligible":False}
                    continue
                fname=f"{cell}_{stage}_source_segment.csv"
                with (out/fname).open("w",newline="",encoding="utf8") as f:
                    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
                cuts={str(v):crossing(rows,v) for v in CUTS}
                valid=[x["integral_mAh"] for x in cuts.values() if x is not None]
                assert all(b>=a-1e-8 for a,b in zip(valid,valid[1:]))
                stage_out={"eligible":True,"member":name,"line":rows[0]["line"],"cycle":rows[0]["cycle"],
                           "rows":len(rows),"start_V":rows[0]["v"],"end_V":rows[-1]["v"],
                           "first_last_h":rows[-1]["time_h"]-rows[0]["time_h"],"cutoffs":cuts,
                           "segment_csv":fname,"segment_sha256":hashlib.sha256((out/fname).read_bytes()).hexdigest()}
                if cuts["3.3"] is not None and cuts["3.1"] is not None:
                    a,b=cuts["3.3"],cuts["3.1"]
                    stage_out["extra_mAh_3p3_to_3p1"]=b["integral_mAh"]-a["integral_mAh"]
                    stage_out["extra_mAh_observed_bracket"]=[max(0,b["bracket_low_mAh"]-a["bracket_high_mAh"]),b["bracket_high_mAh"]-a["bracket_low_mAh"]]
                cell_out["stages"][stage]=stage_out
        result["cells"][cell]=cell_out
    n=sum(s["eligible"] for c in result["cells"].values() for s in c["stages"].values())
    result["eligible_segments"]=n
    assert n>0, "no qualifying measured segments; no result"
    (out/"cutoff_result.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps(result,allow_nan=False))

if __name__=="__main__":
    audit(Path(sys.argv[1]))
