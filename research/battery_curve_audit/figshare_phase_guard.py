"""Source-first elapsed-time + step/current gated comparison of 3 Figshare cells.

This is a *descriptive* battery data-quality experiment, NOT field FPR/FNR,
physical identity attestation, phase synchronization or commercial validation.
Raw publisher records are read in-memory and never saved in the result JSON.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import io
import json
import sys

TIME_TOLERANCE_S = Decimal('0.5')
CURRENT_TOLERANCE_A = Decimal('0.02')
VOLTAGE_NEAR_V = Decimal('0.002')
MIN_SAME_REGIME_POINTS = 1000


def _unique_times(window: dict) -> tuple[list, int]:
    """Keep only timepoints that appear exactly once; repeated clock ticks are ambiguous."""
    points = window.get('points')
    if not isinstance(points, list) or not points:
        raise ValueError('REVIEW_REQUIRED: empty source waveform')
    unique=[]
    excluded=0
    prev=None
    i=0
    while i<len(points):
        t=points[i][0]
        if not isinstance(t, Decimal) or not t.is_finite():
            raise ValueError('REVIEW_REQUIRED: invalid source elapsed time')
        if prev is not None and t<prev:
            raise ValueError('REVIEW_REQUIRED: original sampled time not monotonic')
        j=i+1
        while j<len(points) and points[j][0]==t:
            j+=1
        for k in range(i,j):
            _,v,cur,step=points[k]
            if (not isinstance(v,Decimal) or not v.is_finite()
                or not isinstance(cur,Decimal) or not cur.is_finite()
                or not isinstance(step,str) or not step.strip()):
                raise ValueError('REVIEW_REQUIRED: malformed waveform value or test step')
        if j==i+1:
            unique.append(points[i])
        else:
            excluded+=(j-i)
        prev=t
        i=j
    return unique,excluded


def compare_phase_controlled(left:dict,right:dict)->dict:
    """Deterministic one-to-one comparison; never interpolates or proves test equivalence."""
    l,excluded_l=_unique_times(left)
    r,excluded_r=_unique_times(right)
    base={'left_unique_elapsed_time_points':len(l),
          'right_unique_elapsed_time_points':len(r),
          'left_ambiguous_time_rows_excluded':excluded_l,
          'right_ambiguous_time_rows_excluded':excluded_r,
          'time_tolerance_seconds':str(TIME_TOLERANCE_S),
          'current_tolerance_amperes':str(CURRENT_TOLERANCE_A),
          'near_voltage_threshold_volts':str(VOLTAGE_NEAR_V),
          'physical_phase_alignment_authenticated':False,
          'independent_cell_identity_authenticated':False,
          'field_FPR_FNR_established':False}
    pairs=[]
    # Distinctly shifted starting clocks cannot be declared aligned by sliding
    # the entire trace; there is no independent physical start synchronization.
    if l and r and abs(l[0][0]-r[0][0])<=TIME_TOLERANCE_S:
        i=j=0
        while i<len(l) and j<len(r):
            delta=l[i][0]-r[j][0]
            if abs(delta)<=TIME_TOLERANCE_S:
                pairs.append((l[i],r[j],abs(delta)))
                i+=1;j+=1
            elif delta<0:
                i+=1
            else:
                j+=1
    count=len(pairs)
    same_step=[(a,b,delta) for a,b,delta in pairs if a[3]==b[3]]
    matched=[(a,b,delta) for a,b,delta in same_step
             if abs(a[2]-b[2])<=CURRENT_TOLERANCE_A]
    if count==0: decision='NO_BOUNDED_TIME_OVERLAP'
    elif len(matched)<MIN_SAME_REGIME_POINTS: decision='INSUFFICIENT_SAME_REGIME_PAIRS'
    else: decision='BOUNDED_REGIME_OVERLAP_RESEARCH_ONLY'
    stats={'matched_unique_elapsed_time_points':count,
           'left_unmatched_unique_elapsed_time_points':len(l)-count,
           'right_unmatched_unique_elapsed_time_points':len(r)-count,
           'same_step_points':len(same_step),
           'same_step_and_current_points':len(matched),
           'max_pair_time_delta_seconds':str(max((x[2] for x in pairs),default=None)) if pairs else None,
           'exact_voltage_pairs':None,
           'near_2mV_voltage_pairs':None,
           'max_voltage_delta_volts':None,
           'decision':decision}
    if decision=='BOUNDED_REGIME_OVERLAP_RESEARCH_ONLY':
        diffs=[abs(a[1]-b[1]) for a,b,_ in matched]
        stats.update({'exact_voltage_pairs':sum(v==0 for v in diffs),
                      'near_2mV_voltage_pairs':sum(v<=VOLTAGE_NEAR_V for v in diffs),
                      'max_voltage_delta_volts':str(max(diffs))})
    return {**base,**stats}


def run():
    """Fetch three original source MD5+CRC pinned containers, not the 10GB set."""
    from research.battery_curve_audit.figshare_three_archive_probe import (
        URL,PINNED,MAX_META_BYTES,MAX_SOURCE_BYTES,fetch_bounded,
        validate_source_meta, inspect_zip)
    from research.battery_curve_audit.figshare_three_curve_probe import read_matched_window
    meta_raw=fetch_bounded(URL,MAX_META_BYTES)
    meta=json.loads(meta_raw)
    pinned=validate_source_meta(meta)
    windows=[]; sources=[]
    for pub in pinned:
        raw=fetch_bounded(f'https://ndownloader.figshare.com/files/{pub["id"]}',MAX_SOURCE_BYTES)
        proof=inspect_zip(raw,pub)
        target=pub['name'][:-4]+'_01_ET_T23.csv'
        with ZipFile(io.BytesIO(raw)) as z:
            w=read_matched_window(z,target)
        windows.append(w)
        sources.append({'source_file_id':pub['id'],
                        'source_archive_sha256':proof['original_zip_sha256'],
                        'source_csv_name':target,
                        'paired_meta_sha256':w['paired_meta_sha256'],
                        'source_window_points':w['count'],
                        'source_distinct_step_codes':len({row[3] for row in w['points']})})
    comparisons=[]
    for i in range(len(windows)):
        for j in range(i+1,len(windows)):
            comparisons.append({'left_source_id':sources[i]['source_file_id'],
                                'right_source_id':sources[j]['source_file_id'],
                                **compare_phase_controlled(windows[i],windows[j])})
    return {'schema':'cano.battery.figshare279.original-three-phase-current-gate.v1',
            'source_article_id':25975315,'source_doi':meta['doi'],
            'publisher_metadata_sha256':sha256(meta_raw).hexdigest(),
            'source_windows':sources,'pair_results':comparisons,
            'total_source_time_voltage_points':sum(s['source_window_points'] for s in sources),
            'pair_count':len(comparisons),
            'elapsed_time_zero_is_not_independent_physical_phase_synchronization':True,
            'publisher_meta_to_physical_cell_identity_independently_verified':False,
            'independently_proven_same_test_conditions':False,
            'field_acceptance':'NOT_ESTABLISHED',
            'field_FPR_FNR_established':False,
            'production_release_allowed':False,
            'decision':'SOURCE_GATED_ELAPSED_TIME_STEP_CURRENT_RESEARCH_ONLY'}


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=1:
        print('usage: python -m research.battery_curve_audit.figshare_phase_guard OUTPUT.json',file=sys.stderr)
        return 2
    try:
        output=Path(args[0])
        if output.exists() or not output.parent.is_dir():
            raise ValueError('REVIEW_REQUIRED: output already exists or parent absent')
        result=run()
        with output.open('x',encoding='utf-8') as f:
            json.dump(result,f,indent=2,sort_keys=True)
            f.write('\n')
        print(result['decision'], 'source_points', result['total_source_time_voltage_points'],
              'time_matched_pairs',[x['matched_unique_elapsed_time_points'] for x in result['pair_results']],
              'same_regime_pairs',[x['same_step_and_current_points'] for x in result['pair_results']])
        return 0
    except (OSError,ValueError,TypeError,KeyError,InvalidOperation) as e:
        print('REVIEW_REQUIRED:',str(e)[:180],file=sys.stderr)
        return 2


if __name__=='__main__': raise SystemExit(main())