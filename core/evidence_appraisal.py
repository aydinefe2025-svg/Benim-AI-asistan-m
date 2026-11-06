"""Human-recorded, claim-level evidence profiles; never a universal truth score."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone


_OWNER = re.compile(r"^oidc_[0-9a-f]{64}$")
_DOI = re.compile(r"^10\.\d{4,9}/[A-Za-z0-9._;()/:+\-]{1,180}$", re.I)
_DESIGNS = {
    "randomized_trial", "observational", "systematic_review",
    "qualitative", "case_report", "computational", "preprint",
    "other", "unclear",
}
_TRI_STATES = {"yes", "no", "unclear", "not_applicable"}
_ROB_DOMAINS = (
    "randomization", "deviations_from_interventions", "missing_outcome_data",
    "outcome_measurement", "selective_reporting",
)
_ROB_JUDGEMENTS = {"low", "some_concerns", "high", "unclear"}


def validate_appraisal_profile(profile):
    """Validate structured notes without producing a quality score."""
    if not isinstance(profile, dict):
        raise ValueError("Evidence profile must be an object")
    design = profile.get("study_design")
    if design not in _DESIGNS:
        raise ValueError("Choose a recognized study design or unclear")
    required = (
        "population", "sample_size", "comparator", "outcome",
        "effect_estimate", "uncertainty", "limitations",
    )
    for field in required:
        value = profile.get(field)
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 1000:
            raise ValueError(field + " must contain 1–1000 characters; use 'unclear' if unreported")
    if profile.get("preregistration") not in _TRI_STATES:
        raise ValueError("Preregistration status must be explicit")
    if profile.get("independent_replication") not in _TRI_STATES:
        raise ValueError("Replication status must be explicit")
    if profile.get("conflicting_evidence") not in _TRI_STATES:
        raise ValueError("Conflicting-evidence status must be explicit")
    if design == "randomized_trial":
        domains = profile.get("risk_of_bias")
        if not isinstance(domains, dict):
            raise ValueError("Randomized trials require result-level risk-of-bias notes")
        for domain in _ROB_DOMAINS:
            entry = domains.get(domain)
            if (not isinstance(entry, dict)
                    or entry.get("judgement") not in _ROB_JUDGEMENTS
                    or not isinstance(entry.get("rationale"), str)
                    or not 10 <= len(entry["rationale"].strip()) <= 500):
                raise ValueError("Each RoB 2 domain needs a judgement and rationale")
    elif profile.get("risk_of_bias") not in (None, {}):
        raise ValueError("RoB 2 fields apply only to randomized trials")
    return {
        "study_design": design,
        **{field: profile[field].strip() for field in required},
        "preregistration": profile["preregistration"],
        "independent_replication": profile["independent_replication"],
        "conflicting_evidence": profile["conflicting_evidence"],
        **({"risk_of_bias": {
            domain: {
                "judgement": profile["risk_of_bias"][domain]["judgement"],
                "rationale": profile["risk_of_bias"][domain]["rationale"].strip(),
            } for domain in _ROB_DOMAINS
        }} if design == "randomized_trial" else {}),
    }


def record_claim_evidence_appraisal(manager, mission_id, claim_index, *,
                                    reviewer_id, profile):
    """Append an authenticated, source-bound appraisal while preserving claim status."""
    if not isinstance(reviewer_id, str) or not _OWNER.fullmatch(reviewer_id):
        raise PermissionError("Authenticated OIDC reviewer required")
    clean = validate_appraisal_profile(profile)
    saved = manager.get(mission_id)
    if saved["status"] != "review_pending" or len(saved["stages"]) != 4:
        raise RuntimeError("Only a completed draft can receive evidence appraisal")
    stages = saved["stages"]
    claims = stages[0].get("source_claim_audit")
    if (not isinstance(claims, list) or type(claim_index) is not int
            or not 0 <= claim_index < len(claims)):
        raise ValueError("Claim audit entry does not exist")
    claim = claims[claim_index]
    if not isinstance(claim, dict) or claim.get("status") != "quote_found_unverified":
        raise ValueError("A matched source quotation is required for appraisal")
    docs = stages[0].get("source_documents")
    doc = next((d for d in docs or [] if isinstance(d, dict)
                and isinstance(d.get("doi"), str)
                and d["doi"].casefold() == claim.get("doi", "").casefold()), None)
    if (not isinstance(doc, dict) or doc.get("status") != "full_text_excerpt"
            or not isinstance(doc.get("excerpt"), str) or not doc["excerpt"].strip()
            or not isinstance(doc.get("doi"), str) or not _DOI.fullmatch(doc["doi"])
            or doc.get("url") != claim.get("citation_url")):
        raise ValueError("A matched quote from retrieved full text is required")
    digest_source = json.dumps({
        "claim": claim["claim"], "doi": claim["doi"], "quote": claim["quote"],
        "url": doc["url"], "excerpt": doc["excerpt"],
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
    event = {
        "profile": clean, "reviewer_id": reviewer_id, "reviewed_at":
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evidence_digest": digest,
        "interpretation": "structured_human_appraisal_no_universal_score",
    }
    with manager.colony._db() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT status,stages FROM colony_missions WHERE id=?",
                         (mission_id,)).fetchone()
        if row is None or row["status"] != "review_pending":
            raise RuntimeError("Mission changed during appraisal")
        current = json.loads(row["stages"])
        if current != stages:
            raise RuntimeError("Evidence changed during appraisal; reload and retry")
        target = current[0]["source_claim_audit"][claim_index]
        events = target.setdefault("evidence_appraisal_events", [])
        if not isinstance(events, list):
            raise ValueError("Invalid appraisal history")
        events.append(event)
        target["evidence_appraisal"] = event
        db.execute("UPDATE colony_missions SET stages=? WHERE id=?",
                   (json.dumps(current, ensure_ascii=False), mission_id))
    return manager.get(mission_id)["stages"][0]["source_claim_audit"][claim_index][
        "evidence_appraisal"
