"""Audit legacy recovery refs without writes; allow explicit manual fast-forward only.

Render's service source was verified as main on 2026-11-09. The historical
fix/sqlite-backup-restore-20261031 ref is preserved and is NOT auto-deployed.
Never force, rebase, or merge divergent work through this module.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_SAFE_REF = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,150}$")


def _git(cwd, *args, check=True):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                            text=True, check=False, timeout=30)
    if check and result.returncode:
        raise RuntimeError("Git branch sync failed; existing refs preserved")
    return result


def sync_branches(*, cwd=".", source="main",
                  target="fix/sqlite-backup-restore-20261031",
                  audit_only=False):
    """Inspect refs with audit_only=True; only explicit manual mode may push."""
    if type(audit_only) is not bool:
        raise ValueError("audit_only must be bool")
    if (not _SAFE_REF.fullmatch(source) or not _SAFE_REF.fullmatch(target)
            or source == target or source.endswith(".lock")
            or target.endswith(".lock") or ".." in source or ".." in target
            or "//" in source or "//" in target):
        raise ValueError("Invalid branch sync pair")
    root = Path(cwd)
    src = "refs/remotes/origin/" + source
    dst = "refs/remotes/origin/" + target
    _git(root, "fetch", "--no-tags", "origin",
         "+" + "refs/heads/" + source + ":" + src,
         "+" + "refs/heads/" + target + ":" + dst)
    source_sha = _git(root, "rev-parse", src).stdout.strip()
    target_sha = _git(root, "rev-parse", dst).stdout.strip()

    if source_sha == target_sha:
        if audit_only:
            return {"status": "already_in_sync", "source_sha": source_sha,
                    "target_sha": target_sha, "requires_human_review": False,
                    "mutated": False}
        return {"status": "already_in_sync", "sha": source_sha}

    target_is_ancestor = _git(root, "merge-base", "--is-ancestor", target_sha,
                              source_sha, check=False)
    if target_is_ancestor.returncode not in (0, 1):
        raise RuntimeError("Git ancestry audit failed; refs preserved")
    if audit_only:
        if target_is_ancestor.returncode == 0:
            status, requires_review = "legacy_behind_main", False
        else:
            source_is_ancestor = _git(root, "merge-base", "--is-ancestor",
                                      source_sha, target_sha, check=False)
            if source_is_ancestor.returncode not in (0, 1):
                raise RuntimeError("Git ancestry audit failed; refs preserved")
            status = ("legacy_ahead_main" if source_is_ancestor.returncode == 0
                      else "legacy_diverged_requires_review")
            requires_review = True
        return {"status": status, "source_sha": source_sha,
                "target_sha": target_sha,
                "requires_human_review": requires_review, "mutated": False}

    if target_is_ancestor.returncode != 0:
        raise RuntimeError(
            "Branches diverged: legacy contains commits missing from main; "
            "human-reviewed integration required, no force-push attempted")
    # Explicit manual mode only: Git refuses non-fast-forward updates.
    _git(root, "push", "origin", source_sha + ":refs/heads/" + target)
    return {"status": "fast_forwarded", "sha": source_sha}


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Legacy branch read-only audit")
    parser.add_argument("--audit-only", required=True, action="store_true",
                        help="Inspect divergence but never update any remote branch")
    arguments = parser.parse_args()
    result = sync_branches(audit_only=arguments.audit_only)
    if result["requires_human_review"]:
        print("::warning::Historical recovery branch is ahead/diverged; "
              "preserve it for human-reviewed integration; no Git ref updated.")
    print(json.dumps(result, sort_keys=True))
