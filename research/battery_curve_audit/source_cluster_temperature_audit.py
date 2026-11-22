#!/usr/bin/env python3
"""Conditional, source-clustered label-exchangeability audit (not a physics test).

Input: source-derived, already published 9-cell/27-pair summary, *not* raw measurements.
No laboratory calibration, real measurement, or field accuracy is inferred.
"""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
from itertools import product
import hashlib
import json
import math
from pathlib import Path

TEMPERATURES = (10, 23, 45)
EXPECTED_SHA256 = '424e1cf66146d3cd3477297f6c315c0ef18d794c0b7dffc05d374964131eb5da'


def validate(data):
    if not isinstance(data, dict) or data.get('source_file_records') != 9 or data.get('source_temperature_pairs') != 27:
        raise ValueError('Expected 9 physical source files and 27 paired observations')
    if data.get('temperature_causality_established') is not False or data.get('production_release_allowed') is not False:
        raise ValueError('Unsupported causal/production claim in source summary')
    records = data.get('source_results')
    if not isinstance(records, list) or len(records) != 27:
        raise ValueError('Invalid number of records')
    by_id = defaultdict(dict)
    for row in records:
        if not isinstance(row, dict):
            raise ValueError('Malformed row')
        sid = row.get('source_file_id'); temp = row.get('temperature_C')
        if type(sid) is not int or temp not in TEMPERATURES or type(temp) is not int:
            raise ValueError('Invalid source ID or temperature')
        if temp in by_id[sid]:
            raise ValueError('Duplicate source-temperature pair')
        charge=row.get('charge_change_percent'); discharge=row.get('discharge_change_percent')
        for val in (charge, discharge, row.get('mean_change_percent')):
            if type(val) not in (float, int) or not math.isfinite(val):
                raise ValueError('Invalid numeric source value')
        if type(row.get('mixed_or_zero_channel_sign')) is not bool:
            raise ValueError('Unverifiable sign flag')
        if row['mixed_or_zero_channel_sign'] != (charge >= 0 or discharge >= 0):
            raise ValueError('Channel sign inconsistency')
        if row.get('both_channels_decline') is not (charge < 0 and discharge < 0):
            raise ValueError('Channel decline inconsistency')
        if (charge + discharge)/2 >= 0:
            raise ValueError('Non-negative mean (unexpected in pinned source)')
        by_id[sid][temp] = row
    if len(by_id) != 9 or any(set(by_id[s]) != set(TEMPERATURES) for s in by_id):
        raise ValueError('9 source clusters must have exactly three temperatures each')
    events = [sid for sid in sorted(by_id) if any(r['mixed_or_zero_channel_sign'] for r in by_id[sid].values())]
    if any(sum(r['mixed_or_zero_channel_sign'] for r in by_id[sid].values()) != 1 for sid in events):
        raise ValueError('This exact single-event-per-source calculation is not applicable')
    if Counter(r['mixed_or_zero_channel_sign'] for r in records)[True] != data.get('mixed_or_zero_channel_sign_pairs'):
        raise ValueError('Summary disagrees with source records')
    return by_id, events


