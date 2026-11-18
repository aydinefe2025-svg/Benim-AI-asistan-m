"""Owner-only, read-only progress for CANO's verified web code-job receipts.

This view never inspects private goal text or owner identifiers. The source is
CodeJobStore.recent(), which already enforces the authenticated OIDC owner.
"""
from __future__ import annotations

import re

_CANONICAL_PR = re.compile(
    r"https://github\.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/[1-9][0-9]*\Z"
)
_ACTIVE = frozenset(("queued", "running", "pr_open", "ci_verified"))


def summarize_recent_code_jobs(jobs):
    """Summarize only the owner-visible recent rows, not the entire database."""
    records = [row for row in jobs if isinstance(row, dict)]
    latest_pr = None
    for row in records:
        if row.get("status") != "deployed":
            continue
        candidate = row.get("pr_url")
        if isinstance(candidate, str) and _CANONICAL_PR.fullmatch(candidate):
            latest_pr = candidate
            break
    return {
        "total": len(records),
        "deployed": sum(row.get("status") == "deployed" for row in records),
        "active": sum(row.get("status") in _ACTIVE for row in records),
        "blocked": sum(row.get("status") == "blocked" for row in records),
        "last_pr_url": latest_pr,
    }


def render_owner_code_status(st, jobs):
    """Render once in the main pane, only when the calling app authenticated."""
    stats = summarize_recent_code_jobs(jobs)
    st.info(
        f"🛠️ CANO kod işleri — Son {stats['total']} kayıt: "
        f"{stats['deployed']} yayınlandı · "
        f"{stats['active']} sırada/çalışıyor · "
        f"{stats['blocked']} engellendi. "
        "Bu, giriş yaptığın hesaba ait kalıcı görev makbuzudur; "
        "sıradaki veya engellenen işler tamamlanmış sayılmaz."
    )
    if stats["last_pr_url"]:
        st.link_button("Son yayınlanan kod değişikliğini aç", stats["last_pr_url"])
    return stats
