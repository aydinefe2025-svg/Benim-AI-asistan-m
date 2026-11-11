"""Reuse CANO's archived published findings for *planning* off-grid energy.

This is a units/provenance-aware, conservative feasibility screen. Published peak
power and density figures are NOT continuous field measurements. This module
never touches real devices, creates workers, or promotes a candidate as proven.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "data" / "cano_research_bridge_evidence.json"
ELECTRICAL = frozenset({"electric_peak_mw", "electric_peak_density_uw_cm2"})
EXCLUSIONS = frozenset({"mechanical_actuation_only", "energy_transfer_not_generation"})


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError(f"Invalid {field}")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid {field}") from None
    if not d.is_finite() or d < 0:
        raise ValueError(f"Invalid {field}")
    return d


def _fmt(value):
    return format(value.normalize(), "f")


def _check_catalog(catalog):
    if not isinstance(catalog, dict) or catalog.get("schema") != 1:
        raise ValueError("Unsupported evidence catalog")
    observations = catalog.get("observations")
    if not isinstance(observations, list) or not 1 <= len(observations) <= 100:
        raise ValueError("Invalid source inventory")
    ids = set()
    for obs in observations:
        if not isinstance(obs, dict) or not isinstance(obs.get("id"), str) or not obs["id"]:
            raise ValueError("Invalid observation identity")
        if obs["id"] in ids:
            raise ValueError("Duplicate observation")
        ids.add(obs["id"])
        if obs.get("class") not in ELECTRICAL | EXCLUSIONS:
            raise ValueError("Unknown evidence mechanism")
        for key in ("source", "archive"):
            if not isinstance(obs.get(key), str) or not obs[key].startswith("https://"):
                raise ValueError("Missing source provenance")
        if not isinstance(obs.get("boundary"), str) or not obs["boundary"].strip():
            raise ValueError("Missing scientific limitation")
        if not isinstance(obs.get("source_kind"), str) or not obs["source_kind"].strip():
            raise ValueError("Missing evidence class")
        if obs["class"] in ELECTRICAL:
            _number(obs.get("value"), "archived research value")
        elif "value" in obs:
            raise ValueError("Mechanical/transfer result cannot be counted as electricity")
    return observations


def load_evidence(path=None):
    """Read the existing research catalog only; no browsing or inferred readings."""
    source = Path(path) if path is not None else DEFAULT_CATALOG
    if source.stat().st_size > 65536:
        raise ValueError("Research catalog exceeds size limit")
    catalog = json.loads(source.read_text(encoding="utf-8"))
    _check_catalog(catalog)
    return catalog


def compare_workload(catalog, *, area_cm2, standby_mw, active_mw, active_fraction, hours):
    """Return only an optimistic cross-paper instantaneous-power ceiling.

    Inputs must be explicitly chosen for a proposed device; no claim of usable
    site energy is made without separate simultaneous field measurements.
    """
    observations = _check_catalog(catalog)
    area = _number(area_cm2, "active_area_cm2")
    standby = _number(standby_mw, "standby_mw")
    active = _number(active_mw, "active_mw")
    duty = _number(active_fraction, "active_fraction")
    duration = _number(hours, "hours")
    if area > 1_000_000 or duty > 1 or duration <= 0 or duration > 8760:
        raise ValueError("Invalid bounded workload or area")

    upper = Decimal(0)
    contributions = []
    excluded = []
    for row in observations:
        kind = row["class"]
        if kind == "electric_peak_mw":
            estimate = _number(row["value"], "research electric peak")
        elif kind == "electric_peak_density_uw_cm2":
            estimate = _number(row["value"], "research electric peak density") * area / Decimal(1000)
        else:
            excluded.append(row["id"])
            continue
        upper += estimate
        contributions.append({"id": row["id"], "optimistic_mw": _fmt(estimate),
                              "study_source": row["source"], "source_kind": row["source_kind"]})
    average = standby * (Decimal(1) - duty) + active * duty
    decision = ("insufficient_even_if_peaks_were_continuous" if average > upper
                else "candidate_only_field_measurements_required")
    return {
        "decision": decision,
        "study_ideal_upper_mw": _fmt(upper),
        "study_ideal_upper_mwh": _fmt(upper * duration),
        "field_guaranteed_mw": "0",
        "load_average_mw": _fmt(average),
        "load_mwh": _fmt(average * duration),
        "hours": _fmt(duration),
        "active_area_cm2": _fmt(area),
        "simultaneous_collection_unverified": True,
        "proven_feasible": False,
        "units": "mW (instantaneous) and mWh (energy over assumed duration)",
        "contributions": contributions,
        "excluded_from_electric_harvest": excluded,
        "warning": "Different papers/conditions; peaks are NOT guaranteed, continuous, or measured together."
    }


def growth_claim_gate(catalog):
    """Carry earlier failed *digital* generalization gates into promotion review."""
    _check_catalog(catalog)
    prior = catalog.get("prior_validation")
    required = ("adaptation_demonstrated", "compositional_transfer_confirmed")
    if (not isinstance(prior, dict) or any(type(prior.get(x)) is not bool for x in required)
            or any(not isinstance(prior.get(x), str) or not prior[x].startswith("https://")
                   for x in ("adaptation_source", "transfer_source"))):
        raise ValueError("Missing archived validation gates or provenance")
    failed = [x for x in required if not prior[x]]
    return {
        "decision": ("do_not_claim_robust_self_improvement" if failed
                     else "independent_review_still_required"),
        "unpassed_gates": failed,
        "agent_model_weights_updated": False,
        "automatic_promotion": False,
        "sources": [prior["adaptation_source"], prior["transfer_source"]],
    }
