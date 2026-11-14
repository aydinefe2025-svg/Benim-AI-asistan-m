"""Restore only a verified GitHub CANO colony artifact; never reset known history.

A successful scheduled freshness-only workflow may produce no artifacts.
Search past *successful* runs for the most recent named state artifact, validate
its exact run receipt and SQLite readback, and only then replace the destination.
If no complete state exists, fail closed rather than silently bootstrapping.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from scripts.verify_cano_restore import verify_restored_state

EXPECTED_MODE = "bounded_virtual_reproduction_with_held_out_validation"
REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


def restore_previous_state(destination: Path, *, run_ids, inspect_artifacts, download):
    """Atomic restore, injecting GitHub-only boundaries for deterministic tests.

    Existing cache is never overwritten. An *available* but corrupt matching
    artifact is fatal: silently falling back could roll history backwards.
    """
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        return verify_restored_state(destination)

    run_ids = list(run_ids)
    if any(type(run_id) is not int or run_id <= 0 for run_id in run_ids):
        raise ValueError("GitHub run IDs must be positive integers")
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("Duplicate GitHub run IDs")
    destination.parent.mkdir(parents=True, exist_ok=True)
    for run_id in run_ids:
        artifacts = inspect_artifacts(run_id)
        if not isinstance(artifacts, list):
            raise RuntimeError("GitHub artifact metadata unavailable")
        name = f"cano-colony-cycle-{run_id}"
        matches = [a for a in artifacts if isinstance(a, dict) and a.get("name") == name]
        if len(matches) > 1:
            raise RuntimeError("Ambiguous duplicate CANO state artifacts")
        if not matches or matches[0].get("expired") is True:
            continue
        info = matches[0]
        if type(info.get("size_in_bytes")) is not int or info["size_in_bytes"] <= 0:
            raise RuntimeError("Invalid CANO artifact metadata")
        with tempfile.TemporaryDirectory(prefix=".cano-artifact-", dir=destination.parent) as td:
            work = Path(td)
            try:
                download(run_id, name, work)
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                raise RuntimeError("CANO artifact download failed; preserve old history") from exc
            db_path = work / "colony-cycle.sqlite3"
            receipt_path = work / "colony-cycle.json"
            if not receipt_path.is_file() or not db_path.is_file():
                raise RuntimeError("CANO artifact missing database or receipt")
            try:
                report = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeError, OSError) as exc:
                raise RuntimeError("CANO receipt cannot be read") from exc
            result = verify_restored_state(db_path)
            if (not isinstance(report, dict)
                or report.get("github_run_id") != str(run_id)
                or type(report.get("stored_ticks")) is not int
                or type(report.get("verified_tick_id")) is not int
                or report["stored_ticks"] != result["stored_ticks"]
                or report["verified_tick_id"] != result["last_tick_id"]
                or report.get("db_integrity") != "ok"
                or report.get("mode") != EXPECTED_MODE
                or not isinstance(report.get("specialist_agents"), dict)
                or report["specialist_agents"].get("status") != "passed"):
                raise RuntimeError("CANO receipt does not match verified database/run")
            os.replace(db_path, destination)
            return result
    raise RuntimeError(
        "CANO prior verified state artifact not found; refusing a fresh colony reset"
    )


def _gh_json(*args):
    try:
        run = subprocess.run(["gh", *args], capture_output=True, text=True,
                             check=True, timeout=40)
        return json.loads(run.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # Do not print GH output: CLI errors may include private identifiers.
        raise RuntimeError("GitHub metadata command failed") from exc


def _list_successful_runs(repo):
    values = _gh_json("run", "list", "--repo", repo, "--workflow",
                      "cano-colony-cycle.yml", "--branch", "main",
                      "--status", "success", "--limit", "100",
                      "--json", "databaseId")
    if not isinstance(values, list):
        raise RuntimeError("Unexpected GitHub run-list response")
    return [item.get("databaseId") if isinstance(item, dict) else None
            for item in values]


def _list_artifacts(repo, run_id):
    values = _gh_json("api", f"repos/{repo}/actions/runs/{run_id}/artifacts")
    if not isinstance(values, dict) or not isinstance(values.get("artifacts"), list):
        raise RuntimeError("Unexpected GitHub artifacts response")
    return values["artifacts"]


def _download(repo, run_id, name, dest):
    try:
        subprocess.run(["gh", "run", "download", str(run_id), "--repo", repo,
                        "--name", name, "--dir", str(dest)], check=True,
                       capture_output=True, text=True, timeout=100)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("GitHub artifact download failed") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--dest", default="artifacts/colony-cycle.sqlite3")
    args = parser.parse_args(argv)
    if not isinstance(args.repo, str) or not REPO_PATTERN.fullmatch(args.repo):
        parser.error("Expected owner/repository from trusted GitHub workflow")
    result = restore_previous_state(
        Path(args.dest), run_ids=_list_successful_runs(args.repo),
        inspect_artifacts=lambda run_id: _list_artifacts(args.repo, run_id),
        download=lambda run_id, name, dest: _download(args.repo, run_id, name, dest),
    )
    print(json.dumps({"status": "verified_restored_state", **result}))


if __name__ == "__main__":
    main()
