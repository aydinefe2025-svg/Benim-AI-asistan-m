#!/usr/bin/env python3
"""Create a reproducible, self-checking, offline battery-audit pilot ZIP.

Release contains only source code, docs, tests and synthetic examples.
Never includes GitHub Actions raw publisher artifacts or customer data.
"""
from __future__ import annotations
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

PREFIX = "CANO_BATARYA_CEVRIMDISI_PILOT"
EPOCH = (2026, 11, 19, 0, 0, 0)
PROGRAMS = [
    "customer_pipeline.py",
    "customer_preflight.py",
    "numeric_equivalence_guard.py",
    "near_duplicate_guard.py",
    "original_20261118.py",
    "independent_holdout.py",
    "integrated_customer_gate.py",
    "field_pilot_evidence.py",
    "field_receipt_binding.py",
]
DOCUMENTS = [
    "CUSTOMER_PIPELINE.md",
    "CUSTOMER_PREFLIGHT.md",
    "INTEGRATED_CUSTOMER_GATE.md",
    "NUMERIC_EQUIVALENCE.md",
    "NEAR_DUPLICATES.md",
    "FIELD_PILOT_EVIDENCE.md",
    "FIELD_RECEIPT_BINDING.md",
    "README.md",
]
TESTS = [
    "test_battery_customer_pipeline.py",
    "test_battery_customer_output_guard.py",
    "test_battery_decimal_identity.py",
    "test_battery_units_guard.py",
    "test_battery_numeric_equivalence.py",
    "test_battery_near_duplicate_guard.py",
    "test_battery_independent_holdout.py",
    "test_battery_integrated_gate.py",
    "test_battery_integrated_output_safety.py",
    "test_battery_field_pilot_evidence.py",
    "test_battery_field_receipt_binding.py",
    "test_customer_preflight.py",
]

VERIFY = r'''#!/usr/bin/env python3
"""Check every packaged file against the original build manifest; optionally test."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent

def verify():
    record = json.loads((ROOT / "release_manifest.json").read_text("utf-8"))
    files = record["files"]
    for rel, expected in sorted(files.items()):
        if rel.startswith("/") or ".." in Path(rel).parts or "\\" in rel:
            raise ValueError("Unsafe manifest path: " + rel)
        path = (ROOT / rel).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError("Missing or invalid file: " + rel)
        b = path.read_bytes()
        if len(b) != expected["bytes"] or hashlib.sha256(b).hexdigest() != expected["sha256"]:
            raise ValueError("Modified file: " + rel)
    print("INTEGRITY PASS:",len(files),"source/demo/test/launcher files; commit",record["source_commit"])
    return record

def tests():
    patterns = [
        "test_battery_customer_pipeline.py",
        "test_battery_customer_output_guard.py",
        "test_battery_integrated_gate.py",
        "test_battery_integrated_output_safety.py",
        "test_battery_units_guard.py",
        "test_battery_field_pilot_evidence.py",
        "test_battery_field_receipt_binding.py",
    ]
    for name in patterns:
        subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-p",name,"-v"],cwd=ROOT,check=True)
    print("PACKAGED TESTS PASS")

def demo():
    with tempfile.TemporaryDirectory() as tmp:
        for name, expected_return, expected_decision in [
            ("manifest_clean.json",0,"SCREEN_ONLY_NO_CROSS_CELL_CANDIDATES"),
            ("manifest_duplicate.json",2,"REVIEW_REQUIRED"),
        ]:
            out = Path(tmp) / (name + ".out.json")
            proc = subprocess.run([
                sys.executable, "research/battery_curve_audit/customer_pipeline.py",
                "--manifest",str(ROOT/"demo-data"/name),
                "--root",str(ROOT/"demo-data"),
                "--summary",str(out)
            ],cwd=ROOT,check=False,capture_output=True,text=True)
            if proc.returncode != expected_return:
                raise AssertionError(name + " unexpected exit: " + str(proc.returncode) + ": " + proc.stderr)
            doc = json.loads(out.read_text("utf-8"))
            if doc["decision"] != expected_decision:
                raise AssertionError(name + " decision " + str(doc["decision"]))
            if doc["private_identifiers_in_public_summary"] or "DEMO_" in out.read_text("utf-8"):
                raise AssertionError("public demo leaked cell identifier")
            print(name, "PASS:", expected_decision)
    print("TWO SYNTHETIC DEMO CASES PASS")

if __name__ == "__main__":
    verify()
    if "--tests" in sys.argv:
        tests()
    if "--demo" in sys.argv:
        demo()
'''

