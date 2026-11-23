#!/usr/bin/env python3
"""One-command, fail-closed real-source replay for BIRDS EPS + AGV.

Usage from repository root (Python 3.11+):
    python research/gka_final_owner_replay.py --output-dir GKA_FINAL_PROOF_LOCAL

Publisher files are fetched in memory by existing pinned/source-validated scripts.
No original CSV/XLSX is re-distributed, and no source data or secrets are altered.
A successful replay verifies computational evidence ONLY: no fault or SoH proof.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import zipfile

REPO = Path(__file__).resolve().parent.parent
RESEARCH = REPO / "research"
TESTS = (
    "test_birds_manuscript_population_guard.py",
    "test_birds_published_panel_rules.py",
    "test_agv_temp_stratified_qc.py",
    "test_agv_day_cluster_common_support.py",
    "test_agv_month_pair_block_sensitivity.py",
)
STAGES = (
    ("source", "tsuru_agv_real_source_ci.py", "TSURU_AGV_REAL_SOURCE_CI_RECEIPT.json",
     "BOTH_ORIGINAL_BYTES_REPLAYED_AND_PINNED"),
    ("four_birds", "birds_eps_constellation_qc.py", "BIRDS_FOUR_EPS_CI_RECEIPT.json",
     "FOUR_SATELLITE_SOURCE_IDENTITIES_AND_OOXML_PROFILE_VERIFIED"),
    ("population", "birds_manuscript_population_guard.py",
     "BIRDS_2022_PAPER_POPULATION_CONCORDANCE_RECEIPT.json",
     "PUBLISHER_POPULATION_CONCORDANCE_AUDITED_WITH_SOURCE_SHEET_DATES"),
    ("panel", "birds_published_panel_rules.py",
     "BIRDS_FOUR_PUBLISHED_PANEL_RULES_SCREEN_RECEIPT.json",
     "PUBLISHER_RULES_APPLIED_TO_PINNED_SOURCE_SCREENING_ONLY"),
    ("temperature", "agv_temp_stratified_qc.py",
     "AGV_TEMP_MATCHED_REAL_SOURCE_RECEIPT.json",
     "REAL_AGV_TEMP_STRATIFIED_EXPLORATORY_QC"),
    ("day_cluster", "agv_day_cluster_common_support.py",
     "AGV_DAY_CLUSTER_COMMON_SUPPORT_RECEIPT.json",
     "OBSERVATIONAL_AGV_COMMON_SUPPORT_AND_DAY_CLUSTER_AUDIT"),
    ("month_block", "agv_month_pair_block_sensitivity.py",
     "AGV_PAIRED_MONTH_BLOCK_SENSITIVITY_RECEIPT.json",
     "AGV_PAIRED_CALENDAR_MONTH_BLOCK_SENSITIVITY_ORIGINAL_DATA"),
)
FIVE_SAT = ("TSURU", "UGUISU", "RAAVANA", "NEPALISAT")
EXPECTED_AGV_MD5 = "2faa82bd0c27763d4b12d4c58510a1f5"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for piece in iter(lambda: stream.read(1 << 20), b""):
            h.update(piece)
    return h.hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def verify_documents(documents):
    """Independent cross-file checks; not merely testing each receipt's status."""
    src, four, population, panel, temp, day, month = (
        documents[s[0]] for s in STAGES
    )
    for key, _, _, expected in STAGES:
        require(documents[key].get("status") == expected, key + ": unexpected status")
    require(src["agv"]["rows"] == 57880 and src["agv"]["packs"] == 10,
            "AGV publisher sample size changed")
    require(src["agv"]["md5"] == EXPECTED_AGV_MD5, "AGV publisher MD5 changed")
    require(src["tsuru"]["rows_excluding_headers"] == 26023,
            "TSURU original source population changed")
    require(len(four["satellites"]) == 4 and len(panel["satellites"]) == 4,
            "four original satellites not all represented")
    for name in FIVE_SAT:
        baseline = (src["tsuru"]["sha256"] if name == "TSURU"
                    else four["satellites"][name]["sha256"])
        require(four["satellites"][name]["sha256"] == baseline,
                name + ": four-source identity conflict")
        require(panel["satellites"][name]["sha256"] == baseline,
                name + ": published-panel source identity conflict")
    source_sha = src["agv"]["sha256"]
    for name, field in (("temperature", "agv_sha256"),
                        ("day_cluster", "source_sha256"),
                        ("month_block", "input_source_sha256")):
        require(documents[name][field] == source_sha,
                name + ": AGV publisher identity conflict")
    require(population["original_three_birds"]["source_rows"] == 8469,
            "paper/source record count changed")
    require(population["original_three_birds"][
        "source_rows_outside_paper_window_by_sheet"] == 7390,
        "manuscript period mismatch no longer reconciles")
    require(not population["acceptance"]["paper_8439_same_population_as_original_workbooks"],
            "published benchmark population incorrectly equated with source")
    require(not population["acceptance"]["published_test_metrics_reproduced"],
            "benchmark model F1 not independently reproduced")
    require(panel["independent_physical_fault_confirmation"] is False,
            "physical fault claim changed without evidence")
    require(day["source_n_rows"] == 57880 and month["source_rows"] == 57880,
            "AGV source subset accidentally treated as original")
    require(month["negative_estimate_packs"] == 5 and
            month["positive_estimate_packs"] == 5,
            "AGV original population contrast changed")
    require(month["interval_excludes_zero_packs"] == ["FB-1"],
            "AGV original exploratory month-pair sensitivity changed")
    for pack in sorted(month["packs"]):
        old = day["results"][pack]["temperature_stratified_pct"]
        new = month["packs"][pack]["estimate_pct"]
        require(old is not None and new is not None and abs(old-new) < 2e-6,
                pack + ": month/day point estimate mismatch")
    return {
        "original_agv_events": 57880,
        "original_satellites": 4,
        "three_birds_source_rows": 8469,
        "paper_labeled_rows": 8439,
        "source_rows_outside_manuscript_window_by_sheet": 7390,
        "agv_month_pair_excludes_zero_descriptive_only": ["FB-1"],
        "benchmark_accuracy_reproduced": False,
        "independent_physical_fault_confirmed": False,
        "battery_capacity_or_soh_measured": False,
    }


