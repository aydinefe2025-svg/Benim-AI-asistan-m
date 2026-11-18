"""Owner-only, read-only progress for CANO's verified web code-job receipts.

This view never inspects private goal text or owner identifiers. The source is
CodeJobStore.recent(), which already enforces the authenticated OIDC owner.
"""
from __future__ import annotations

import re

_CANONICAL_PR = re.compile(
    r"https://github\.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/[1-9][0-9]*\Z"
)
_CANONICAL_CI = re.compile(
    r"https://github\.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/[1-9][0-9]*\Z"
)
_CANONICAL_DEPLOY = re.compile(r"dep-[a-z0-9]{12,32}\Z")
_RENDER_SERVICE = "srv-dbiulm8473hc73amkjtg"
_ACTIVE = frozenset(("queued", "running", "pr_open", "ci_verified"))


def _safe_deployed_receipts(jobs):
    """Only trusted links for deployed jobs; reject arbitrary external URLs."""
    for row in jobs:
        if row.get("status") != "deployed":
            continue
        pr = row.get("pr_url")
        ci = row.get("ci_run_url")
        deploy = row.get("deploy_id")
        yield {
            "pr": pr if isinstance(pr, str) and _CANONICAL_PR.fullmatch(pr) else None,
            "ci": ci if isinstance(ci, str) and _CANONICAL_CI.fullmatch(ci) else None,
            "deploy": (
                f"https://dashboard.render.com/web/{_RENDER_SERVICE}/deploys/{deploy}"
                if isinstance(deploy, str) and _CANONICAL_DEPLOY.fullmatch(deploy)
                else None
            ),
        }


def summarize_recent_code_jobs(jobs):
    """Summarize owner entries with complete, canonical PR/CI/Render receipts.

    A stored deployed status is not evidence without its own PR, CI and
    Render identifiers. Even a complete receipt is not a fresh remote check.
    """
    records = [row for row in jobs if isinstance(row, dict)]
    completed = [
        receipt for receipt in _safe_deployed_receipts(records)
        if receipt["pr"] and receipt["ci"] and receipt["deploy"]
    ]
    labeled_deployed = sum(row.get("status") == "deployed" for row in records)
    return {
        "total": len(records),
        "deployed": len(completed),
        "unverified_deployments": labeled_deployed - len(completed),
        "active": sum(row.get("status") in _ACTIVE for row in records),
        "blocked": sum(row.get("status") == "blocked" for row in records),
        "last_pr_url": completed[0]["pr"] if completed else None,
    }


def render_owner_code_status(st, jobs):
    """Render once in the main pane, only when the calling app authenticated."""
    stats = summarize_recent_code_jobs(jobs)
    st.info(
        f"🛠️ CANO kod işleri — Son {stats['total']} kayıt: "
        f"{stats['deployed']} tam makbuzlu yayın kaydı · "
        f"{stats['unverified_deployments']} makbuzu eksik yayın etiketi · "
        f"{stats['active']} sırada/çalışıyor · "
        f"{stats['blocked']} engellendi. "
        "Görünen bağlantılar kayıt kanıtıdır; CI başarısı ve Render LIVE "
        "bu ekranda bağımsız olarak yeniden kontrol edilmemiştir."
    )
    if stats["last_pr_url"]:
        st.link_button("Son yayınlanan kod değişikliğini aç", stats["last_pr_url"])
    # Only show a complete same-job PR/CI/Render receipt; never mix
    # evidence from different jobs or present partial evidence as proof.
    receipt = next(
        (r for r in _safe_deployed_receipts(jobs)
         if r["pr"] and r["ci"] and r["deploy"]), None
    )
    if receipt is not None:
        if receipt["ci"]:
            st.link_button("GitHub CI makbuzunu aç", receipt["ci"])
        if receipt["deploy"]:
            st.link_button("Render dağıtım makbuzunu aç", receipt["deploy"])
    return stats
