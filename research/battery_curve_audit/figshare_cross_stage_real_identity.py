"""A source-labeled, NOT physically certified, ET->AT identity stress test.

Works on the same 6 publisher-MD5-pinned original Figshare archives as PR #733.
Critically separates a waveform near-duplicate detector from a physical cell
identity/reidentification service. No model is fitted, tuned, or certified here.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path, PurePosixPath
from statistics import median
from zipfile import ZipFile
import csv
import io
import json
import math
import re
import sys

from research.battery_curve_audit.figshare_six_source_curve_screen import (
    PINS, STAGES, TEMPS, PHASES, TOLERANCE_MV, DURATION_FRACTION,
    inspect_zip, read_phases, phase_pair_max_mV, load_archive_directory,
)

EXPECTED_PUBLIC_CELLS=6
ET_AT_RECORDS_PER_CELL=6  # three temperatures, both phases


def check_distinct_publisher_labels(labels):
    if len(labels)!=EXPECTED_PUBLIC_CELLS:
        raise ValueError('SOURCE_REVIEW_REQUIRED: exactly six source cell labels required')
    normalized=[]
    for value in labels:
        if not isinstance(value,tuple) or len(value)!=2 or not all(
                isinstance(x,str) and x.strip() for x in value):
            raise ValueError('SOURCE_REVIEW_REQUIRED: missing lab or internal serial')
        normalized.append(tuple(x.strip().casefold() for x in value))
    if len(set(normalized))!=EXPECTED_PUBLIC_CELLS:
        raise ValueError('SOURCE_REVIEW_REQUIRED: colliding lab/internal serials across archives')


def score_fixed_condition(ET, AT):
    """6x6 original-record comparison, labels solely for *post hoc* evaluation.

    No label info enters the voltage distance function. Candidate ranking by
    max voltage discrepancy is descriptive, not an approved identity classifier.
    """
    names=sorted(x[1][:-4] for x in PINS)
    if (set(ET),set(AT)) != (set(names),set(names)):
        raise ValueError('SOURCE_REVIEW_REQUIRED: exact six-cell condition cohort required')
    rows=[]
    for src in names:
        candidates=[]
        for tgt in names:
            volts,duration=phase_pair_max_mV(ET[src],AT[tgt])
            if not all(math.isfinite(x) and x>=0 for x in (volts,duration)):
                raise ValueError('SOURCE_REVIEW_REQUIRED: invalid physical curve distance')
            candidates.append({'at_source':tgt,'max_voltage_difference_mV':round(volts,5),
                'relative_duration_difference':round(duration,8),
                'near_duplicate_rule_matches':volts<=TOLERANCE_MV and duration<=DURATION_FRACTION})
        candidates.sort(key=lambda x:(x['max_voltage_difference_mV'],
                                      x['relative_duration_difference'],x['at_source']))
        true_pos=next(i for i,x in enumerate(candidates,1) if x['at_source']==src)
        rows.append({'et_source':src,'matching_publisher_cell_AT_rank':true_pos,
                     'closest_AT_source':candidates[0]['at_source'],
                     'same_source_max_voltage_difference_mV':next(x['max_voltage_difference_mV']
                             for x in candidates if x['at_source']==src),
                     'same_source_near_duplicate_rule_matches':next(x['near_duplicate_rule_matches']
                             for x in candidates if x['at_source']==src),
                     'cross_source_near_duplicate_alerts':sum(x['near_duplicate_rule_matches']
                             for x in candidates if x['at_source']!=src),
                     'candidate_count':len(candidates)})
    return rows


def measure_real_cross_stage(originals):
    if set(originals)!={p[1] for p in PINS}:
        raise ValueError('SOURCE_REVIEW_REQUIRED: exactly six source archives')
    views={};source_labels=[];source_provenance=[];measured_rows=0
    for publisher_id,name,size,publisher_md5 in PINS:
        raw=originals[name]
        if not isinstance(raw,bytes) or len(raw)!=size:
            raise ValueError('SOURCE_REVIEW_REQUIRED: original archive size mismatch')
        archive=inspect_zip(raw,{'id':publisher_id,'name':name,
                                  'size':size,'md5':publisher_md5})
        source=name[:-4];label=None;start_dates={};record_count=0;source_rows=0
        with ZipFile(io.BytesIO(raw)) as z:
            for stage_ix,stage in STAGES:
                for temperature in TEMPS:
                    expected=f'{source}_{stage_ix}_{stage}_T{temperature}.csv'
                    names=[x for x in z.namelist() if PurePosixPath(x).name==expected]
                    if len(names)!=1:raise ValueError('SOURCE_REVIEW_REQUIRED: missing/ambiguous source measurement')
                    original_name=names[0]
                    rec=read_phases(z,original_name,cell=source,stage=stage,temp=temperature)
                    present=(rec['publisher_lab'],rec['publisher_internal_serial'])
                    if label is not None and label!=present:
                        raise ValueError('SOURCE_REVIEW_REQUIRED: lab/serial changed within original ZIP')
                    label=present
                    paired_name=original_name[:-4]+'_meta.txt'
                    if paired_name not in z.namelist() or z.getinfo(paired_name).file_size>50000:
                        raise ValueError('SOURCE_REVIEW_REQUIRED: source date sidecar absent')
                    metadata=z.read(paired_name).decode('utf-8-sig')
                    match=re.search(r'^Measurement start date:\s*(\d{2}\.\d{2}\.\d{4})\s*$',metadata,re.M)
                    if not match:raise ValueError('SOURCE_REVIEW_REQUIRED: source acquisition date missing')
                    start_dates[f'{stage}_T{temperature}']=match.group(1)
                    for phase in PHASES:views[(source,stage,temperature,phase)]=rec['phases'][phase]
                    source_rows+=rec['raw_csv_rows'];record_count+=1
        if any(start_dates.get(f'ET_T{temperature}') == start_dates.get(f'AT_T{temperature}') for temperature in TEMPS):
            raise ValueError('SOURCE_REVIEW_REQUIRED: longitudinal ET and AT dates overlap')
        source_labels.append(label)
        source_provenance.append({'public_source':source,'publisher_file_id':publisher_id,
            'original_sha256':archive['original_zip_sha256'],
            'publisher_lab_internal_serial_consistent':True,
            'source_acquisition_dates_by_stage_and_temperature':start_dates,
            'original_CSV_count':record_count,'original_rows':source_rows})
        measured_rows+=source_rows
    check_distinct_publisher_labels(source_labels)
    by_src=defaultdict(list)
    for r in source_provenance:by_src[r['public_source']].append(r)
    all_rank=[];same_near_count=0;cross_alert_count=0;per_condition=[];actual_positive=[]
    for T in TEMPS:
        for phase in PHASES:
            et={name[:-4]:views[(name[:-4],'ET',T,phase)] for _,name,_,_ in PINS}
            at={name[:-4]:views[(name[:-4],'AT',T,phase)] for _,name,_,_ in PINS}
            scores=score_fixed_condition(et,at)
            all_rank.extend(row['matching_publisher_cell_AT_rank'] for row in scores)
            same_near_count+=sum(row['same_source_near_duplicate_rule_matches'] for row in scores)
            cross_alert_count+=sum(row['cross_source_near_duplicate_alerts'] for row in scores)
            actual_positive.extend(row['same_source_max_voltage_difference_mV'] for row in scores)
            per_condition.append({'temperature_C':T,'phase':phase,
                'ET_AT_distinct_record_pairs':36,'same_source_labeled_pairs':6,
                'different_source_labeled_pairs':30,
                'near_duplicate_self_alerts':sum(row['same_source_near_duplicate_rule_matches'] for row in scores),
                'near_duplicate_different_source_alerts':sum(row['cross_source_near_duplicate_alerts'] for row in scores),
                'same_source_nearest_AT_count':sum(row['matching_publisher_cell_AT_rank']==1 for row in scores),
                'ET_to_AT_match_rank_details':scores})
    if len(all_rank)!=36 or measured_rows!=11_554_465:
        raise ValueError('SOURCE_REVIEW_REQUIRED: source condition denominator or original row drift')
    report={
        'schema':'cano.battery.figshare-source-labeled-longitudinal-cross-stage.v1',
        'source_doi':'10.6084/m9.figshare.25975315','license':'CC BY 4.0',
        'source_archive_count':len(PINS),'original_CSV_count':36,
        'measured_source_rows':measured_rows,'source_provenance':source_provenance,
        'cross_stage_ET_AT_all_candidate_pairs':216,
        'cross_stage_same_source_record_pairs':36,
        'cross_stage_different_source_record_pairs':180,
        'same_source_near_duplicate_rule_matches':same_near_count,
        'different_source_near_duplicate_rule_alerts':cross_alert_count,
        'same_source_top1_rank_count':all_rank.count(1),
        'same_source_rank_distribution':{str(i):all_rank.count(i) for i in range(1,7)},
        'same_source_absolute_voltage_discrepancy_mV_min':round(min(actual_positive),5),
        'same_source_absolute_voltage_discrepancy_mV_median':round(median(actual_positive),5),
        'same_source_absolute_voltage_discrepancy_mV_max':round(max(actual_positive),5),
        'predeclared_full_waveform_threshold_mV':TOLERANCE_MV,
        'predeclared_phase_duration_fraction':DURATION_FRACTION,
        'per_condition':per_condition,
        'meaning':'REAL ET and AT separate records with the same publisher lab/internal serial but different acquisition dates: NOT waveform data copies; original data labels are not third-party verified chain of custody',
        'waveform_near_duplicate_sufficient_for_physical_cell_identity':False,
        'demonstrated_reidentification_acceptance':False,
        'field_false_negative_rate_certified':False,
        'field_false_positive_rate_certified':False,
        'production_cell_identity_claim_allowed':False,
        'decision':'BLOCK_WAVEFORM_ONLY_PHYSICAL_IDENTITY_REQUIRE_INDEPENDENT_WITNESS',
    }
    return report


def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if len(args)!=2:
        print('usage: python -m research.battery_curve_audit.figshare_cross_stage_real_identity ORIGINAL_DIR RESULT.json',file=sys.stderr)
        return 2
    try:
        dest=Path(args[1]);root=Path(args[0])
        if dest.exists() or not dest.parent.is_dir():
            raise ValueError('SOURCE_REVIEW_REQUIRED: output cannot overwrite an existing audit')
        report=measure_real_cross_stage(load_archive_directory(root))
        with dest.open('x',encoding='utf-8') as fh:
            json.dump(report,fh,sort_keys=True,indent=2);fh.write('\n')
        print('REAL_LONGITUDINAL_SOURCE_IDENTITY_EVALUATED',json.dumps({
            'original_rows':report['measured_source_rows'],
            'actual_same_source_remeasurements':report['cross_stage_same_source_record_pairs'],
            'same_cell_near_duplicate_matches':report['same_source_near_duplicate_rule_matches'],
            'different_cell_near_duplicate_alerts':report['different_source_near_duplicate_rule_alerts'],
            'top1_correct_source':report['same_source_top1_rank_count'],
            'identity_claim_allowed':report['production_cell_identity_claim_allowed']}))
        return 0
    except (OSError,KeyError,TypeError,ValueError,csv.Error) as e:
        print('SOURCE_REVIEW_REQUIRED: '+str(e)[:300],file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())