README = r'''# CANO | Offline Battery Data Preflight Pilot

This is a free, offline Python 3.12+ screening prototype, NOT a certified battery
health/SOH instrument, paid commercial service, or independence certificate.
It does not need pip, cloud tokens, API keys, or customer uploads.

## Windows, quickest start
1. Unzip to a regular folder; do not run directly inside the ZIP.
2. Double-click Verify-Package.cmd (hashes only) or run:
   py -3 verify_package.py --tests --demo
3. Double-click Run-Demo.cmd to generate an aggregate result from synthetic
   independent curves. Double-click Run-Detection-Demo.cmd for a controlled
   duplicate example; it intentionally returns REVIEW_REQUIRED (exit code 2).
4. For authorized customer CSVs, supply an explicit manifest and an output path:
   Run-Customer.cmd "C:\Lab\manifest.json" "C:\Lab\summary-new.json"
   The manifest paths are relative to the manifest's parent folder.
5. Existing output files are never overwritten. Select a NEW filename for each
   run; do not delete old evidence before your own archive procedure.

## Windows PowerShell alternative
   py -3 research/battery_curve_audit/customer_pipeline.py --manifest
   (Use on ONE physical command line: --manifest path --root folder --summary path)

## Linux/macOS
   python3 verify_package.py --tests --demo
   python3 research/battery_curve_audit/customer_pipeline.py --manifest
   demo-data/manifest_clean.json --root demo-data --summary ./clean-report.json

## What is checked?
CSV timestamp/voltage unit compatibility; omitted complete trailing pairs (no
zero fill); exact text and exact Decimal numeric duplicate curves; nearby curves
as review CANDIDATES; source file hash rechecks; whole-cell transitive holdouts;
short/flat unscreened traces; case where fewer than three cell groups survive.
A safe-looking output is a SCREEN, not proof of independent experiments.

The PUBLIC summary contains counts/units but no cell IDs, filenames, SHA hashes
or raw traces. Optional private split (CLI --private-split) contains sensitive
identifiers: keep only inside an authorized customer's protected folder.
--report-only cannot be combined with --private-split. Review required returns
exit 2; --report-only is for inspection, not authorization to train/test.

The optional integrated_customer_gate.py is a stricter acceptance-oriented gate.
It emits NO accepted split for unresolved exact/near candidates; do not infer
physical independence from a green technical result.

Scientific limitations: no live customer/site or instrument acceptance, no
independently established sensitivity/specificity, no measured field false
negative rate, no SOH/SOC prediction validation, no warranty or revenue.

## Data provenance and licenses
Demo curves are wholly SYNTHETIC, not a published experiment. No publisher
CSV measurements are included. This pilot's benchmark context:
BulyK47 / POLITEHNICA Bucharest battery-datasets; CC BY 4.0 data,
https://github.com/BulyK47/battery-datasets
DOI: https://doi.org/10.21227/cm0f-jg66
The independent SOC source David-EIPI is not bundled and requires its own
BSD-2-Clause attribution if used separately.

The manifest verifies accidental modification, not publisher authenticity.
For provenance, compare the source_commit in release_manifest.json with the
verified GitHub main or PR commit and compare the ZIP's externally reported
SHA-256 receipt. Never treat a self-supplied checksum as a digital signature.
'''

