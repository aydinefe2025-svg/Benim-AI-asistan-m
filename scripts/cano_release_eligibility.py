"""Read-only, fail-closed eligibility screen for bounded CANO self-release PRs.

This is only an independent static policy witness. Passing DOES NOT authorize
a merge by itself: verified owner/Neon job, exact CI head, concurrent main
SHA, GitHub protections and Render live SHA must also be checked separately.
Never check out or run candidate code with credentials here.
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.request import Request, urlopen

REPO = "aydinefe2025-svg/Benim-AI-asistan-m"
SOURCE = "core/cano_development_status.py"
TESTS = frozenset({
    "tests/test_cano_owner_code_progress.py",
    "tests/test_cano_code_job_receipt_links.py",
})
BRANCH = re.compile(r"cano/owner-job-[0-9a-f]{8}-[a-z0-9-]{3,48}\Z")
SHA = re.compile(r"[a-f0-9]{40}\Z")
# Reject new imports, execution, file/network/API access, reflection, and
# owner/private-data readers even if they are hidden in strings/comments.
DANGEROUS_ADDITION = re.compile(
    r"(?i)(?:\b(?:import|from|eval|exec|compile|open|input|globals|locals|"
    r"vars|getattr|setattr|delattr|__import__|subprocess|requests|urllib|"
    r"httpx|socket|pickle|secret|credential|password|token|def|class|lambda)\b"
    r"|\b(?:os|sys|shutil|pathlib|importlib)\s*\."
    r"|__|\b(?:st\.secrets|st\.session_state|st\.user)\b"
    r"|\bst\.(?:info|write|caption|json|markdown|text|code|link_button|"
    r"metric|dataframe|table|success|warning|error|exception)\s*\("
    r"|\b(?:print|display|logging)\s*\("
    r"|\b(?:goal|owner_key|email|identity|subject)\b)"
)


def assess(pr, files):
    """Return (eligible, allowlisted_reason). No token, user or payload logging."""
    if not isinstance(pr, dict) or not isinstance(files, list):
        return False, "malformed_input"
    head, base = pr.get("head"), pr.get("base")
    if not isinstance(head, dict) or not isinstance(base, dict):
        return False, "missing_pr_identity"
    if (pr.get("state") != "open"
            or type(pr.get("number")) is not int or pr["number"] <= 0
            or not isinstance(head.get("repo"), dict)
            or head["repo"].get("full_name") != REPO
            or not isinstance(base.get("repo"), dict)
            or base["repo"].get("full_name") != REPO
            or base.get("ref") != "main"
            or not isinstance(head.get("ref"), str)
            or not BRANCH.fullmatch(head["ref"])
            or not isinstance(head.get("sha"), str)
            or not SHA.fullmatch(head["sha"])):
        return False, "untrusted_pr_identity"
    if (type(pr.get("changed_files")) is not int
            or pr["changed_files"] != len(files)
            or not 2 <= len(files) <= 3):
        return False, "incomplete_diff"
    names = []
    for f in files:
        if not isinstance(f, dict):
            return False, "malformed_file"
        name = f.get("filename")
        if not isinstance(name, str) or name in names:
            return False, "duplicate_or_invalid_path"
        names.append(name)
        if (f.get("status") != "modified"
                or type(f.get("additions")) is not int
                or type(f.get("deletions")) is not int
                or f["additions"] < 0 or f["deletions"] < 0
                or not isinstance(f.get("patch"), str)):
            return False, "unverifiable_patch"
    name_set = set(names)
    if SOURCE not in name_set or not name_set.intersection(TESTS):
        return False, "missing_source_or_regression"
    if not name_set.issubset({SOURCE, *TESTS}):
        return False, "outside_bounded_scope"
    for f in files:
        if f["filename"] == SOURCE:
            if f["additions"] > 40 or f["deletions"] > 40:
                return False, "source_diff_too_large"
            # Removing a receipt guard can weaken owner privacy without any
            # suspicious added line. Require independent review instead.
            if f["deletions"]:
                return False, "source_deletion_requires_review"
            added = [
                line[1:] for line in f["patch"].splitlines()
                if line.startswith("+") and not line.startswith("+++")
            ]
            if any(DANGEROUS_ADDITION.search(line) for line in added):
                return False, "unsafe_source_addition"
        elif f["additions"] + f["deletions"] > 250:
            return False, "test_diff_too_large"
    return True, "bounded_diff_eligible"


def _github_files(number, token):
    """Read-only PR file listing, no pagination silently truncated."""
    if not isinstance(token, str) or not token:
        raise ValueError("read_only_token_unavailable")
    url = f"https://api.github.com/repos/{REPO}/pulls/{number}/files?per_page=100"
    req = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urlopen(req, timeout=15) as response:
        records = json.load(response)
    if not isinstance(records, list) or len(records) > 100:
        raise ValueError("unverifiable_file_listing")
    return records


def main():
    """CI runs this trusted-base script and prints only an allowlisted result."""
    try:
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as handle:
            event = json.load(handle)
        pr = event["pull_request"]
        if not isinstance(pr, dict):
            raise ValueError("missing_pr")
        files = _github_files(pr["number"], os.environ.get("GH_TOKEN", ""))
        eligible, reason = assess(pr, files)
        # Fetch exactly one listing; mismatched GitHub metadata must fail
        # closed rather than accepting an incomplete candidate.
        print("CANO_RELEASE_ELIGIBILITY=" + ("PASS" if eligible else "REVIEW_REQUIRED"))
        print("CANO_RELEASE_REASON=" + reason)
        print("CANO_RELEASE_PR=" + str(pr["number"]))
        print("CANO_RELEASE_HEAD_SHA=" + str(pr["head"]["sha"])[:40])
        return 0 if eligible else 1
    except Exception:
        # Do not print exception text: upstream may include credentials.
        print("CANO_RELEASE_ELIGIBILITY=REVIEW_REQUIRED")
        print("CANO_RELEASE_REASON=unverifiable_source")
        return 1


if __name__ == "__main__":
    sys.exit(main())
