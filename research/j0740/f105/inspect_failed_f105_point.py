#!/usr/bin/env python3
"""Read-only diagnosis of the retained F105 index-1 raw C journal."""
import argparse, hashlib, json, zipfile
from pathlib import Path

ARTIFACT_SHA="c6d2de2ad7ade68a87e2efd9ff79300faf55d8745a4e2b62abb22ce3216b5de0"
RESULT="F105/F105_401x801_LOCAL_PEAK.json"
JOURNAL="F105/F105_401x801_LOCAL_PEAK.jsonl"
p=argparse.ArgumentParser()
p.add_argument("--artifact",type=Path,required=True)
a=p.parse_args()
raw=a.artifact.read_bytes()
assert hashlib.sha256(raw).hexdigest()==ARTIFACT_SHA,"F105_ARTIFACT_SHA_MISMATCH"
with zipfile.ZipFile(a.artifact) as z:
    result=json.loads(z.read(RESULT))
    journal_bytes=z.read(JOURNAL)
assert hashlib.sha256(journal_bytes).hexdigest()==result["journal_sha256"],"F105_JOURNAL_SHA_MISMATCH"
rows=[json.loads(line) for line in journal_bytes.decode().splitlines()]
idx=[r for r in rows if r["index"]==1]
print("F105_ARTIFACT_STATUS",result["status"])
print("F105_RAW_JOURNAL_ROWS",len(rows))
print("F105_INDEX1_ROWS",len(idx))
print("F105_INDEX1_JSONL")
for row in idx:
    print(json.dumps({k:row[k] for k in ("r_ratio","J_relative_error","M_msun","J_cgs","R_eq_km","f_hz")},sort_keys=True))
if idx:
    ordered=sorted(idx,key=lambda r:r["r_ratio"])
    print("F105_INDEX1_RHO",idx[0]["rho_g_cm3"])
    print("F105_INDEX1_RELERR_RANGE",min(r["J_relative_error"] for r in idx),max(r["J_relative_error"] for r in idx))
    print("F105_INDEX1_RATIO_RANGE",min(r["r_ratio"] for r in idx),max(r["r_ratio"] for r in idx))
    crossings=[]
    for lo,hi in zip(ordered,ordered[1:]):
        if (lo["J_cgs"]-4.8245626795750385e48)*(hi["J_cgs"]-4.8245626795750385e48)<0:
            crossings.append([lo["r_ratio"],hi["r_ratio"]])
    print("F105_INDEX1_J_SIGN_CROSSINGS",json.dumps(crossings))
