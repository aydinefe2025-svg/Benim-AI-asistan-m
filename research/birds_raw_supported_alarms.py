import hashlib,json,pathlib,collections,math
from birds_raw_conversion_audit import load,rawcode,CHANNELS
from birds_published_panel_rules import panel_flags
rows,meta,_=load()
fits=json.loads(pathlib.Path("BIRDS_RAW_CONVERSION_RECEIPT.json").read_text())["channels"]
by=collections.defaultdict(list)
for sat,sheet,n,v in rows:by[sat,sheet].append({"row":n,"t":v["A"],"vals":v})
result={}
for sat in meta:
    per={k:0 for k in ("original_type1","original_type2","raw_qualified_type1","raw_qualified_type2","raw_complete_rows","raw_incomplete_rows","original_on_raw_qualified_type1","original_on_raw_qualified_type2","raw_rule_disagreements_type1","raw_rule_disagreements_type2")}
    excluded=[];ts=[]
    for (s,sh),series in by.items():
        if s!=sat:continue
        original,_=panel_flags(series,100)
        good=[];converted=[]
        for r in series:
            vals=r["vals"];p={};missing=[]
            for name,(a,b,w,_) in CHANNELS.items():
                if name in ("Vbat","Ibatt"):continue
                x=rawcode(vals.get(a),w)
                if x is None:missing.append(name);continue
                f=fits[name];p[b]=f["slope"]*x+f["intercept"]
            if missing:
                excluded.append({"sheet":sh,"row":r["row"],"time_A_s":r["t"],"missing_panel_channels":missing,"original_type1":r["row"] in original["type1"],"original_type2":r["row"] in original["type2"]})
                continue
            good.append(r);converted.append({"row":r["row"],"t":r["t"],"vals":p})
        of,_=panel_flags(good,100);nf,_=panel_flags(converted,100)
        per["raw_complete_rows"]+=len(good);per["raw_incomplete_rows"]+=len(series)-len(good)
        for k in ("type1","type2"):
            per["original_"+k]+=len(original[k]);per["original_on_raw_qualified_"+k]+=len(of[k]);per["raw_qualified_"+k]+=len(nf[k]);per["raw_rule_disagreements_"+k]+=len(of[k]^nf[k])
            if of[k]^nf[k]:ts.extend({"sheet":sh,"row":n,"rule":k} for n in sorted(of[k]^nf[k]))
    per["excluded_rows"]=excluded;per["classification_differences"]=ts
    result[sat]=per
assert sum(x["raw_complete_rows"]+x["raw_incomplete_rows"] for x in result.values())==31725
assert sum(x["raw_rule_disagreements_type1"]+x["raw_rule_disagreements_type2"] for x in result.values())==0
out={"status":"BIRDS_RAW_SUPPORTED_ALARM_RESCREEN","results":result,"fit_reference_sha256":hashlib.sha256(pathlib.Path("BIRDS_RAW_CONVERSION_RECEIPT.json").read_bytes()).hexdigest(),"limits":"Require all ten raw panel channels present, preserve source row adjacency. Fitted raw conversion is derived from published TSURU values, not a separately calibrated instrument. Exclusion is not proof of no physical failure. Type 2 remains an observational screen."}
p=pathlib.Path("BIRDS_RAW_SUPPORTED_ALARM_RECEIPT.json");p.write_text(json.dumps(out,indent=2,allow_nan=False),encoding="utf-8");print(json.dumps(out));print("ALARM_RECEIPT_SHA256="+hashlib.sha256(p.read_bytes()).hexdigest())
