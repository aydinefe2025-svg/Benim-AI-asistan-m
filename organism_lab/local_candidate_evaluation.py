"""Bounded local Ollama proposals with an external, fail-closed acceptance oracle.

No user supplied Python is executed. Only localhost model endpoints permitted.
This does not launch autonomous agent processes or grant tool invocation to an LLM.
"""
from __future__ import annotations
import ast
import json
import os
from urllib.parse import urlsplit
from .bounded_task_execution import DISPATCH, gate_result
from .providers import generate, ProviderError


def _local_endpoint():
    raw=os.getenv("OLLAMA_URL","http://localhost:11434/api/generate")
    try:
        parsed=urlsplit(raw)
        valid=(parsed.scheme=="http" and parsed.hostname in ("localhost","127.0.0.1")
               and parsed.port in (None,11434) and parsed.path=="/api/generate"
               and not parsed.username and not parsed.password
               and not parsed.query and not parsed.fragment)
    except ValueError:
        valid=False
    if not valid:
        raise ValueError("refusing a non-local model endpoint")


def _canonical_safe_return(text):
    """Compare a single, statically parsed add-return expression; NEVER execute it."""
    if not isinstance(text,str) or not 0<len(text)<=256:
        return None
    try:
        tree=ast.parse("def _f():\n    "+text.replace("\n","\n    ")+"\n")
    except (SyntaxError,ValueError):
        return None
    if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef):
        return None
    body=tree.body[0].body
    if len(body)!=1 or not isinstance(body[0],ast.Return):
        return None
    expression=body[0].value
    if not (isinstance(expression,ast.BinOp) and isinstance(expression.op,ast.Add)
            and isinstance(expression.left,ast.Name) and expression.left.id=="a"
            and isinstance(expression.right,ast.Name) and expression.right.id=="b"):
        return None
    return ast.dump(expression,include_attributes=False)


def evaluate_candidate(job, *, expected=None, transport=None):
    if not isinstance(job,dict) or job.get("type") not in DISPATCH:
        raise ValueError("unknown task kind denied before model invocation")
    _local_endpoint()
    safe_job={k:v for k,v in job.items() if k not in
              ("expected","expected_patch","gold","label","secret","oracle")}
    try:
        encoded=json.dumps(safe_job,ensure_ascii=False,sort_keys=True,allow_nan=False)
    except (TypeError,ValueError) as exc:
        raise ValueError("cannot encode local task") from exc
    if len(encoded.encode("utf-8"))>4096:
        raise ValueError("oversized local task")
    contracts={
        "python_bug_fix": "For python_bug_fix, return the corrected Python return statement as a JSON string. Infer it from source and the declared failing test; never execute untrusted code.",
        "source_citation_check": "For source_citation_check, return JSON boolean true or false only. Check literal claim inclusion and the caller-supplied peer_reviewed flag; this is metadata consistency, not external verification.",
        "linear_fit_slope": "For linear_fit_slope, compute rise divided by run; return a signed JSON number. Keep the minus sign if y decreases while x increases.",
        "unit_conversion": "For unit_conversion, return the converted amount as a JSON number, not a string.",
        "csv_mean": "For csv_mean, return the arithmetic mean of values as a JSON number.",
        "json_nested_lookup": "For json_nested_lookup, follow path keys in data and return the JSON value at that path.",
    }
    instruction=contracts.get(job["type"],"Return the computation result as a JSON value.")
    prompt=("Solve this bounded task only. No tools, no shell, no filesystem, no web. "
            "Respond with a valid JSON object containing exactly one key 'answer'. "
            "No markdown, notes, confidence claims, or explanation. "
            +instruction+"\nTask: "+encoded)
    try:
        returned=generate(prompt,provider="ollama",transport=transport)
    except ProviderError as exc:
        return {"status":"unavailable","reason":type(exc).__name__}
    try:
        result=json.loads(returned["text"])
    except (ValueError,TypeError):
        return {"status":"rejected","reason":"non_json_model_output"}
    if not isinstance(result,dict) or set(result)!={"answer"}:
        return {"status":"rejected","reason":"invalid_answer_schema"}
    candidate=result["answer"]
    if expected is not None and job["type"]=="python_bug_fix":
        parsed_candidate=_canonical_safe_return(candidate)
        outcome={"status":"verified" if parsed_candidate is not None and parsed_candidate==_canonical_safe_return(expected) else "rejected"}
    else:
        outcome=gate_result(candidate,expected=expected)
    return {"status":outcome["status"],"candidate":candidate,
            "provider":"ollama_local","task_type":job["type"]}
