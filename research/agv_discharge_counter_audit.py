"""AGV original publisher counter/units audit; no inferred capacity labels."""
import csv, hashlib, io, json, statistics, collections, pathlib, urllib.request, math
BASE="https://zenodo.org/api/records/7748947/files/"
PIN={"dataset.csv":"2faa82bd0c27763d4b12d4c58510a1f5","README.adoc":"040c1cef4cb20fed5105144e417b451b"}
def fetch(name):
    errors=[]
    for url in [BASE+name+"/content","https://zenodo.org/records/7748947/files/"+name+"?download=1"]:
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"AGV-source-replay/1.0"}),timeout=90) as f: raw=f.read()
            if hashlib.md5(raw).hexdigest()!=PIN[name]:raise ValueError("publisher MD5 mismatch")
            return raw
        except Exception as e:errors.append(str(e))
    raise ValueError("source verification failed: "+name+" "+str(errors))
def summarize(values):
    if not values:return None
    return {"n":len(values),"min":min(values),"median":statistics.median(values),"max":max(values)}
def correlation(x,y):
    if len(x)<2 or min(x)==max(x) or min(y)==max(y):return None
    return round(statistics.correlation(x,y),8)
def inspect(rows):
    packs=collections.defaultdict(list)
    for row in rows:
        packs[row["battery"]].append((int(row["counter"]),row["date"],int(row["cycletime"]),int(row["totaldischarge"])))
    results={}
    for name,items in sorted(packs.items()):
        by_counter=sorted(items)
        c=collections.Counter(x[0] for x in items)
        diffs=[b[3]-a[3] for a,b in zip(by_counter,by_counter[1:]) if b[0]==a[0]+1]
        gap_count=sum(b[0]>a[0]+1 for a,b in zip(by_counter,by_counter[1:]))
        dts=[b[3]-a[3] for a,b in zip(items,items[1:])]
        x=[a[2] for a in items];y=[a[3] for a in items]
        results[name]={"rows":len(items),"counter_distinct":len(c),"counter_duplicate_rows":sum(n-1 for n in c.values()),"counter_gap_pairs":gap_count,
          "source_order_counter_decreases":sum(b[0]<a[0] for a,b in zip(items,items[1:])),
          "source_order_dates_decrease":sum(b[1]<a[1] for a,b in zip(items,items[1:])),
          "duration_seconds":summarize(x),"totaldischarge_field":summarize(y),
          "zero_duration_count":sum(v==0 for v in x),"zero_discharge_count":sum(v==0 for v in y),
          "adjacent_counter_totaldischarge_decreases":sum(v<0 for v in diffs),
          "adjacent_counter_totaldischarge_increases":sum(v>0 for v in diffs),
          "adjacent_counter_totaldischarge_equal":sum(v==0 for v in diffs),
          "adjacent_counter_totaldischarge_delta":summarize(diffs),
          "source_order_totaldischarge_decreases":sum(v<0 for v in dts),
          "duration_vs_raw_totaldischarge_pearson":correlation(x,y),
          "equal_duration_different_discharge":None}
        # A direct observed counterexample. Distinct records, same duration, different raw field.
        times=collections.defaultdict(list)
        for a in items:
            if a[2]>0:times[a[2]].append(a)
        best=None
        for t,g in times.items():
            lo=min(g,key=lambda a:a[3]);hi=max(g,key=lambda a:a[3])
            if lo[3]!=hi[3] and (best is None or hi[3]-lo[3]>best["raw_difference"]):
                best={"seconds":t,"raw_difference":hi[3]-lo[3],"records":[list(lo),list(hi)]}
        results[name]["equal_duration_different_discharge"]=best
    return results
def main():
    # Known cumulative vs per-event examples keep counter interpretation separate.
    fixture=[{"battery":"X","counter":"1","date":"2020-01-01","cycletime":"10","totaldischarge":"20"},{"battery":"X","counter":"2","date":"2020-01-01","cycletime":"10","totaldischarge":"10"}]
    f=inspect(fixture)["X"]
    assert f["adjacent_counter_totaldischarge_decreases"]==1 and f["equal_duration_different_discharge"]["raw_difference"]==10
    raw=fetch("dataset.csv");doc=fetch("README.adoc")
    rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert len(rows)==57880
    assert tuple(rows[0])==("counter","date","cycletime","totaldischarge","mintemperature","maxtemperature","battery")
    result=inspect(rows)
    assert len(result)==10
    out={"status":"ORIGINAL_AGV_COUNTER_AND_MEASUREMENT_CONTRACT_AUDIT","source_md5":PIN,
         "csv_sha256":hashlib.sha256(raw).hexdigest(),"readme_sha256":hashlib.sha256(doc).hexdigest(),
         "readme_text":doc.decode("utf-8"),"source_rows":len(rows),"packs":result,
         "limitations":"Raw field meaning must follow original README; do not infer Ah, SoH or capacity from integer values without verified units and SoC window. Counter comparisons are observed not causal."}
    pathlib.Path("AGV_COUNTER_SOURCE_RECEIPT.json").write_text(json.dumps(out,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps(out,indent=2))
if __name__=="__main__":main()
