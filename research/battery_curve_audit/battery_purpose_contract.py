"""Fail-closed intended-use contract for CANO battery CSV screening.

A negative near-duplicate/data-integrity screen is never evidence that two
physical cells are the same or different. Public six-cell original ET->AT
remeasurement stress (PR #739) demonstrated 0/36 same-source longitudinal
matches at the frozen 2 mV threshold. No independently witnessed field labels.
"""
from __future__ import annotations

SCHEMA = "cano.battery.intended-use.v1"
SCREEN = "data-integrity-screen"
PURPOSES = frozenset((
    SCREEN, "physical-cell-identity", "field-acceptance",
    "certified-battery-health",
))
SCREEN_CLEAR_DECISIONS = frozenset((
    "PASS_SCREEN_ONLY", "SCREEN_ONLY_NO_CROSS_CELL_CANDIDATES",
))

def scope(decision: str) -> dict:
    """Machine-readable safety facts, even on a clean screening decision."""
    if not isinstance(decision, str) or not decision:
        raise ValueError("PURPOSE_REVIEW_REQUIRED: invalid screening decision")
    return {
        "schema": SCHEMA,
        "permitted_use": SCREEN,
        "data_integrity_screen_clear": decision in SCREEN_CLEAR_DECISIONS,
        "physical_cell_identity_independently_verified": False,
        "real_field_fpr_fnr_established": False,
        "battery_health_certified": False,
        "physical_identity_or_field_release_allowed": False,
    }

def require_purpose(purpose: str) -> None:
    """Block unsupported real-world claims before opening customer data.

    Explicit user/application intent must never turn a screening pass into a
    physical cell identity, field-acceptance, or health-certification result.
    """
    if not isinstance(purpose, str) or purpose not in PURPOSES:
        raise ValueError("PURPOSE_REVIEW_REQUIRED: unsupported intended use")
    if purpose != SCREEN:
        raise ValueError(
            "PURPOSE_REVIEW_REQUIRED: physical-cell identity, certified health "
            "and field acceptance NOT_ESTABLISHED; only data-integrity-screen "
            "is permitted without independent custody and labeled field trials"
        )

def verify_scope(report: dict) -> bool:
    """Reject missing, edited, or string-coerced release flags."""
    if not isinstance(report, dict) or report.get("use_scope") != scope(report.get("decision")):
        raise ValueError("PURPOSE_REVIEW_REQUIRED: missing or altered intended-use boundary")
    return True
