"""Finite offline CANO task batch.

Processes at most 32 explicitly given jobs. Never starts autonomous loops,
spawns programs, performs network operations, or marks unverified tasks verified.
"""
import argparse
import json
import sys
from pathlib import Path
from .verified_task_runner import run_job

MAX_BATCH=32
MAX_BATCH_BYTES=65536


def run_batch(jobs):
    if not isinstance(jobs,list) or not 1 <= len(jobs) <= MAX_BATCH:
        raise ValueError("batch must contain 1..32 jobs")
    try:
        encoded=json.dumps(jobs,sort_keys=True,ensure_ascii=False,allow_nan=False).encode("utf-8")
    except (TypeError,ValueError,OverflowError) as exc:
        raise ValueError("invalid task batch") from exc
    if len(encoded)>MAX_BATCH_BYTES:
        raise ValueError("batch exceeds byte budget")
    results=[]
    seen=set()
    executed=rejected=duplicates=0
    for index,job in enumerate(jobs):
        try:
            outcome=run_job(job)
        except (ValueError,TypeError,OverflowError):
            results.append({"index":index,"status":"rejected","reason":"invalid_task"})
            rejected+=1
            continue
        receipt=outcome["task_sha256"]
        if receipt in seen:
            results.append({"index":index,"task_sha256":receipt,"status":"duplicate"})
            duplicates+=1
        else:
            seen.add(receipt)
            results.append({"index":index,**outcome})
            executed+=1
    return {"schema":"cano-finite-task-batch-v1",
            "total":len(jobs),"executed":executed,"duplicates":duplicates,
            "rejected":rejected,"results":results,
            "claim_level":"computed_unverified"}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",required=True,help="JSON file with {jobs:[...]}, or - for standard input")
    ns=parser.parse_args(argv)
    try:
        if ns.input=="-":
            raw=sys.stdin.buffer.read(MAX_BATCH_BYTES+1)
        else:
            path=Path(ns.input)
            if path.stat().st_size>MAX_BATCH_BYTES:
                raise ValueError("input file too large")
            raw=path.read_bytes()
        if len(raw)>MAX_BATCH_BYTES:
            raise ValueError("batch too large")
        payload=json.loads(raw)
        if not isinstance(payload,dict) or set(payload)!={"jobs"}:
            raise ValueError("expected {jobs:[...]}")
        result=run_batch(payload["jobs"])
    except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:
        print(json.dumps({"status":"rejected","reason":type(exc).__name__}))
        return 2
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return int(result["rejected"]>0)


if __name__=="__main__":
    raise SystemExit(main())
