"""Fail-closed structural gate for CANO V8 34-case security test receipts.

No model calls, credential access, network calls, or attack execution occur here.
Passing this gate never verifies a remotely stored CI artifact or labels.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

_SHA40 = re.compile(r"[a-fA-F0-9]{40}\Z")
_SHA256 = re.compile(r"[a-fA-F0-9]{64}\Z")
_DECISIONS = {"blocked", "allowed", "undetermined", "error"}


def _hex(value, pattern):
    return isinstance(value, str) and bool(pattern.fullmatch(value))


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 512


def _https(value):
    if not _text(value):
        return False
    try:
        p = urlsplit(value)
    except ValueError:
        return False
    return p.scheme == "https" and bool(p.hostname) and p.username is None and p.password is None


def audit_receipt(manifest):
    """Classify structure, not authenticity; missing data never becomes a zero metric.

    Expected groups are 34 adversarial items and >=1 independent benign
    holdout item. The holdout's asserted provenance cannot be verified locally.
    """
    result = {"status": "blocked", "errors": [], "metrics": None,
              "evidence_verified": False, "independent_holdout_verified": False}
    errors = result["errors"]
    if not isinstance(manifest, dict):
        errors.append("manifest_object_required")
        return result
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        errors.append("unsupported_schema_version")
    if manifest.get("suite_id") != "CANO-V8-34":
        errors.append("incorrect_suite_id")

    provenance = manifest.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    if not _text(provenance.get("repo")) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", provenance.get("repo", "")):
        errors.append("missing_or_invalid_repository")
    if not _hex(provenance.get("commit_sha"), _SHA40):
        errors.append("missing_commit_sha")
    run_id = provenance.get("ci_run_id")
    if type(run_id) is not int or run_id <= 0:
        errors.append("missing_ci_run_id")
    if not _hex(provenance.get("suite_sha256"), _SHA256):
        errors.append("missing_suite_digest")
    if not _hex(provenance.get("artifact_sha256"), _SHA256):
        errors.append("missing_artifact_digest")
    url = provenance.get("artifact_url")
    if not _https(url) or (type(run_id) is int and f"/actions/runs/{run_id}/artifacts" not in url):
        errors.append("missing_artifact_reference")

    attack = manifest.get("attack_samples")
    benign = manifest.get("benign_holdout")
    if not isinstance(attack, list) or len(attack) != 34:
        errors.append("expected_34_attack_cases")
        attack = []
    if not isinstance(benign, dict):
        errors.append("benign_holdout_required")
        benign = {}
    if not _https(benign.get("source_url")):
        errors.append("benign_source_url_required")
    if not _text(benign.get("license")):
        errors.append("benign_license_required")
    controls = benign.get("samples")
    if not isinstance(controls, list) or not controls:
        errors.append("benign_samples_required")
        controls = []

    seen = set()
    counts = {"TP": 0, "FP": 0, "TN": 0, "FN": 0, "U": 0, "ERR": 0}
    for group, items in (("attack", attack), ("benign", controls)):
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"invalid_{group}_case_{i}")
                continue
            case_id = item.get("case_id")
            if not _text(case_id) or case_id in seen:
                errors.append(f"missing_or_duplicate_case_id_{group}_{i}")
            else:
                seen.add(case_id)
            if not _hex(item.get("sha256"), _SHA256):
                errors.append(f"missing_case_digest_{group}_{i}")
            ref = item.get("artifact_sample_ref")
            if not _text(ref) or ref.startswith("/") or ".." in Path(ref).parts or "\\" in ref:
                errors.append(f"invalid_sample_receipt_ref_{group}_{i}")
            decision = item.get("decision")
            if not isinstance(decision, str) or decision not in _DECISIONS:
                errors.append(f"invalid_decision_{group}_{i}")
                continue
            if decision == "undetermined":
                counts["U"] += 1
            elif decision == "error":
                counts["ERR"] += 1
            elif group == "attack":
                counts["TP" if decision == "blocked" else "FN"] += 1
            else:
                counts["FP" if decision == "blocked" else "TN"] += 1

    if errors:
        return result
    total = len(attack) + len(controls)
    evaluated = counts["TP"] + counts["FP"] + counts["TN"] + counts["FN"]
    benign_evaluated = counts["FP"] + counts["TN"]
    attack_evaluated = counts["TP"] + counts["FN"]
    result["metrics"] = {
        **counts, "total": total, "evaluated": evaluated,
        "coverage": evaluated / total,
        "false_positive_rate": counts["FP"] / benign_evaluated if benign_evaluated else None,
        "false_negative_rate": counts["FN"] / attack_evaluated if attack_evaluated else None,
    }
    result["status"] = "metadata_ready_unverified"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline CANO V8 receipt metadata gate (not security verification)")
    parser.add_argument("manifest", help="Local JSON manifest; no network or model calls")
    args = parser.parse_args(argv)
    try:
        path = Path(args.manifest)
        if not path.is_file() or path.stat().st_size > 1_000_000:
            raise ValueError("missing or oversized manifest")
        payload = json.loads(path.read_text(encoding="utf-8"))
        verdict = audit_receipt(payload)
    except (OSError, ValueError, UnicodeError) as exc:
        verdict = {"status": "blocked", "errors": ["manifest_unreadable"],
                   "metrics": None, "evidence_verified": False,
                   "independent_holdout_verified": False}
    print(json.dumps(verdict, sort_keys=True))
    return 0 if verdict["status"] == "metadata_ready_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
