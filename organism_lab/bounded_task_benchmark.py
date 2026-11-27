"""Reproduce old 30-case schema and a disjoint new seed on Windows.

The families are explicitly programmed; NOT open-ended coding or autonomous research.
"""
import hashlib
import json
import random
from pathlib import Path
import time
from .bounded_task_execution import execute, gate_result

ARCHIVE_SEED=261126
FRESH_SEED=271127
SCHEMA="cano-local-worker-capability-benchmark-v1"


def fixture(seed):
    tasks=[]
    rng=random.Random(seed)
    for i in range(5):
        values=[rng.randint(-100,150) for _ in range(7)]
        tasks.append({"family":"csv_mean","job":{"type":"csv_mean","values":values},"expected":sum(values)/len(values)})
        path=["analysis","period",str(i)]
        tasks.append({"family":"json_nested_lookup","job":{"type":"json_nested_lookup","data":{"analysis":{"period":{str(i):i*2+1}}},"path":path},"expected":i*2+1})
        amount=(i+1)*1.25
        tasks.append({"family":"unit_conversion","job":{"type":"unit_conversion","amount":amount,"from":"kg","to":"g"},"expected":amount*1000})
        slope=i-2
        offset=3*i+1
        points=[[x,slope*x+offset] for x in range(-2,3)]
        tasks.append({"family":"linear_fit_slope","job":{"type":"linear_fit_slope","points":points},"expected":float(slope)})
        tasks.append({"family":"python_bug_fix","job":{"type":"python_bug_fix","source":"def add(a,b):\n    return a-b\n","test":"add(2,3)==5","expected_patch":"return a+b"},"expected":"return a+b"})
        claim=f"Experiment-{i}: N={i+1}"
        source={"id":f"src-{i}","text":claim,"peer_reviewed":i%2==0}
        tasks.append({"family":"source_citation_check","job":{"type":"source_citation_check","claim":claim,"sources":[source],"must_peer_review":True},"expected":i%2==0})
    assert len(tasks)==30
    return tasks


def negatives():
    return [
        {"type":"unknown","x":1},
        {"type":"run_shell","command":"whoami"},
        {"type":"csv_mean","values":[]},
        {"type":"csv_mean","values":[1,True]},
        {"type":"json_nested_lookup","path":["a"]},
        {"type":"json_nested_lookup","data":{},"path":["missing"]},
        {"type":"unit_conversion","amount":1,"from":"kg","to":"m"},
        {"type":"unit_conversion","amount":float("inf"),"from":"kg","to":"g"},
        {"type":"linear_fit_slope","points":[[1,3],[1,4]]},
        {"type":"python_bug_fix","source":"import os\nos.system('x')","test":"add(2,3)==5"},
        {"type":"python_bug_fix","source":"def add(a,b):\n return a-b\n","test":"add(2,3)==99"},
        {"type":"source_citation_check","claim":"N=2","sources":[],"must_peer_review":True},
    ]


def study(seed):
    cases=fixture(seed)
    good=0
    errors=[]
    start=time.perf_counter_ns()
    for i,sample in enumerate(cases):
        try:
            actual=execute(sample["job"])
            verdict=gate_result(actual,expected=sample["expected"])
            if verdict["status"]=="verified": good+=1
            else: errors.append({"index":i,"family":sample["family"],"reason":"oracle_mismatch","actual":actual})
            if gate_result(actual)["status"]!="unverified":
                errors.append({"index":i,"reason":"oracle_bypass"})
            if gate_result(actual,expected="independent wrong expected")["status"]=="verified":
                errors.append({"index":i,"reason":"false_oracle_success"})
        except Exception as exc:
            errors.append({"index":i,"family":sample["family"],"exception":repr(exc)})
    elapsed=(time.perf_counter_ns()-start)/1e6
    return {"seed":seed,"n":len(cases),"correct":good,"accuracy":good/len(cases),
            "families":6,"unique_jobs":len({json.dumps(x["job"],sort_keys=True) for x in cases}),
            "errors":errors,"duration_ms":elapsed}


def run():
    prior=study(ARCHIVE_SEED)
    fresh=study(FRESH_SEED)
    rej=0
    errs=[]
    for i,job in enumerate(negatives()):
        try:
            execute(job)
            errs.append(i)
        except (ValueError,TypeError):
            rej+=1
    module=Path(__file__).with_name("bounded_task_execution.py")
    return {"schema":SCHEMA,"source_path":module.name,
            "source_sha256":hashlib.sha256(module.read_bytes()).hexdigest(),
            "tests":[prior,fresh],
            "n_invalid":len(negatives()),"rejected_invalid":rej,"unsafe_accepts":errs,
            "no_external_network":True,"no_user_code_execution":True,
            "independent_oracle_required":True,
            "production_release":False,
            "limits":"Fixed six practical task schemas. The bug repair is single-pattern only; source review flag is caller-supplied metadata, NOT independently confirmed peer review. No general agent/learning or real-world research accuracy demonstrated."}


def main():
    result=run()
    print(json.dumps(result,sort_keys=True,indent=2))
    if any(t["correct"]<24 for t in result["tests"]) or result["unsafe_accepts"]:
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
