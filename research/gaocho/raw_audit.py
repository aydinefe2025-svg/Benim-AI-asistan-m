#!/usr/bin/env python3
"""Gao-Cho Zenodo 10065172: source integrity + run-level holdout audit.
No production changes; not an independent laboratory replication.
"""
import csv, hashlib, io, json, math, re, statistics, sys, time, urllib.request, zipfile
from pathlib import Path

OUT = Path("research/gaocho/out")
OUT.mkdir(parents=True, exist_ok=True)
EXPECTED_MD5 = "d6c110ed103f4f4536cba83a49cc5576"
URLS = [
    "https://zenodo.org/records/10065172/files/AtmosphericCaptureData.zip?download=1",
    "https://zenodo.org/api/records/10065172/files/AtmosphericCaptureData.zip/content",
]
provenance = {"record": "10.5281/zenodo.10065172", "urls_tried": [],
              "raw_reanalysis_status": "NOT_RUN", "source_md5_verified": False}
def save(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
def emit(text):
    print(text, flush=True)

payload = None
for url in URLS:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CANO-scientific-audit/1.0 (academic replication)", "Accept": "application/zip,*/*"})
        with urllib.request.urlopen(req, timeout=65) as res:
            data = res.read(25_000_000)
            code = res.status
            length = len(data)
        record = {"url": url, "http_status": code, "bytes": length}
        provenance["urls_tried"].append(record)
        if len(data) > 20_000_000:
            raise ValueError("unexpected archive size; capped download")
        md5 = hashlib.md5(data).hexdigest()
        record["md5"] = md5
        if md5 != EXPECTED_MD5:
            raise ValueError(f"MD5 mismatch expected={EXPECTED_MD5} actual={md5}")
        payload = data
        provenance.update(source_md5_verified=True, source_sha256=hashlib.sha256(data).hexdigest(), source_bytes=len(data))
        break
    except Exception as exc:
        provenance["urls_tried"].append({"url": url, "error": str(exc)[:400]})
if payload is None:
    provenance["raw_reanalysis_status"] = "DOWNLOAD_FAILED"
    save("source_provenance.json", provenance)
    emit("NOT_RUN: Source ZIP inaccessible or integrity mismatch")
    sys.exit(2)

def wind_from_path(path):
    m = re.search(r"(?<!\d)(0\.\d+|[1-5]\.\d+)\s*(?:m/?s|mps|m_s|m per second)(?![a-z])", path, flags=re.I)
    return float(m.group(1)) if m else None

def slope_and_r2(x, y):
    n = len(x)
    mx, my = statistics.fmean(x), statistics.fmean(y)
    xx = sum((v-mx)**2 for v in x)
    if n < 4 or xx == 0: return None, None
    s = sum((a-mx)*(b-my) for a,b in zip(x,y))/xx
    ss = sum((v-my)**2 for v in y)
    r2 = 1-sum((b-(my+s*(a-mx)))**2 for a,b in zip(x,y))/ss if ss > 0 else None
    return s, r2

def parse_tsv(zf, member):
    member = member.filename if hasattr(member, 'filename') else member
    sample = []
    rows = []
    examples = []
    skipped = 0
    with zf.open(member) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace"), delimiter="\t")
        for line in reader:
            if len(examples) < 3:
                examples.append(line[:12])
            if len(line) < 7:
                skipped += 1
                continue
            try:
                vals = [float(v.replace(",", ".")) for v in line[:7]]
                if not all(math.isfinite(v) for v in vals): raise ValueError()
                # time(s), tunnel T, tunnel RH, setpoint RH, chamber T, chamber RH, volume(mL)
                t, ta, rh, rhsp, tc, rhc, volume = vals
                if not (0 <= rh <= 100 and 0 <= rhc <= 100 and -30 <= ta <= 80 and -30 <= tc <= 90):
                    skipped += 1
                    continue
                rows.append(vals)
            except (ValueError, OverflowError):
                skipped += 1
    rec = {"member": member, "numeric_rows": len(rows), "skipped_rows": skipped,
           "first_lines": examples, "wind_m_s_from_filename": wind_from_path(member)}
    if len(rows) < 20:
        rec["status"] = "INSUFFICIENT_NUMERIC_ROWS"
        return rec
    rows.sort(key=lambda z:z[0])
    tmin,tmax=rows[0][0],rows[-1][0]
    duration=tmax-tmin
    rec.update(duration_s=duration, volume_first_ml=rows[0][6],
               volume_last_ml=rows[-1][6], monotonic_volume_decreases=sum(rows[i][6]<rows[i-1][6] for i in range(1,len(rows))),
               rh_air_median=statistics.median(r[2] for r in rows),
               rh_chamber_median=statistics.median(r[5] for r in rows),
               rh_setpoint_median=statistics.median(r[3] for r in rows),
               delta_rh_mean=statistics.fmean(r[2]-r[5] for r in rows))
    if duration < 120:
        rec["status"]="SHORT_DURATION"
        return rec
    # Middle 80% timestamp span. Pre-specified to limit startup/end effects.
    middle=[r for r in rows if tmin+0.1*duration <= r[0] <= tmax-0.1*duration]
    slope,r2=slope_and_r2([r[0] for r in middle],[r[6] for r in middle])
    rec.update(central_n=len(middle),slope_r2=r2,ml_per_hr=slope*3600 if slope is not None else None,
               central_delta_rh=statistics.fmean(r[2]-r[5] for r in middle) if middle else None,
               central_temp_air_c=statistics.fmean(r[1] for r in middle) if middle else None,
               central_temp_chamber_c=statistics.fmean(r[4] for r in middle) if middle else None)
    rec["status"]="PARSED" if slope is not None else "FIT_FAILED"
    return rec

inventory=[]
results=[]
with zipfile.ZipFile(io.BytesIO(payload)) as zf:
    bad=zf.testzip()
    provenance.update(zip_crc_ok=(bad is None), zip_member_count=len(zf.infolist()))
    if bad is not None:
        provenance["raw_reanalysis_status"]="ZIP_CRC_FAILED"
        save("source_provenance.json", provenance)
        sys.exit(3)
    for m in zf.infolist():
        inventory.append({"name":m.filename,"bytes_uncompressed":m.file_size,"bytes_compressed":m.compress_size})
        if not m.is_dir() and m.filename.lower().endswith((".tsv", ".txt")) and m.file_size < 100_000_000:
            try: results.append(parse_tsv(zf,m))
            except Exception as exc: results.append({"member":m.filename,"status":"PARSE_EXCEPTION","error":str(exc)[:400]})
save("source_inventory.json",inventory)
save("run_statistics.json",results)
provenance["parsed_records"]=len(results)

# Group by entire file/run, not individual time rows. Train/test predetermined
# from alphabetical ordering, every third *eligible* run as blind holdout.
eligible = sorted((r for r in results if r.get("status")=="PARSED"
                   and r.get("wind_m_s_from_filename") and r.get("ml_per_hr") is not None
                   and r.get("central_delta_rh",0)>0),key=lambda r:r["member"])
audit = {"status":"NOT_RUN","train_files":[],"test_files":[],"formula":"q_ml_h=K * (RH_air-RH_chamber) * sqrt(U_m_s)",
         "unit_note":"empirical RH-percent model; not the PNAS physical mass-transfer model; within-source holdout is G2, not G3"}
if len(eligible)>=6:
    train=[r for i,r in enumerate(eligible) if i%3 != 2]
    test=[r for i,r in enumerate(eligible) if i%3 == 2]
    def x(r):return r["central_delta_rh"]*math.sqrt(r["wind_m_s_from_filename"])
    xt=[x(r) for r in train]
    yt=[r["ml_per_hr"] for r in train]
    k=sum(a*b for a,b in zip(xt,yt))/sum(a*a for a in xt)
    baseline=statistics.fmean(yt)
    cases=[{"member":r["member"],"actual_ml_h":r["ml_per_hr"],
            "predicted_ml_h":k*x(r),"naive_prediction_ml_h":baseline} for r in test]
    def metrics(pred_key):
        err=[c[pred_key]-c["actual_ml_h"] for c in cases]
        return {"mae_ml_h":statistics.fmean(abs(e) for e in err),
                "rmse_ml_h":math.sqrt(statistics.fmean(e*e for e in err)),
                "bias_ml_h":statistics.fmean(err)}
    audit.update(status="RUN",training_K=k,train_files=[r["member"] for r in train],
                 test_files=[r["member"] for r in test],test_cases=cases,
                 model=metrics("predicted_ml_h"),null_mean_baseline=metrics("naive_prediction_ml_h"))
else:
    audit["why_not_run"]=f"Only {len(eligible)} runs have valid time series, velocity metadata and positive RH gradient; no inferred speeds"
provenance["raw_reanalysis_status"] = "RUN_LEVEL_HOLDOUT" if audit["status"]=="RUN" else "RAW_INSPECTED_HOLDOUT_NOT_RUN"
save("holdout_metrics.json",audit)
save("source_provenance.json",provenance)
lines=["# Gao–Cho source audit — measured data, not external validation",
       f"- ZIP MD5 match: {provenance['source_md5_verified']}",
       f"- ZIP SHA256: {provenance['source_sha256']}",
       f"- ZIP entries: {len(inventory)}; logs parsed: {len(results)}",
       f"- Source run-level audit: {audit['status']}; G3 independent-laboratory: NOT_DONE",
       f"- Details: source_provenance.json / source_inventory.json / run_statistics.json / holdout_metrics.json"]
(OUT/"REPORT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
emit("\n".join(lines))
