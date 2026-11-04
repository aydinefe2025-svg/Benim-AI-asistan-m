"""Synchronize the Render source branch with main, fast-forward only.

Never force, rebase, or merge divergent user work. This operation only updates
Git refs; Render auto-deploy is a separate operator-controlled setting.
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
                  target="fix/sqlite-backup-restore-20261031"):
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
        return {"status": "already_in_sync", "sha": source_sha}
    is_ancestor = _git(root, "merge-base", "--is-ancestor", target_sha,
                       source_sha, check=False)
    if is_ancestor.returncode != 0:
        raise RuntimeError(
            "Branches diverged: production contains commits missing from main; "
            "human-reviewed integration required, no force-push attempted")
    # Git rejects a concurrent update that violates fast-forward semantics.
    _git(root, "push", "origin", source_sha + ":refs/heads/" + target)
    return {"status": "fast_forwarded", "sha": source_sha}


if __name__ == "__main__":
    import json
    print(json.dumps(sync_branches(), sort_keys=True))