def execute(cmd, workdir, label, logs):
    process = subprocess.run(cmd, cwd=workdir, env=os.environ.copy(),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             encoding="utf-8", errors="replace", timeout=600,
                             check=False)
    (logs / (label + ".log")).write_text(process.stdout, encoding="utf-8")
    if process.returncode:
        raise RuntimeError(label + " exited " + str(process.returncode) +
                           "; inspect logs/" + label + ".log")
    print("PASS " + label, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True,
                        help="New EMPTY directory for receipts and evidence archive")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required")
    output = Path(args.output_dir).expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Output directory is not empty; refusing to overwrite evidence")
    output.mkdir(parents=True, exist_ok=True)
    logs = output / "logs"
    logs.mkdir()
    state = {"status": "FAILED_NOT_CERTIFIED", "started_at_utc": dt.datetime.now(
        dt.timezone.utc).isoformat(), "platform": platform.platform(),
             "python": sys.version, "output": str(output),
             "personal_windows_execution_attested": False}
    try:
        for index, pattern in enumerate(TESTS):
            execute([sys.executable, "-m", "unittest", "discover",
                     "-s", str(RESEARCH), "-p", pattern, "-v"],
                    output, "test_" + str(index + 1), logs)
        documents = {}
        manifest = {}
        for name, filename, output_file, expected_status in STAGES:
            execute([sys.executable, str(RESEARCH / filename)],
                    output, "source_" + name, logs)
            receipt = output / output_file
            require(receipt.is_file(), name + ": no original-source JSON receipt")
            document = json.loads(receipt.read_text(encoding="utf-8"))
            require(document.get("status") == expected_status,
                    name + ": expected real-data result missing")
            documents[name] = document
            manifest[output_file] = {
                "sha256": digest(receipt), "bytes": receipt.stat().st_size
            }
        facts = verify_documents(documents)
        state.update({
            "status": "COMPUTATIONAL_ORIGINAL_SOURCE_REPLAY_VERIFIED",
            "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "scope": "Original pinned source reprocessing, NOT physical causality or SoH",
            "source_facts": facts,
            "files": manifest,
            "script_sha256": digest(Path(__file__)),
            "tests_executed": list(TESTS),
        })
        status_path = output / "GKA_FINAL_REPLAY_STATUS.json"
        status_path.write_text(json.dumps(state, sort_keys=True, indent=2) +
                               "\n", encoding="utf-8")
        archive = output / "GKA_FINAL_PROOF.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=8) as zipf:
            for receipt in sorted(manifest):
                zipf.write(output / receipt, receipt)
            zipf.write(status_path, status_path.name)
        with zipfile.ZipFile(archive) as z:
            require(z.testzip() is None and len(z.namelist()) == len(manifest) + 1,
                    "output archive CRC or member count mismatch")
        print("GKA_FINAL_COMPUTATIONAL_REPLAY_VERIFIED=" + json.dumps({
            "manifest": status_path.name,
            "archive": archive.name,
            "sha256": digest(archive),
            "original_agv_events": facts["original_agv_events"],
            "four_satellites": facts["original_satellites"],
            "personal_pc_attested": False,
        }, sort_keys=True), flush=True)
    except Exception as exc:
        state["failure_reason"] = type(exc).__name__ + ": " + str(exc)
        (output / "GKA_FINAL_REPLAY_STATUS.json").write_text(
            json.dumps(state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print("GKA_FINAL_REPLAY_FAILED=" + state["failure_reason"],
              file=sys.stderr, flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
