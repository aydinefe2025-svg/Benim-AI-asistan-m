"""V4 synthetic-only *third* independent physical-trigger channel for Graz.

This module tests a trust-domain separation strategy. HMAC keys, simulated pulses,
UTC truth, current units and phase labels here are TEST FIXTURES, not a physical
calibration or real lab attestation. No path authorizes production release.
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
from research.battery_curve_audit import graz_clock_anchor_gate as two

ISSUER = 'independent-physical-trigger-C'
PULSE_EVENTS = (60, 1140)

@dataclass(frozen=True)
class Pulse:
    issuer: str
    session_id: str
    cell_id: str
    event: int
    reference_t: float
    electric_observed_t: float
    sensor_observed_t: float
    uncertainty_s: float
    stream_sha256: str
    mac_hex: str = ''


def _finite(value: float) -> float:
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
        raise ValueError('finite number required')
    return float(value)


def _mac_payload(x:Pulse)->bytes:
    return json.dumps({key:value for key,value in asdict(x).items() if key!='mac_hex'},
                      sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def signed_stream_digest(electric:Sequence[virtual.Electric],sensors:Sequence[virtual.Sensor])->str:
    """Source identity binding on observable fields ONLY; excludes simulation truth_t."""
    e=[(x.observed_t,x.physical_cell,x.stage,x.voltage_v,x.current_a) for x in electric]
    s=[(x.observed_t,x.physical_cell,x.source_cell,x.stage,x.source_stage,x.sensor_um) for x in sensors]
    raw=json.dumps({'electrical':e,'sensors':s},separators=(',',':'),allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def sign_pulse(x:Pulse,*,signing_key:bytes)->Pulse:
    """Only to generate synthetic test witnesses; never publish real signing keys."""
    if not isinstance(signing_key,bytes) or len(signing_key)<32 or x.mac_hex:
        raise ValueError('not unsigned / valid 256-bit test signing key')
    return replace(x,mac_hex=hmac.new(signing_key,_mac_payload(x),hashlib.sha256).hexdigest())


def verify_and_join_three_reference(
    electric:list[virtual.Electric],sensors:list[virtual.Sensor],*,
    anchors:Sequence[two.Anchor],trust_roots:Mapping[str,bytes],
    pulses:Sequence[Pulse],trigger_key:bytes,session_id:str,expected_cell:str,
    reference_bounds:tuple[float,float],phase_source_authentic:bool,
    max_reference_disagreement_s:float=.15, max_trigger_uncertainty_s:float=.03,
    max_join_jitter_s:float=.5,
)->dict:
    """Gate virtual time joins on C's independent trigger plus two signed A/B roots.

    Returns zero accepted (fail closed) for absent, reused, mismatched, stale,
    corrupt or high-uncertainty C evidence. A forged A/B+C domain is impossible
    to distinguish from a real one *within the signed data alone*.
    """
    def denied(reason):
        return {'gate_passed':False,'gate_reason':reason,'accepted':0,
                'wrong_time_accepted':0,'rejected_before_join':len(sensors),
                'simulation_only':True,'physical_production_release_allowed':False,
                'real_hardware_trigger_calibration_verified':False,
                'independent_real_phase_metadata_verified':False,
                'real_capacity_ah_verified':False}
    try:
        valid_bounds=(len(reference_bounds)==2 and all(math.isfinite(_finite(x)) for x in reference_bounds)
                      and reference_bounds[1]>reference_bounds[0])
    except (TypeError,ValueError,IndexError):
        valid_bounds=False
    if not valid_bounds:
        return denied('invalid external reference bounds')
    if not (0 < _finite(max_reference_disagreement_s) <= .15 and
            0 < _finite(max_trigger_uncertainty_s) <= .03 and
            0 < _finite(max_join_jitter_s) <= .5):
        return denied('unsafe witness tolerance')
    if expected_cell not in virtual.PRELOADS_KN or not isinstance(session_id,str) or not session_id:
        return denied('source identity missing')
    if not (isinstance(trigger_key,bytes) and len(trigger_key)>=32 and
            isinstance(trust_roots,Mapping) and
            set(trust_roots)==set(two.ANCHOR_ISSUERS) and
            all(isinstance(z,bytes) and len(z)>=32 and z!=trigger_key for z in trust_roots.values())):
        return denied('external third trust root missing or shared with existing roots')
    verdict=two.verify_independent_anchors(anchors,trust_roots=trust_roots,
        session_id=session_id,cell_id=expected_cell,
        expected_first_reference_t=reference_bounds[0],
        expected_last_reference_t=reference_bounds[1])
    if not verdict.passed:
        return denied('original two-root gate failed: '+verdict.reason)
    if len(pulses)!=len(PULSE_EVENTS):
        return denied('requires two independent hardware-trigger pulses')
    if phase_source_authentic is not True:
        return denied('no independent experiment phase proof')
    try:
        stream_hash=signed_stream_digest(electric,sensors)
        if any(x.physical_cell != expected_cell for x in electric) or any(x.physical_cell!=expected_cell for x in sensors):
            return denied('different physical source cell')
        seen=set(); offset_c=[]
        for p in pulses:
            if (p.issuer!=ISSUER or p.session_id!=session_id or p.cell_id!=expected_cell
                    or p.event not in PULSE_EVENTS or p.event in seen):
                return denied('wrong third-issuer/session/cell or duplicate event')
            seen.add(p.event)
            if p.stream_sha256!=stream_hash:
                return denied('pulse signature not attached to actual logged streams')
            vals=[_finite(x) for x in (p.reference_t,p.electric_observed_t,p.sensor_observed_t,p.uncertainty_s)]
            if not 0<=vals[3]<=max_trigger_uncertainty_s:
                return denied('third channel trigger uncertainty out of range')
            if not reference_bounds[0]<=p.reference_t<=reference_bounds[1]:
                return denied('third channel reference outside declared session')
            correct=hmac.new(trigger_key,_mac_payload(p),hashlib.sha256).hexdigest()
            if not isinstance(p.mac_hex,str) or not hmac.compare_digest(correct,p.mac_hex):
                return denied('third channel signature bad / tampered')
            if abs(p.reference_t-p.electric_observed_t)+p.uncertainty_s > max_reference_disagreement_s:
                return denied('third channel external reference disagrees with raw electrical clock')
            matching_anchors=[a for a in anchors if a.event==p.event]
            if len(matching_anchors)!=len(two.ANCHOR_ISSUERS):
                return denied('third channel has no matched first/second witness events')
            if any(abs(a.reference_t-p.reference_t)>max_reference_disagreement_s for a in matching_anchors):
                return denied('independent third reference exposes shared A/B clock compromise')
            # Ensure the *pulse* times really fall inside the bound observable stream, not just a fabricated anchor claim.
            if not any(abs(e.observed_t-p.electric_observed_t) <= .75 for e in electric):
                return denied('third pulse detached from electrical time series')
            if not any(abs(s.observed_t-p.sensor_observed_t) <= .75 for s in sensors):
                return denied('third pulse detached from sensor time series')
            offset_c.append(p.sensor_observed_t-p.electric_observed_t)
        if seen!=set(PULSE_EVENTS):return denied('third channel missing events')
        corrected=statistics.median(offset_c)
        if abs(corrected - verdict.corrected_sensor_offset_s)>max_reference_disagreement_s:
            return denied('third channel clock offset disagrees with original A/B anchors')
        if abs(corrected)>.7 or abs(offset_c[1]-offset_c[0])/(PULSE_EVENTS[1]-PULSE_EVENTS[0])*1e6>100:
            return denied('third physical trigger exceeds clock offset/drift budget')
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError) as exc:
        return denied('malformed third channel evidence: '+type(exc).__name__)
    # A/B validates phase boolean only in the synthetic model; real phase still not proven.
    outcome=two.verify_and_join(electric,sensors,anchors=anchors,trust_roots=trust_roots,
        session_id=session_id,expected_cell=expected_cell,true_reference_bounds=reference_bounds,
        phase_source_authentic=phase_source_authentic,max_jitter_s=max_join_jitter_s)
    return {**outcome,'third_reference_verified_in_simulation':True,
            'third_reference_pulses':len(pulses),
            'real_hardware_trigger_calibration_verified':False,
            'independent_real_phase_metadata_verified':False,
            'real_capacity_ah_verified':False,
            'physical_production_release_allowed':False}


def mock_independent_pulses(*,seed:int,session_id:str,cell_id:str,truth_first_t:float,
    clock_offset_s:float,electric:list[virtual.Electric],sensors:list[virtual.Sensor],
    correlated_fake_reference:bool=False)->tuple[list[Pulse],bytes]:
    """Fixture. Correlated fake mode models a third, fully compromised reference."""
    import random
    rng=random.Random(seed+442721)
    key=hashlib.sha256(f'SYNTHETIC-C-NOT-A-HARDWARE-KEY-{seed}'.encode()).digest()
    h=signed_stream_digest(electric,sensors)
    pulses=[]
    for event in PULSE_EVENTS:
        ref=truth_first_t+event
        e=ref+rng.uniform(-.007,.007)
        s=ref+clock_offset_s+rng.uniform(-.007,.007)
        if correlated_fake_reference:
            ref+=clock_offset_s
            e+=clock_offset_s
        x=Pulse(ISSUER,session_id,cell_id,event,ref,e,s,.012,h)
        pulses.append(sign_pulse(x,signing_key=key))
    return pulses,key