def evaluate(data, source_sha256):
    by_id, events = validate(data)
    k = len(events)
    observed=Counter(t for sid in events for t,r in by_id[sid].items() if r['mixed_or_zero_channel_sign'])
    if k <= 0:
        raise ValueError('No discordant source record: this audit is not applicable')
    observed_max=max(observed.values())
    # Exhaustive, exact null over all 3**k temperature relabelings of the
    # *discordant* source clusters only; non-discordant clusters contribute zero.
    assignments=list(product(TEMPERATURES, repeat=k))
    any_temp_extreme=sum(max(Counter(a).values()) >= observed_max for a in assignments)
    fixed_10_extreme=sum(Counter(a)[10] >= observed[10] for a in assignments)
    any_p=Fraction(any_temp_extreme,len(assignments))
    fixed_p=Fraction(fixed_10_extreme,len(assignments))
    scenarios=[]
    for label, weights in [
        ('equal-label-weights', (Fraction(1,3),)*3),
        ('moderate-10C-preference', (Fraction(2,5),Fraction(3,10),Fraction(3,10))),
        ('stronger-10C-preference', (Fraction(1,2),Fraction(1,4),Fraction(1,4))),
        ('pronounced-10C-preference', (Fraction(3,5),Fraction(1,5),Fraction(1,5))),
    ]:
        if sum(weights) != 1: raise AssertionError('Null weights do not sum to one')
        # Observed maximal clustering is all k on one temperature.
        if observed_max == k:
            prob=sum(w**k for w in weights)
        else:
            prob=sum(math.prod(weights[TEMPERATURES.index(t)] for t in a) for a in assignments
                     if max(Counter(a).values()) >= observed_max)
        scenarios.append({'scenario':label, 'weights_by_temperature':{str(t):str(w) for t,w in zip(TEMPERATURES,weights)},
                          'any_temperature_probability_exact':str(prob),'any_temperature_probability':float(prob)})
    leave_one_out=[]
    for sid in sorted(by_id):
        kept=[v for v in events if v != sid]
        n=len(kept)
        # Only for currently observed same-temperature case.
        value=3*Fraction(1,3)**n if n else Fraction(1)
        leave_one_out.append({'removed_source_file_id':sid,'removed_source_discordant':sid in events,
                              'remaining_discordant_sources':n,
                              'any_temperature_probability':float(value)})
    return {
        'schema':'cano.battery.nine-source-conditional-temperature-label-sensitivity.v1',
        'source_summary_sha256':source_sha256,
        'source_summary_provenance':'library publisher-source-derived summary; original 54 CSV NOT reopened in this study',
        'physical_source_clusters':len(by_id), 'temperature_pair_rows':len(data['source_results']),
        'discordant_source_clusters':k,
        'discordant_by_temperature':{str(t):int(observed[t]) for t in TEMPERATURES},
        'discordant_ids':events,
        'discordant_by_cohort':dict(sorted(Counter(by_id[s][10]['cohort'] for s in events).items())),
        'exact_label_assignment_count':len(assignments),
        'conditional_uniform_null':{
            'any_temperature_extreme_assignments':any_temp_extreme,
            'any_temperature_probability_exact':str(any_p),
            'any_temperature_probability':float(any_p),
            'prespecified_10C_extreme_assignments':fixed_10_extreme,
            'prespecified_10C_probability_exact':str(fixed_p),
            'prespecified_10C_probability':float(fixed_p),
        },
        'unequal_temperature_label_sensitivity':scenarios,
        'leave_one_source_out':leave_one_out,
        'assumptions':['one discordance event maximum per physical source',
                       'temperature labels exchangeable within each source under conditional null',
                       'independent label assignments across physical source clusters',
                       'discordance count fixed at observed k',
                       'uniform weights are a counterfactual model, NOT the measured test protocol'],
        'limitations':['23C test order and RPT carryover may violate exchangeability',
                       'source cohorts/instrument families may share systematic biases',
                       'k01 ET/AT chronology is not independently verified in the source-derived ledger',
                       'post-hoc temperature selection: any-temperature calculation is primary',
                       'hypothetical null probability is NOT proof of causal temperature influence',
                       'this audit is NOT a new raw measurement, device calibration or independent laboratory experiment'],
        'temperature_causality_established':False,
        'instrument_calibration_established':False,
        'independent_physical_replication_established':False,
        'field_acceptance':'NOT_ESTABLISHED',
        'production_release_allowed':False,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    raw=args.source.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(f'SOURCE_SHA256_MISMATCH expected={EXPECTED_SHA256} actual={digest}')
    result=evaluate(json.loads(raw), digest)
    args.output.write_text(json.dumps(result, ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(f"PASS 9 sources; 27 paired rows; 4 clustered discordances; any-temp P={result['conditional_uniform_null']['any_temperature_probability_exact']}")

if __name__=='__main__': main()