LAUNCHERS = {
"Verify-Package.cmd": r'''@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 verify_package.py
) else (
  python verify_package.py
)
set "RC=%errorlevel%"
echo.
pause
exit /b %RC%
''',
"Run-Demo.cmd": r'''@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 research\battery_curve_audit\customer_pipeline.py --manifest "demo-data\manifest_clean.json" --root "demo-data" --summary "demo-clean-summary.json"
) else (
  python research\battery_curve_audit\customer_pipeline.py --manifest "demo-data\manifest_clean.json" --root "demo-data" --summary "demo-clean-summary.json"
)
set "RC=%errorlevel%"
echo.
echo Existing reports are never overwritten. Review demo-clean-summary.json.
pause
exit /b %RC%
''',
"Run-Detection-Demo.cmd": r'''@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 research\battery_curve_audit\customer_pipeline.py --manifest "demo-data\manifest_duplicate.json" --root "demo-data" --summary "demo-duplicate-summary.json"
) else (
  python research\battery_curve_audit\customer_pipeline.py --manifest "demo-data\manifest_duplicate.json" --root "demo-data" --summary "demo-duplicate-summary.json"
)
set "RC=%errorlevel%"
echo.
echo REVIEW_REQUIRED and exit 2 is EXPECTED in the controlled duplicate demo.
echo Existing reports are never overwritten.
pause
exit /b %RC%
''',
"Run-Customer.cmd": r'''@echo off
setlocal
if "%~1"=="" goto usage
if "%~2"=="" goto usage
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 research\battery_curve_audit\customer_pipeline.py --manifest "%~f1" --root "%~dp1" --summary "%~f2"
) else (
  python research\battery_curve_audit\customer_pipeline.py --manifest "%~f1" --root "%~dp1" --summary "%~f2"
)
exit /b %errorlevel%
:usage
echo Usage: Run-Customer.cmd "C:\Lab\manifest.json" "C:\Lab\new-summary.json"
echo Never pass unauthorized customer data.
exit /b 2
''',
}

def _read_inputs(repo):
    entries = {}
    for name in PROGRAMS + DOCUMENTS:
        rel = "research/battery_curve_audit/" + name
        entries[rel] = (repo / rel).read_bytes()
    for name in TESTS:
        rel = "tests/" + name
        entries[rel] = (repo / rel).read_bytes()
    return entries

def _samples(entries):
    levels = {"A": "4.10", "B": "4.10", "C": "3.80", "D": "3.50"}
    for cell, level in levels.items():
        lines = ["Timestamp_1 [h],DC1 [V]"]
        for i in range(120):
            voltage = Decimal(level) - Decimal(i)*Decimal("0.002")
            value = format(voltage, ".4f") if cell == "B" else str(voltage)
            lines.append(f"{i},{value}")
        entries[f"demo-data/{cell}.csv"] = ("\n".join(lines)+"\n").encode("utf-8")
    for kind, names in (("clean",("A","C","D")),("duplicate",("A","B","C","D"))):
        obj = {"schema":"cano.battery.customer-files.v1",
               "files":[{"path":k+".csv","cell":"DEMO_"+k,"mode":"dchg"} for k in names]}
        entries[f"demo-data/manifest_{kind}.json"] = (json.dumps(obj,indent=2)+"\n").encode()

def build(repo, output, commit):
    entries = _read_inputs(repo)
    entries.update({
        "verify_package.py": VERIFY.encode("utf-8"),
        "START_HERE_TR.md": README.encode("utf-8"),
    })
    entries.update({name:value.encode("ascii") for name,value in LAUNCHERS.items()})
    _samples(entries)
    manifest = {"schema":"cano.battery.offline-pilot-release.v1",
                "version":"2026-11-19-pilot",
                "source_repo":"aydinefe2025-svg/Benim-AI-asistan-m",
                "source_commit":commit,
                "contains_raw_publisher_or_customer_data":False,
                "files":{k:{"sha256":hashlib.sha256(v).hexdigest(),"bytes":len(v)}
                         for k,v in sorted(entries.items())}}
    entries["release_manifest.json"]=(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n").encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
        raise ValueError("Will not overwrite existing release package")
    with ZipFile(output,"x",compression=ZIP_DEFLATED,compresslevel=8) as z:
        for rel,data in sorted(entries.items()):
            info=ZipInfo(PREFIX+"/"+rel,date_time=EPOCH)
            info.compress_type=ZIP_DEFLATED
            info.external_attr=(0o644 << 16)
            z.writestr(info,data,compress_type=ZIP_DEFLATED,compresslevel=8)
    with ZipFile(output) as z:
        bad=z.testzip()
        if bad:
            raise ValueError("Broken ZIP member: "+bad)
    print("RELEASE CREATED",output,"bytes",output.stat().st_size,
          "sha256",hashlib.sha256(output.read_bytes()).hexdigest(),
          "files",len(entries),"commit",commit)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    p=parser.parse_args()
    repo=Path(__file__).resolve().parents[2]
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()
    if len(commit)!=40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Missing Git commit provenance")
    build(repo,p.output,commit)
if __name__=="__main__":
    main()
