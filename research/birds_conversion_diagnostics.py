import collections,hashlib,json,math,pathlib,statistics
from birds_raw_conversion_audit import load,rawcode,CHANNELS
rows,meta,clocks=load()
assert len(rows)==31725
d=json.loads(pathlib.Path("BIRDS_RAW_CONVERSION_RECEIPT.json").read_text())
total=passed=excluded=0;bad=[]
for k,c in d["channels"].items():
    for sat,x in c["heldout"].items():
        total+=x["n"];excluded+=x["excluded_raw"];passed+=x["n"]-x["abs_error_gt_0p02"]
    bad.extend([dict(channel=k,**r) for r in c["top_residuals"]])
assert total+excluded==30630*12 and total-passed==1
raw_exclusions=collections.Counter();examples={}
for sat,sheet,n,v in rows:
    if sat=="TSURU" and sheet=="March 28":continue
    for name,(a,b,width,tol) in CHANNELS.items():
        if rawcode(v.get(a),width) is None:
            raw_exclusions[(sat,name)]+=1
            if (sat,name) not in examples:examples[(sat,name)]={"sheet":sheet,"row":n,"raw_repr":repr(v.get(a)),"engineering":v.get(b)}
target=[{"row":n,"time_A_s":v["A"],"raw_battery_current":v.get("AH"),"battery_current_mA":v.get("AI"),"raw_battery_voltage":v.get("AF"),"battery_voltage_V":v.get("AG"),"raw_panel_Y_voltage":v.get("L"),"panel_Y_voltage_mV":v.get("M"),"raw_panel_Y_current":v.get("V"),"panel_Y_current_mA":v.get("W")} for sat,sheet,n,v in rows if sat=="UGUISU" and sheet=="13 Feb 2021" and 1071<=n<=1075]
assert any(x["row"]==1073 and x["raw_battery_current"]=="0000" and x["battery_current_mA"]==0 for x in target)
# Full gap distributions, no top-five truncation. Retain source row adjacency.
times=collections.defaultdict(list)
for sat,sheet,n,v in rows:times[sat,sheet].append((n,v["A"]))
gaps={}
for (sat,sheet),a in times.items():
    gaps.setdefault(sat,collections.Counter()).update(round(b[1]-x[1],6) for x,b in zip(a,a[1:]) if b[0]==x[0]+1)
# Compare the same raw-code rule for panel low voltage, no battery current involved.
panels=[("L","M"),("N","O"),("P","Q"),("R","S"),("T","U")]
pstats={}
for sat in meta:
    ss=[r for r in rows if r[0]==sat]
    by=[]
    for a,b in panels:
        q=[(rawcode(v.get(a),4),v[b]) for _,_,_,v in ss]
        q=[(x,y) for x,y in q if x is not None]
        disagree=sum((x*6250/4095<1200)!=(y<1200) for x,y in q)
        by.append({"raw_column":a,"engineering_column":b,"n":len(q),"raw_low_voltage_count":sum(x*6250/4095<1200 for x,y in q),"engineering_low_voltage_count":sum(y<1200 for x,y in q),"disagreements":disagree})
    pstats[sat]=by
out={"status":"BIRDS_HELDOUT_RAW_CONVERSION_AND_CLOCK_DIAGNOSTICS","training_rows":1095,"heldout_rows":30630,"tested_channel_pairs":total,"passed_0p02_units":passed,"excluded_raw_representation":excluded,"anomaly":bad,"neighboring_records":target,"raw_exclusions":[{"satellite":k[0],"channel":k[1],"count":v,"example":examples[k]} for k,v in raw_exclusions.items()],"timestamp_gaps":{s:dict(sorted(c.items())) for s,c in gaps.items()},"raw_voltage_threshold_crosscheck":pstats,"source":meta,"source_receipt_sha256":hashlib.sha256(pathlib.Path("BIRDS_RAW_CONVERSION_RECEIPT.json").read_bytes()).hexdigest(),"limits":"0.02 engineering units is numerical tolerance only. 0000 may represent missing/reset/sentinel, no imputation. Raw voltage formula inferred by fit and checked independently of converted threshold. Timestamp seconds as documented, not independently calibrated, no absolute UTC. Physical calibration and fault cause remain unresolved."}
p=pathlib.Path("BIRDS_CONVERSION_DIAGNOSTIC_SUMMARY.json");p.write_text(json.dumps(out,indent=2,allow_nan=False),encoding="utf-8");print(json.dumps(out,ensure_ascii=True));print("SUMMARY_SHA256="+hashlib.sha256(p.read_bytes()).hexdigest())
