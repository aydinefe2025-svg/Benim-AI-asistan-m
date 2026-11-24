"""Synthetic-only two-root clock anchor gate for Graz sensor/electrical join.

HMAC is an *illustrative* verifier for independent signed witness streams in the
virtual laboratory. This repository does NOT possess authentic hardware clock
attestations, trusted lab issuers, calibrated instruments, or verified phases.
No real-battery measurement is released by this module.
"""
from __future__ import annotations

from dataclasses import dataclass, replace, asdict
import hashlib
import hmac
import json
import math
import statistics
from typing import Mapping, Sequence

from research.battery_curve_audit import graz_virtual_lab as virtual

ANCHOR_ISSUERS = ("independent-reference-A", "independent-reference-B")
EVENTS = (60, 600, 1140)


@dataclass(frozen=True)
class Anchor:
    issuer: str
    session_id: str
    cell_id: str
    event: int
    reference_t: float
    electric_observed_t: float
    sensor_observed_t: float
    uncertainty_s: float
    mac_hex: str = ""


def _finite(x: float) -> float:
    if isinstance(x, bool) or not isinstance(x, (int,float)) or not math.isfinite(x):
        raise ValueError("nonfinite or boolean time/uncertainty")
    return float(x)


def _payload(x: Anchor) -> bytes:
    return json.dumps({key: value for key,value in asdict(x).items() if key != "mac_hex"},
                      sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sign_anchor(x: Anchor, *, signing_key: bytes) -> Anchor:
    """Simulation fixture builder. Signing keys must NEVER be stored in result archives."""
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise ValueError("separate trust root of at least 256 bits required")
    if x.mac_hex:
        raise ValueError("refuse to modify an already signed anchor")
    return replace(x, mac_hex=hmac.new(signing_key, _payload(x), hashlib.sha256).hexdigest())


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str
    corrected_sensor_offset_s: float | None = None
    worst_clock_uncertainty_s: float | None = None
    max_observed_drift_ppm: float | None = None
    anchors_verified: int = 0
    independent_issuers_verified: int = 0


def verify_independent_anchors(
    anchors: Sequence[Anchor], *, trust_roots: Mapping[str, bytes],
    session_id: str, cell_id: str, expected_first_reference_t: float,
    expected_last_reference_t: float, max_offset_s: float=.7,
    max_observation_error_s: float=.15, max_anchor_uncertainty_s: float=.05,
    max_drift_ppm: float=100., min_span_s: float=900.
) -> Verdict:
    """Fail closed on forged, stale, single-issuer, inconsistent and high-drift evidence.

    Two independent roots and 3 nonrepeating anchored events per root are needed.
    This does not *create* trusted lab roots or independently certify true UTC.
    """
    def bad(reason: str) -> Verdict:
        return Verdict(False, reason)
    for q in (expected_first_reference_t,expected_last_reference_t,max_offset_s,
              max_observation_error_s,max_anchor_uncertainty_s,max_drift_ppm,min_span_s):
        _finite(q)
    if not session_id or cell_id not in virtual.PRELOADS_KN:
        return bad("unrecognized session or physical cell")
    if not (0 < max_offset_s <= .7 and 0 < max_observation_error_s <= .15 and
            0 < max_anchor_uncertainty_s <= .05 and 0 < max_drift_ppm <= 100. and min_span_s >= 900):
        return bad("clock validation bounds are not fail-closed")
    if not (len(anchors) == len(ANCHOR_ISSUERS)*len(EVENTS)):
        return bad("requires three independent timestamp anchors from both witness roots")
    if not isinstance(trust_roots,Mapping) or set(trust_roots) != set(ANCHOR_ISSUERS):
        return bad("two distinct externally pinned issuer identities required")
    if any(not isinstance(k,bytes) or len(k)<32 for k in trust_roots.values()):
        return bad("weak or unauthenticated trust root")
    if len(set(trust_roots.values())) != 2:
        return bad("different issuer labels cannot reuse the same trust key")
    by_issuer: dict[str,list[Anchor]] = {issuer: [] for issuer in ANCHOR_ISSUERS}
    seen=set()
    try:
        for x in anchors:
            if x.issuer not in by_issuer or x.session_id != session_id or x.cell_id != cell_id:
                return bad("wrong witness identity, session replay or physical cell")
            if x.event not in EVENTS or (x.issuer,x.event) in seen:
                return bad("replayed or duplicated anchor event")
            seen.add((x.issuer,x.event))
            reference=_finite(x.reference_t)
            electric=_finite(x.electric_observed_t)
            sensor=_finite(x.sensor_observed_t)
            uncert=_finite(x.uncertainty_s)
            if not 0 <= uncert <= max_anchor_uncertainty_s:
                return bad("anchor reported uncertainty exceeds budget")
            if not (expected_first_reference_t <= reference <= expected_last_reference_t):
                return bad("anchor outside independent session window")
            correct_mac=hmac.new(trust_roots[x.issuer],_payload(x),hashlib.sha256).hexdigest()
            if not isinstance(x.mac_hex,str) or not hmac.compare_digest(correct_mac,x.mac_hex):
                return bad("invalid witness authentication or altered anchor")
            if abs(electric-reference)+uncert > max_observation_error_s:
                return bad("electric device not aligned to trusted reference")
            if abs(sensor-reference)+uncert > max_offset_s:
                return bad("sensor clock offset outside independently witnessed budget")
            by_issuer[x.issuer].append(x)
    except (ValueError,TypeError,OverflowError,AttributeError) as exc:
        return bad("malformed or nonfinite witness: "+type(exc).__name__)
    per_issuer=[];drift=[]
    for issuer, group in by_issuer.items():
        group.sort(key=lambda z:z.event)
        if [x.event for x in group]!=list(EVENTS):
            return bad("missing anchor event")
        if group[-1].reference_t-group[0].reference_t < min_span_s:
            return bad("insufficient independent witness time span")
        offsets=[x.sensor_observed_t-x.electric_observed_t for x in group]
        span=group[-1].reference_t-group[0].reference_t
        ppms=abs(offsets[-1]-offsets[0])/span*1e6
        if ppms > max_drift_ppm:
            return bad("clock drift exceeds independent witness limit")
        per_issuer.append(statistics.median(offsets))
        drift.append(ppms)
    if abs(per_issuer[0]-per_issuer[1]) > 2*max_observation_error_s:
        return bad("independent witnesses disagree on clock offset")
    corrected_offset=statistics.median(per_issuer)
    if abs(corrected_offset) > max_offset_s:
        return bad("verified offset exceeds safe correction bound")
    worst_uncertainty=max(x.uncertainty_s for x in anchors) + max_observation_error_s
    return Verdict(True,"independent_anchor_evidence_accepted_synthetic_only",
                   round(corrected_offset,8),round(worst_uncertainty,8),
                   round(max(drift),4),len(anchors),len(by_issuer))


def verify_and_join(
    electric: list[virtual.Electric], sensors: list[virtual.Sensor],
    *, anchors: Sequence[Anchor], trust_roots: Mapping[str, bytes], session_id: str,
    expected_cell: str, true_reference_bounds: tuple[float,float],
    phase_source_authentic: bool, max_jitter_s: float=.50
) -> dict:
    """Admission only with authenticated anchors; booleans alone cannot approve clock.

    Legacy virtual.match_synthetic is intentionally called only after signed
    independent roots pass. The physical lab has no synthetic truth timestamps.
    """
    if not 0< _finite(max_jitter_s) <= .5:
        raise ValueError("unbounded matching tolerance")
    verdict=verify_independent_anchors(
        anchors,trust_roots=trust_roots,session_id=session_id,cell_id=expected_cell,
        expected_first_reference_t=true_reference_bounds[0],
        expected_last_reference_t=true_reference_bounds[1]
    )
    base={"gate_passed":verdict.passed,"gate_reason":verdict.reason,
          "verified_issuer_count":verdict.independent_issuers_verified,
          "anchor_count":verdict.anchors_verified,
          "corrected_sensor_offset_s":verdict.corrected_sensor_offset_s,
          "max_observed_drift_ppm":verdict.max_observed_drift_ppm,
          "simulation_only":True,"physical_production_release_allowed":False,
          "real_phase_and_sensor_calibration_verified":False}
    if not verdict.passed:
        return {**base,"accepted":0,"wrong_time_accepted":0,
                "rejected_before_join":len(sensors)}
    if not phase_source_authentic:
        return {**base,"gate_passed":False,"gate_reason":"independent experimental phase evidence absent",
                "accepted":0,"wrong_time_accepted":0,"rejected_before_join":len(sensors)}
    if any(s.physical_cell != expected_cell for s in sensors) or any(e.physical_cell != expected_cell for e in electric):
        return {**base,"gate_passed":False,"gate_reason":"source physical cell identity mismatch",
                "accepted":0,"wrong_time_accepted":0,"rejected_before_join":len(sensors)}
    adjusted=[replace(s,observed_t=s.observed_t-verdict.corrected_sensor_offset_s) for s in sensors]
    result=virtual.match_synthetic(electric,adjusted,clock_attested=True,
                                   phase_attested=True,tolerance_s=max_jitter_s)
    return {**base,**result,"rejected_before_join":0}


def mock_independent_witnesses(
    *, seed: int, session_id: str, cell_id: str,
    truth_first_t: float, clock_offset_s: float, drift_ppm: float=0.,
    issued_for_wrong_session: bool=False, tamper_after_sign: bool=False,
    omit_second_root: bool=False, correlated_fake_reference: bool=False
) -> tuple[list[Anchor], dict[str,bytes]]:
    """Controlled simulated oracle. NEVER import keys from this function in production."""
    import random
    rng=random.Random(seed)
    roots={issuer:hashlib.sha256(f"TEST-FIXTURE-NOT-LAB-{seed}-{issuer}".encode()).digest()
           for issuer in ANCHOR_ISSUERS}
    anchors=[]
    for issuer in ANCHOR_ISSUERS[:1 if omit_second_root else 2]:
        for event in EVENTS:
            ref=truth_first_t+event
            drift=drift_ppm*1e-6*event
            # Independent analog reference clocks are simulated with +/- 8ms noise.
            electric=ref+rng.uniform(-.008,.008)
            sensor=ref+clock_offset_s+drift+rng.uniform(-.008,.008)
            if correlated_fake_reference:
                # Models a compromised *both* references/roots; unresolvable from proofs.
                ref+=clock_offset_s; electric+=clock_offset_s
            anchor=Anchor(issuer,session_id+'-REPLAY' if issued_for_wrong_session else session_id,
                          cell_id,event,ref,electric,sensor,.012)
            signed=sign_anchor(anchor,signing_key=roots[issuer])
            if tamper_after_sign and event==EVENTS[0] and issuer==ANCHOR_ISSUERS[0]:
                signed=replace(signed,sensor_observed_t=signed.sensor_observed_t+2.)
            anchors.append(signed)
    return anchors, roots