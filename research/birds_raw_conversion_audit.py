import base64,collections,hashlib,json,math,pathlib,posixpath,re,statistics,zipfile
import xml.etree.ElementTree as ET
import numpy as np
from birds_eps_constellation_qc import NS,REL,SOURCES,colname,decode_cell,shared_strings,FIELDS_TSURU_14
from tsuru_agv_real_source_ci import GIT_SHA
PINS={"TSURU":{"sha1":GIT_SHA,"bytes":6059029},**SOURCES}
CHANNELS={"Vpy":("L","M",4,0.0051),"Vpx":("N","O",4,0.0051),"Vmz":("P","Q",4,0.0051),"Vmx":("R","S",4,0.0051),"Vpz":("T","U",4,0.0051),"Ipy":("V","W",2,0.0051),"Ipx":("X","Y",2,0.0051),"Imz":("Z","AA",2,0.0051),"Imx":("AB","AC",2,0.0051),"Ipz":("AD","AE",2,0.0051),"Vbat":("AF","AG",2,0.0051),"Ibatt":("AH","AI",4,0.0051)}
def rawcode(v,width):
    # Do not silently interpret numeric Excel cells as hexadecimal text.
    if isinstance(v,str) and re.fullmatch("[0-9A-Fa-f]{"+str(width)+"}",v.strip()):return int(v,16)
    return None
def load():
    rows=[];meta={};clocks={}
    for sat,pin in PINS.items():
        raw=pathlib.Path(sat+"_original.xlsx").read_bytes()
        if len(raw)!=pin["bytes"] or hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()!=pin["sha1"]:raise ValueError("source identity")
        meta[sat]={"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}
        with zipfile.ZipFile(pathlib.Path(sat+"_original.xlsx")) as z:
            if z.testzip() is not None:raise ValueError("CRC")
            ss=shared_strings(z);sh=ET.fromstring(z.read("xl/workbook.xml")).findall(NS+"sheets/"+NS+"sheet")
            links={e.get("Id"):e.get("Target") for e in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
            clocks[sat]={}
            for s in sh:
                name=s.get("name");target=links[s.get(REL+"id")]
                path=target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl",target))
                x=ET.fromstring(z.read(path)).findall(NS+"sheetData/"+NS+"row")
                prefix=True;last=None;accepted=[];test=sat=="TSURU" and name.startswith(("Test1","Test2"))
                for rr in x[1:]:
                    vals={colname(c.get("r")):decode_cell(c,ss) for c in rr.findall(NS+"c")}
                    complete=all(isinstance(vals.get(k),float) and math.isfinite(vals[k]) for k in FIELDS_TSURU_14)
                    if test:continue
                    if sat=="TSURU":
                        prefix=prefix and complete and (last is None or vals["A"]>last)
                        if not prefix:continue
                    elif not complete:continue
                    if not complete:continue
                    n=int(rr.get("r"));last=vals["A"];accepted.append((n,last))
                    rows.append((sat,name,n,vals))
                diffs=[round(b[1]-a[1],6) for a,b in zip(accepted,accepted[1:]) if b[0]==a[0]+1]
                clocks[sat][name]={"n":len(diffs),"top_gaps":collections.Counter(diffs).most_common(5)}
    return rows,meta,clocks
def audit(rows):
    # Fit on first TSURU sheet only; test elsewhere, do not select by test residual.
    train=[r for r in rows if r[0]=="TSURU" and r[1]=="March 28"];test=[r for r in rows if not(r[0]=="TSURU" and r[1]=="March 28")]
    report={}
    for label,(a,b,width,tol) in CHANNELS.items():
        pairs=[(rawcode(r[3].get(a),width),r[3].get(b)) for r in train]
        pairs=[(x,y) for x,y in pairs if x is not None and isinstance(y,float)]
        if len(set(x for x,y in pairs))<2:raise ValueError("insufficient training codes "+label)
        # Robust seed from medians for each distinct code; iteratively reject outliers
        groups=collections.defaultdict(list)
        for x,y in pairs:groups[x].append(y)
        x=np.array(sorted(groups),float);y=np.array([statistics.median(groups[v]) for v in x])
        ok=np.ones(len(x),bool)
        for _ in range(4):
            slope,intercept=np.linalg.lstsq(np.c_[x[ok],np.ones(ok.sum())],y[ok],rcond=None)[0]
            err=np.abs(y-(slope*x+intercept))
            med=float(np.median(err))
            nxt=err<=max(0.02,med*5)
            if nxt.sum()<2 or np.array_equal(ok,nxt):break
            ok=nxt
        # engineering rounding tolerance: 0.01 unit plus small fitted-slope uncertainty
        satstats={};examples=[]
        for sat in PINS:
            data=[r for r in test if r[0]==sat];err=[];bad=0;invalid=0
            code_values=collections.defaultdict(set)
            for _,sheet,n,v in data:
                code=rawcode(v.get(a),width);meas=v.get(b)
                if code is None or not isinstance(meas,float):invalid+=1;continue
                code_values[code].add(meas)
                pred=float(slope*code+intercept);e=abs(meas-pred);err.append(e)
                if e>0.02:
                    bad+=1
                    examples.append({"satellite":sat,"sheet":sheet,"row":n,"hex":v[a],"published":meas,"predicted":pred,"abs_error":e})
            satstats[sat]={"n":len(err),"excluded_raw":invalid,"abs_error_gt_0p02":bad,"median_abs":statistics.median(err) if err else None,"p99_abs":float(np.percentile(err,99)) if err else None,"max_abs":max(err) if err else None,"same_code_multiple_published_values":sum(len(v)>1 for v in code_values.values())}
        report[label]={"slope":float(slope),"intercept":float(intercept),"training_pairs":len(pairs),"training_unique_codes":len(groups),"training_inlier_codes":int(ok.sum()),"heldout":satstats,"top_residuals":sorted(examples,key=lambda r:r["abs_error"],reverse=True)[:5]}
    return {"training_rows":len(train),"heldout_rows":len(test),"channels":report}
def main():
    rows,meta,clocks=load()
    assert len(rows)==31725
    result=audit(rows);result.update(status="BIRDS_RAW_HEX_TO_ENGINEERING_HELDOUT_CONVERSION_AUDIT",source=meta,clock_native_seconds=clocks,limits="Affine fit from TSURU March 28 only, engineering-field consistency, not independent physical calibration. Strict fixed-width hexadecimal text. Time gaps in published seconds, not absolute UTC. 0.02 unit tolerance is analyst-chosen, not sensor accuracy.")
    p=pathlib.Path("BIRDS_RAW_CONVERSION_RECEIPT.json");p.write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"train":result["training_rows"],"test":result["heldout_rows"],"channels":result["channels"],"gap_distribution":{s:dict(collections.Counter({str(g):sum(dict(x["top_gaps"]).get(g,0) for x in v.values()) for g in set(g for x in v.values() for g,n in x["top_gaps"])}).most_common(5)) for s,v in clocks.items()},"receipt_sha256":hashlib.sha256(p.read_bytes()).hexdigest()},ensure_ascii=True))
if __name__=="__main__":main()
