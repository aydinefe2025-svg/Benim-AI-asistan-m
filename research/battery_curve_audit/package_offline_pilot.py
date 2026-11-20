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
    "external_witness_receipt.py",
    "reviewer_identity_lab.py",
    "provenance_alias_lab.py",
    "battery_virtual_lab.py",
    "customer_pipeline.py",
    "customer_preflight.py",
    "numeric_equivalence_guard.py",
    "near_duplicate_guard.py",
    "original_20261118.py",
    "independent_holdout.py",
    "integrated_customer_gate.py",
    "field_pilot_evidence.py",
    "field_pilot_csv_intake.py",
    "field_receipt_binding.py",
    "field_source_csv_bridge.py",
    "blind_field_review.py",
]
DOCUMENTS = [
    "EXTERNAL_WITNESS_RECEIPT.md",
    "PROVENANCE_ALIAS_LAB.md",
    "SIMULATION_LAB.md",
    "CUSTOMER_PIPELINE.md",
    "CUSTOMER_PREFLIGHT.md",
    "INTEGRATED_CUSTOMER_GATE.md",
    "NUMERIC_EQUIVALENCE.md",
    "NEAR_DUPLICATES.md",
    "FIELD_PILOT_EVIDENCE.md",
    "FIELD_PILOT_CSV_INTAKE.md",
    "FIELD_RECEIPT_BINDING.md",
    "BOUND_FIELD_CSV.md",
    "BLIND_FIELD_REVIEW.md",
    "README.md",
]
TESTS = [
    "test_battery_external_witness_receipt.py",
    "test_battery_reviewer_identity_guard.py",
    "test_battery_reviewer_identity_lab.py",
    "test_battery_virtual_lab.py",
    "test_battery_time_origin_guard.py",
    "test_battery_provenance_aliases.py",
    "test_battery_provenance_alias_lab.py",
    "test_battery_voltage_offset_review.py",
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
    "test_battery_field_csv_intake.py",
    "test_battery_field_receipt_binding.py",
    "test_battery_bound_field_csv.py",
    "test_battery_blind_field_review.py",
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
        "test_battery_external_witness_receipt.py",
        "test_battery_reviewer_identity_guard.py",
        "test_battery_reviewer_identity_lab.py",
        "test_battery_virtual_lab.py",
        "test_battery_time_origin_guard.py",
    "test_battery_provenance_aliases.py",
    "test_battery_provenance_alias_lab.py",
    "test_battery_voltage_offset_review.py",
        "test_battery_customer_pipeline.py",
        "test_battery_customer_output_guard.py",
        "test_battery_integrated_gate.py",
        "test_battery_integrated_output_safety.py",
        "test_battery_units_guard.py",
        "test_battery_field_pilot_evidence.py",
        "test_battery_field_csv_intake.py",
        "test_battery_field_receipt_binding.py",
        "test_battery_bound_field_csv.py",
        "test_battery_blind_field_review.py",
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
    with tempfile.TemporaryDirectory() as tmp:
        out=Path(tmp)/"field-summary.json"
        proc=subprocess.run([
            sys.executable,"research/battery_curve_audit/field_pilot_csv_intake.py",
            "--cells",str(ROOT/"demo-data"/"field_cells.csv"),
            "--reviews",str(ROOT/"demo-data"/"field_reviews.csv"),
            "--frame",str(ROOT/"demo-data"/"field_frame.json"),
            "--summary",str(out),
        ],cwd=ROOT,check=False,capture_output=True,text=True)
        if proc.returncode!=2:
            raise AssertionError("field demo expected provenance block: "+str(proc.returncode)+" "+proc.stderr)
        obj=json.loads(out.read_text("utf-8"))
        if obj["decision"]!="BLOCK_PROVENANCE_LEAKAGE" or obj["field_acceptance"]!="NOT_ESTABLISHED":
            raise AssertionError("field demo unexpectedly accepted")
        if "DEMO_" in out.read_text("utf-8") or "SYNTHETIC_DEMO_NOT_REAL_SITE_PERMISSION" in out.read_text("utf-8"):
            raise AssertionError("field summary leaked identifiers")
        print("FIELD CSV DEMO PASS: BLOCK_PROVENANCE_LEAKAGE")
    # An end-to-end synthetic source->audit->technician CSV->receipt demo.
    # The audit receipt is computed from exact JSON bytes, not invented.
    with tempfile.TemporaryDirectory() as tmp:
        work=Path(tmp)
        manifest=ROOT/"demo-data"/"manifest_clean.json"
        audit=work/"original-source-audit.json"
        pre=subprocess.run([
            sys.executable,"research/battery_curve_audit/integrated_customer_gate.py",
            "--manifest",str(manifest),"--root",str(ROOT/"demo-data"),
            "--report",str(audit)
        ],cwd=ROOT,capture_output=True,text=True)
        if pre.returncode!=0:
            raise AssertionError("synthetic source audit did not pass: "+pre.stderr)
        doc=json.loads(audit.read_text("utf-8"))
        assignments=doc["split"]["assignments"]
        if len(assignments)!=3 or doc["decision"]!="PASS_SCREEN_ONLY":
            raise AssertionError("synthetic source partition unexpectedly blocked")
        cells=work/"cells.csv"
        rows=["cell,device,batch,campaign,partition"]
        for i,entry in enumerate(assignments):
            rows.append(",".join([entry["cell"],"DEV"+str(i),"BATCH"+str(i),
                                  "CAMP"+str(i),entry["partition"]]))
        cells.write_text("\n".join(rows)+"\n",encoding="utf-8")
        reviews=work/"reviews.csv"
        reviewers=[v["cell"] for v in assignments[:2]]
        reviews.write_text(
            "a,b,flagged,reviewer_a_id,reviewer_a_verdict,reviewer_b_id,reviewer_b_verdict\n"
            +reviewers[0]+","+reviewers[1]+",false,BLIND_1,independent,BLIND_2,independent\n",
            encoding="utf-8")
        frame=work/"frame.json"
        frame.write_text(json.dumps({
            "schema":"cano.battery.field-intake-frame.v1",
            "site_authorization":{"permitted":True,
                                  "reference":"SYNTHETIC_ONLY_NOT_REAL_LAB"},
            "audit_receipt_sha256":hashlib.sha256(audit.read_bytes()).hexdigest(),
            "screened_pair_count":3,"screened_flagged_count":0
        },sort_keys=True)+"\n",encoding="utf-8")
        report=work/"bound-redacted.json"
        trial=subprocess.run([
            sys.executable,"research/battery_curve_audit/field_source_csv_bridge.py",
            "--manifest",str(manifest),"--root",str(ROOT/"demo-data"),
            "--audit-report",str(audit),"--cells",str(cells),
            "--reviews",str(reviews),"--frame",str(frame),"--summary",str(report)
        ],cwd=ROOT,capture_output=True,text=True)
        if trial.returncode!=0:
            raise AssertionError("synthetic bound CSV demo failed: "+trial.stderr)
        result=json.loads(report.read_text("utf-8"))
        if (result["decision"]!="PILOT_ONLY_NOT_CERTIFIED" or
                result["field_acceptance"]!="NOT_ESTABLISHED" or
                not result["source_recalculated_and_matched"] or
                not result["receipt_and_partitions_bound"]):
            raise AssertionError("source/ledger not bound or overclaimed acceptance")
        visible=report.read_text("utf-8")
        if any(v in visible for v in
               ("DEMO_", "BLIND_1", "SYNTHETIC_ONLY_NOT_REAL_LAB",
                "audit_receipt_sha256", "BATCH0")):
            raise AssertionError("source-bound report leaked private identifiers")
        print("FOURTH DEMO PASS: source-bound CSV PILOT_ONLY_NOT_CERTIFIED")
    # Fifth demonstration: make prediction-blind forms from original RAW source
    # report, then only allow publication of source-rebound aggregate statistics.
    with tempfile.TemporaryDirectory() as tmp:
        from csv import DictReader,DictWriter
        work=Path(tmp)
        manifest=ROOT/"demo-data"/"manifest_clean.json"
        rawroot=ROOT/"demo-data"
        audit=work/"source-audit.json"
        pre=subprocess.run([
            sys.executable,"research/battery_curve_audit/integrated_customer_gate.py",
            "--manifest",str(manifest),"--root",str(rawroot),"--report",str(audit)
        ],cwd=ROOT,capture_output=True,text=True)
        if pre.returncode!=0:
            raise AssertionError("Fifth demo original source audit failed: "+pre.stderr)
        source=json.loads(audit.read_text("utf-8"))
        if source["decision"]!="PASS_SCREEN_ONLY":
            raise AssertionError("Fifth demo unexpectedly has unresolved source evidence")
        partition={r["cell"]:r["partition"] for r in source["split"]["assignments"]}
        cells=work/"cells.csv"
        cells.write_text("cell,device,batch,campaign,partition\n"+
            "".join(f"{c},SYN_DEVICE_{i},SYN_BATCH_{i},SYN_CAMP_{i},{partition[c]}\n"
                    for i,c in enumerate(sorted(partition))),encoding="utf-8")
        pairs,frame=work/"private-screened.csv",work/"private-frame.json"
        def invoke(*params):
            result=subprocess.run([sys.executable,
                  "research/battery_curve_audit/blind_field_review.py",*map(str,params)],
                  cwd=ROOT,capture_output=True,text=True)
            if result.returncode:
                raise AssertionError("Fifth demo command failed: "+result.stderr)
        invoke("screen","--manifest",manifest,"--root",rawroot,"--audit-report",audit,
               "--cells",cells,"--pairs-out",pairs,"--frame-out",frame)
        config=json.loads(frame.read_text("utf-8"))
        if config["site_authorization"]["permitted"]:
            raise AssertionError("Fifth demo generated authorization was not false")
        config["site_authorization"]={"permitted":True,"reference":"SYNTHETIC_ONLY_NOT_A_REAL_SITE"}
        frame.write_text(json.dumps(config),encoding="utf-8")
        form_a,form_b,seal=work/"reviewer-A.csv",work/"reviewer-B.csv",work/"operator-only.json"
        invoke("prepare","--cells",cells,"--pairs",pairs,"--frame",frame,
               "--audit-report",audit,"--reviewer-a-form",form_a,
               "--reviewer-b-form",form_b,"--operator-seal",seal,"--per-stratum","2")
        for form in (form_a,form_b):
            with form.open(newline="",encoding="utf-8") as stream:
                rows=list(DictReader(stream))
            if not rows or any("flagged" in row or row["verdict"] for row in rows):
                raise AssertionError("Reviewer form accidentally reveals predictions")
            for row in rows:
                row["verdict"]="independent"
            with form.open("w",newline="",encoding="utf-8") as stream:
                writer=DictWriter(stream,fieldnames=("pair_id","a","b","verdict"))
                writer.writeheader();writer.writerows(rows)
        out=work/"redacted-bound-review.json"
        invoke("finalize","--manifest",manifest,"--root",rawroot,
               "--audit-report",audit,"--cells",cells,"--pairs",pairs,"--frame",frame,
               "--reviewer-a-form",form_a,"--reviewer-b-form",form_b,
               "--operator-seal",seal,"--summary",out,
               "--reviewer-a-id","SYN_REVIEWER_A","--reviewer-b-id","SYN_REVIEWER_B")
        result=json.loads(out.read_text("utf-8"))
        if (result["decision"]!="PILOT_ONLY_NOT_CERTIFIED" or
                result["field_acceptance"]!="NOT_ESTABLISHED" or
                not result["source_recalculated_and_matched"]):
            raise AssertionError("Fifth demo generated unsafe field acceptance")
        raw=out.read_text("utf-8")
        if any(x in raw for x in ("SYN_DEVICE_","SYN_REVIEWER_","SYNTHETIC_ONLY_NOT_A_REAL_SITE",
                                  "audit_receipt_sha256")):
            raise AssertionError("Fifth demo exposed private cell/reviewer metadata")
        print("FIFTH BLINDED SYNTHETIC SOURCE-LINKED DEMO PASS")
    print("FIVE SYNTHETIC DEMOS PASS")

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
3. Double-click Run-Reviewer-Simulation.cmd to run 1,000 synthetic reviewer\n   alias and distinct-text controls. Reviewer independence remains unverified.\n   Double-click Run-Provenance-Simulation.cmd to run 1,200 synthetic\n   device/batch/campaign spelling variants, then Run-Simulation.cmd to run the\n   1,400 synthetic-batch
   laboratory study (no real customer data). Then use Run-Demo.cmd to generate an aggregate result from synthetic
   independent curves. Double-click Run-Detection-Demo.cmd for a controlled
   duplicate example; it intentionally returns REVIEW_REQUIRED (exit code 2).
4. For authorized customer CSVs, supply an explicit manifest and an output path:
   Run-Customer.cmd "C:\Lab\manifest.json" "C:\Lab\summary-new.json"
   The manifest paths are relative to the manifest's parent folder.
5. For private lab metadata and two-reviewer CSVs, consult
   research/battery_curve_audit/FIELD_PILOT_CSV_INTAKE.md and run:
   Run-Field-CSV.cmd "C:\Lab\cells.csv" "C:\Lab\reviews.csv" "C:\Lab\frame.json" "C:\Lab\new-summary.json"
   Run-Field-CSV-Demo.cmd is synthetic and intentionally blocks.
6. Existing output files are never overwritten. Select a NEW filename for each
   run; do not delete old evidence before your own archive procedure.

7. To VERIFY the technician CSV roster against the actual raw time/voltage CSVs
   and exact audited split, first generate a private-source-audit.json using
   integrated_customer_gate.py and set frame.json audit_receipt_sha256 to
   the SHA-256 of the exact audit-report bytes (see BOUND_FIELD_CSV.md).
   Then run:
   Run-Field-Verified.cmd "C:\Lab\manifest.json" "C:\Lab\private-source-audit.json" "C:\Lab\cells.csv" "C:\Lab\reviews.csv" "C:\Lab\frame.json" "C:\Lab\NEW-bound-summary.json"
   This verifies source and ledger linkage, NOT site permission or calibration.

8. For a PROSPECTIVE prediction-blind, two-technician review protocol, see
   research/battery_curve_audit/BLIND_FIELD_REVIEW.md. Three commands:
   blind_field_review.py screen / prepare / finalize.
   A screen derives private model pair decisions from reverified original CSVs,
   not an operator's self-written 'flagged' values. Two generated reviewer forms
   omit flagged predictions and have different order; return the completed forms
   separately. Source binding and raw CSVs are checked again on finalize.
   Run-Blind-Review-Demo.cmd tests this with SYNTHETIC inputs only.\n   Private blind-review sampling now authenticates a v2 HMAC seal with a\n   separate 32-byte operator key (--operator-key), which must never be\n   uploaded or shared with reviewers. Older unsigned v1 seals fail closed.
   Real personnel independence and site authorization cannot be proven in code.\n4. Run-Witness-Synthetic-Tests.cmd tests third-party keyed witness integrity
   with temporary SYNTHETIC keys only; external witness key, pre-pinned fingerprint,
   actual institutional authority and independent people are NOT included.
   See research/battery_curve_audit/EXTERNAL_WITNESS_RECEIPT.md.

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

CSV intake cannot verify site consent, source-receipt SHA or blind reviewer
independence. Its default output redacts identifiers, while optional private
ledger is sensitive.

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
"Run-Witness-Synthetic-Tests.cmd": r'''@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m unittest discover -s tests -p "test_battery_external_witness_receipt.py" -q
) else (
  python -m unittest discover -s tests -p "test_battery_external_witness_receipt.py" -q
)
set "RC=%errorlevel%"
echo.
echo TEST KEYS ONLY. Witness HMAC is not institutional identity or physical acceptance.
if not "%CANO_BATCH_NONINTERACTIVE%"=="1" pause
exit /b %RC%
''',

"Run-Reviewer-Simulation.cmd": r'''@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 research\battery_curve_audit\reviewer_identity_lab.py --trials 100 --seed 20261119 --output "reviewer-simulation-1000.json"
) else (
  python research\battery_curve_audit\reviewer_identity_lab.py --trials 100 --seed 20261119 --output "reviewer-simulation-1000.json"
)
set "RC=%errorlevel%"
echo.
echo Synthetic reviewer identity labels only; different IDs do not prove distinct people.
if not "%CANO_BATCH_NONINTERACTIVE%"=="1" pause
exit /b %RC%
''',
"Run-Provenance-Simulation.cmd": r'''@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 research\battery_curve_audit\provenance_alias_lab.py --trials 50 --seed 20261119 --output "provenance-simulation-1200.json"
) else (
  python research\battery_curve_audit\provenance_alias_lab.py --trials 50 --seed 20261119 --output "provenance-simulation-1200.json"
)
set "RC=%errorlevel%"
echo.
echo Synthetic metadata ONLY; no instrument identity or laboratory result certified.
if not "%CANO_BATCH_NONINTERACTIVE%"=="1" pause
exit /b %RC%
''',
"Run-Simulation.cmd": r'''@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 research\battery_curve_audit\battery_virtual_lab.py --trials 100 --seed 20261119 --output "simulation-evidence.json"
) else (
  python research\battery_curve_audit\battery_virtual_lab.py --trials 100 --seed 20261119 --output "simulation-evidence.json"
)
set "RC=%errorlevel%"
echo.
echo Synthetic tests ONLY; output files never overwritten.
if not "%CANO_BATCH_NONINTERACTIVE%"=="1" pause
exit /b %RC%
''',
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
if not "%CANO_BATCH_NONINTERACTIVE%"=="1" pause
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
if not "%CANO_BATCH_NONINTERACTIVE%"=="1" pause
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
if not "%CANO_BATCH_NONINTERACTIVE%"=="1" pause
exit /b %RC%
''',
"Run-Customer.cmd": r'''@echo off
setlocal
if "%~1"=="" goto usage
if "%~2"=="" goto usage
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 research\battery_curve_audit\customer_pipeline.py --manifest "%~f1" --summary "%~f2"
) else (
  python research\battery_curve_audit\customer_pipeline.py --manifest "%~f1" --summary "%~f2"
)
exit /b %errorlevel%
:usage
echo Usage: Run-Customer.cmd "C:\Lab\manifest.json" "C:\Lab\new-summary.json"
echo Never pass unauthorized customer data.
exit /b 2
''',
"Run-Field-CSV.cmd": r'''@echo off
setlocal
if "%~1"=="" goto usage
if "%~2"=="" goto usage
if "%~3"=="" goto usage
if "%~4"=="" goto usage
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 research\battery_curve_audit\field_pilot_csv_intake.py --cells "%~f1" --reviews "%~f2" --frame "%~f3" --summary "%~f4"
) else (
  python research\battery_curve_audit\field_pilot_csv_intake.py --cells "%~f1" --reviews "%~f2" --frame "%~f3" --summary "%~f4"
)
exit /b %errorlevel%
:usage
echo Usage: Run-Field-CSV.cmd "C:\Lab\cells.csv" "C:\Lab\reviews.csv" "C:\Lab\frame.json" "C:\Lab\new-summary.json"
exit /b 2
''',
"Run-Field-CSV-Demo.cmd": r'''@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 research\battery_curve_audit\field_pilot_csv_intake.py --cells "demo-data\field_cells.csv" --reviews "demo-data\field_reviews.csv" --frame "demo-data\field_frame.json" --summary "demo-field-summary.json"
) else (
  python research\battery_curve_audit\field_pilot_csv_intake.py --cells "demo-data\field_cells.csv" --reviews "demo-data\field_reviews.csv" --frame "demo-data\field_frame.json" --summary "demo-field-summary.json"
)
set "RC=%errorlevel%"
echo BLOCK_PROVENANCE_LEAKAGE and exit 2 are expected for synthetic demo.
echo Existing reports are not overwritten.
pause
exit /b %RC%
''',
"Run-Field-Verified.cmd": r'''@echo off
setlocal
if "%~1"=="" goto usage
if "%~2"=="" goto usage
if "%~3"=="" goto usage
if "%~4"=="" goto usage
if "%~5"=="" goto usage
if "%~6"=="" goto usage
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 research\battery_curve_audit\field_source_csv_bridge.py --manifest "%~f1" --root "%~dp1" --audit-report "%~f2" --cells "%~f3" --reviews "%~f4" --frame "%~f5" --summary "%~f6"
) else (
  python research\battery_curve_audit\field_source_csv_bridge.py --manifest "%~f1" --root "%~dp1" --audit-report "%~f2" --cells "%~f3" --reviews "%~f4" --frame "%~f5" --summary "%~f6"
)
exit /b %errorlevel%
:usage
echo Usage: Run-Field-Verified.cmd "manifest.json" "source-audit.json" "cells.csv" "reviews.csv" "frame.json" "NEW-summary.json"
echo The source audit report must match the original authorized CSVs.
exit /b 2
''',
"Run-Blind-Review-Demo.cmd": r'''@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 verify_package.py --demo
) else (
  python verify_package.py --demo
)
set "RC=%errorlevel%"
echo.
echo Prediction-blind fifth demo is synthetic only, not lab acceptance.
if not "%CANO_BATCH_NONINTERACTIVE%"=="1" pause
exit /b %RC%
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

    entries["demo-data/field_cells.csv"] = ("\n".join([
        "cell,device,batch,campaign,partition",
        "DEMO_A,DEV1,B1,C1,train",
        "DEMO_B,DEV2,B2,C2,validation",
        "DEMO_C,DEV3,B3,C3,test",
        "DEMO_D,DEV4,B4,C4,train",
    ])+"\n").encode("utf-8")
    entries["demo-data/field_reviews.csv"] = ("\n".join([
        "a,b,flagged,reviewer_a_id,reviewer_a_verdict,reviewer_b_id,reviewer_b_verdict",
        "DEMO_A,DEMO_B,true,DEMO_REVIEWER_1,linked,DEMO_REVIEWER_2,linked",
        "DEMO_A,DEMO_C,false,DEMO_REVIEWER_1,independent,DEMO_REVIEWER_2,independent",
        "DEMO_B,DEMO_C,false,DEMO_REVIEWER_1,linked,DEMO_REVIEWER_2,linked",
    ])+"\n").encode("utf-8")
    entries["demo-data/field_frame.json"] = (json.dumps({
        "schema":"cano.battery.field-intake-frame.v1",
        "site_authorization":{"permitted":True,"reference":"SYNTHETIC_DEMO_NOT_REAL_SITE_PERMISSION"},
        "audit_receipt_sha256":"d"*64,
        "screened_pair_count":6,"screened_flagged_count":1
    },sort_keys=True,indent=2)+"\n").encode("utf-8")

def build(repo, output, commit):
    entries = _read_inputs(repo)
    entries.update({
        "verify_package.py": VERIFY.encode("utf-8"),
        "START_HERE_TR.md": README.encode("utf-8"),
    })
    entries.update({name:value.encode("ascii") for name,value in LAUNCHERS.items()})
    _samples(entries)
    manifest = {"schema":"cano.battery.offline-pilot-release.v1",
                "version":"2026-11-20-external-keyed-witness-v10",
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
