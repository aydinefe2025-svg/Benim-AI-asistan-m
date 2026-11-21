"""Source-labeled six-cell waveform screening on 36 original Figshare CSV files.

Source: Stroebl et al. 2024, doi:10.6084/m9.figshare.25975315, CC BY 4.0.
ALL 6 source ZIPs must match publisher ID, filename, byte size and MD5; ZIP CRC
and basic structure are checked by the existing source parser. Unit of
inference: *published source-record cell*, NOT independently witnessed cell.
The results are descriptive SOURCE LABEL DISAGREEMENT COUNTS, not field FPR/FNR.
"""
from __future__ import annotations

from collections import defaultdict
import csv
from hashlib import md5,sha256
import io
import json
import math
from pathlib import Path, PurePosixPath
import sys
from zipfile import ZipFile

from research.battery_curve_audit.figshare_three_archive_probe import (
    PINNED as K01, inspect_zip,
)
from research.battery_curve_audit.figshare_k04_original_capacity import (
    ORIGINALS as K04,
)
from research.battery_curve_audit.figshare_k01_et_at_capacity import _meta_record
from research.battery_curve_audit.figshare_three_curve_probe import parse_source_runtime

PINS = (*K01, *K04)
DOI = '10.6084/m9.figshare.25975315'
STAGES = (('01','ET'),('02','AT'))
TEMPS = (10,23,45)
PHASES = (21,22)
TOLERANCE_MV = 2.0  # pre-existing near_duplicate_guard.py research threshold
DURATION_FRACTION = 0.005  # pre-existing research rule
MAX_CSV_MEMBER_BYTES = 60_000_000
MAX_ROWS = 800_000
MAX_CELLS = 6
MIN_PHASE_POINTS = 50
MAX_PHASE_GAP_S = 120


def phase_pair_max_mV(a: tuple[tuple[float,float],...],
                      b: tuple[tuple[float,float],...]) -> tuple[float,float]:
    """Piecewise-linear maximum discrepancy at the union of measured knots.

    Compare relative *physical elapsed seconds*, not row numbers or cycle
    progress; reject duplicate/nonmonotone timestamps, extrapolation and short
    records. Difference of two piecewise-linear curves is piecewise-linear,
    hence its absolute maximum occurs at a union knot or overlap boundary.
    """
    if any(len(x)<MIN_PHASE_POINTS or x[0][0]!=0 or x[-1][0]<=0 for x in (a,b)):
        raise ValueError('SOURCE_REVIEW_REQUIRED: incomplete source phase')
    for seq in (a,b):
        if any(seq[i+1][0]<=seq[i][0] for i in range(len(seq)-1)):
            raise ValueError('SOURCE_REVIEW_REQUIRED: phase clock nonmonotone')
    da, db = a[-1][0], b[-1][0]
    duration_fraction = abs(da-db)/max(da,db)
    stop=min(da,db)
    knots=sorted({0.0,stop, *(t for t,_ in a if 0<t<stop),
                  *(t for t,_ in b if 0<t<stop)})
    def interp(seq, times):
        k=0;out=[]
        for t in times:
            while k+1 < len(seq)-1 and seq[k+1][0]<t:
                k+=1
            x0,y0=seq[k]
            x1,y1=seq[k+1]
            out.append(y0+(y1-y0)*(t-x0)/(x1-x0))
        return out
    aa=interp(a,knots);bb=interp(b,knots)
    return max(abs(x-y) for x,y in zip(aa,bb))*1000, duration_fraction


def compare_source_pair(a,b,*,tolerance_mv=TOLERANCE_MV,
                        duration_fraction=DURATION_FRACTION):
    """Returns pre-specified near-match screen, not a physical-identity claim."""
    if a['cell']==b['cell']:
        raise ValueError('SOURCE_REVIEW_REQUIRED: a cross-cell test contains same source ID')
    if (a['stage'],a['temperature_C'],a['phase']) != (b['stage'],b['temperature_C'],b['phase']):
        raise ValueError('SOURCE_REVIEW_REQUIRED: noncomparable test condition')
    volts_diff, duration_diff = phase_pair_max_mV(a['points'], b['points'])
    return {'near_match': duration_diff<=duration_fraction and volts_diff<=tolerance_mv,
            'duration_delta_fraction':round(duration_diff,8),
            'max_absolute_voltage_difference_mV':round(volts_diff,5)}


def read_phases(z:ZipFile,source_file:str,*,cell:str,stage:str,temp:int)->dict:
    if z.getinfo(source_file).file_size>MAX_CSV_MEMBER_BYTES:
        raise ValueError('SOURCE_REVIEW_REQUIRED: original CSV exceeds reader cap')
    meta=_meta_record(z,source_file)
    indicated=str(meta['temperature']).strip().replace(' ','')
    if indicated!=f'{temp}°C':
        raise ValueError('SOURCE_REVIEW_REQUIRED: climate chamber temperature differs from filename')
    phase_rows={21:[],22:[]}
    phase_activations=defaultdict(int)
    active=None
    n=0;previous=None;start_times={};last_times={}
    with z.open(source_file) as source:
        rd=csv.DictReader(io.TextIOWrapper(source,encoding='utf-8-sig',newline=''))
        if not rd.fieldnames or not {'run_time','c_vol','c_cur','step_type'}.issubset(rd.fieldnames):
            raise ValueError('SOURCE_REVIEW_REQUIRED: missing original measured time/current/voltage')
        for row in rd:
            n+=1
            if n>MAX_ROWS or None in row:
                raise ValueError('SOURCE_REVIEW_REQUIRED: bad CSV row or row cap')
            try:
                t=float(parse_source_runtime(row['run_time']))
                v=float(row['c_vol']);amp=float(row['c_cur']);step=int(row['step_type'])
            except (TypeError,ValueError,OverflowError) as ex:
                raise ValueError('SOURCE_REVIEW_REQUIRED: non-numeric source timestamp/current/voltage') from ex
            if not all(math.isfinite(x) for x in (t,v,amp)) or not (1.5<v<5.0):
                raise ValueError('SOURCE_REVIEW_REQUIRED: invalid measurement/units')
            if previous is not None and t<previous:
                raise ValueError('SOURCE_REVIEW_REQUIRED: source clock reversed')
            previous=t
            phase = step if (step==21 and amp>0 or step==22 and amp<0) else None
            if phase != active:
                if phase in PHASES: phase_activations[phase]+=1
                active=phase
            if phase in PHASES:
                if phase not in start_times:start_times[phase]=t
                elapsed=t-start_times[phase]
                if phase in last_times and elapsed<last_times[phase]:
                    raise ValueError('SOURCE_REVIEW_REQUIRED: invalid source phase clock')
                if phase in last_times and elapsed==last_times[phase]:
                    # Repeated timestamps are discarded only if measured voltage agrees;
                    # otherwise an ambiguous physical signal must not be interpolated.
                    if phase_rows[phase][-1][1]!=v:
                        raise ValueError('SOURCE_REVIEW_REQUIRED: conflicting repeated source time')
                    continue
                if phase in last_times and elapsed-last_times[phase]>MAX_PHASE_GAP_S:
                    raise ValueError('SOURCE_REVIEW_REQUIRED: unexplained source phase gap')
                phase_rows[phase].append((elapsed,v))
                last_times[phase]=elapsed
    if n<500:
        raise ValueError('SOURCE_REVIEW_REQUIRED: source measurement too short')
    if any(phase_activations[p]!=1 or len(phase_rows[p])<MIN_PHASE_POINTS for p in PHASES):
        raise ValueError('SOURCE_REVIEW_REQUIRED: incomplete/multiple charge-discharge phase')
    return {'cell':cell,'stage':stage,'temperature_C':temp,
            'publisher_lab':meta['lab'],'publisher_internal_serial':meta['serial'],
            'paired_meta_sha256':meta['paired_meta_sha256'],
            'raw_csv_rows':n,
            'phases':{p:tuple(phase_rows[p]) for p in PHASES}}


def benchmark(archives:dict[str,bytes]):
    if not isinstance(archives,dict) or len(archives)!=MAX_CELLS or set(archives)!={a[1] for a in PINS}:
        raise ValueError('SOURCE_REVIEW_REQUIRED: exact six publisher archive cohort required')
    cells=[];views=[];all_ids=[]
    for fid,name,size,digest in PINS:
        raw=archives[name]
        if not isinstance(raw,bytes) or len(raw)!=size or md5(raw).hexdigest()!=digest:
            raise ValueError('SOURCE_REVIEW_REQUIRED: publisher bytes/MD5 mismatch')
        archive_meta=inspect_zip(raw,{'id':fid,'name':name,'size':size,'md5':digest})
        stem=name[:-4]
        paths=[]
        with ZipFile(io.BytesIO(raw)) as z:
            for index,stage in STAGES:
                for temp in TEMPS:
                    expected=f'{stem}_{index}_{stage}_T{temp}.csv'
                    matches=[p for p in z.namelist() if PurePosixPath(p).name==expected]
                    if len(matches)!=1:
                        raise ValueError('SOURCE_REVIEW_REQUIRED: absent/ambiguous source CSV')
                    record=read_phases(z,matches[0],cell=stem,stage=stage,temp=temp)
                    paths.append(record)
                    for phase in PHASES:
                        views.append({'cell':stem,'stage':stage,'temperature_C':temp,
                                      'phase':phase,'points':record['phases'][phase]})
        identities={(r['publisher_lab'],r['publisher_internal_serial']) for r in paths}
        if len(identities)!=1:
            raise ValueError('SOURCE_REVIEW_REQUIRED: internal source label changed within cell archive')
        all_ids.extend(identities)
        cells.append({'public_cell':stem,'publisher_file_id':fid,
                      'original_size_bytes':size,'original_sha256':archive_meta['original_zip_sha256'],
                      'zip_crc':'PASS','csv_file_count':len(paths),
                      'csv_measurement_rows':sum(x['raw_csv_rows'] for x in paths),
                      'phase_segments':len(paths)*len(PHASES),
                      'sidecar_internal_identity_consistent':True})
    if len(set((lab.casefold().strip(),serial.casefold().strip()) for lab,serial in all_ids))!=MAX_CELLS:
        raise ValueError('SOURCE_REVIEW_REQUIRED: duplicate publisher lab+serial across all 6 archives')
    by_condition=defaultdict(list)
    for x in views:by_condition[(x['stage'],x['temperature_C'],x['phase'])].append(x)
    if len(by_condition)!=len(STAGES)*len(TEMPS)*len(PHASES):
        raise ValueError('SOURCE_REVIEW_REQUIRED: incomplete source conditions')
    conditions=[];candidate_count=0;comparisons=0;source_pairs=set();source_pair_alerts=set()
    all_source_pairs=set()
    minima=[];phase_profiles=0
    for (stage,temp,phase),gr in sorted(by_condition.items()):
        if len(gr)!=MAX_CELLS:raise ValueError('SOURCE_REVIEW_REQUIRED: missing source cell in condition')
        found=0;smallest=math.inf;mean_diff=[]
        for i,one in enumerate(gr):
            # Only replays of real source segments: a controlled derived positive,
            # *not* an independently acquired positive true-duplicate case.
            alias=dict(one)
            alias['cell']='CONTROL_COPY_'+str(i)
            control=compare_source_pair(one,alias)
            if not control['near_match'] or control['max_absolute_voltage_difference_mV']!=0:
                raise ValueError('SOURCE_REVIEW_REQUIRED: known replay control not detected')
            phase_profiles+=1
            for two in gr[i+1:]:
                pair=tuple(sorted((one['cell'],two['cell'])))
                all_source_pairs.add(pair)
                result=compare_source_pair(one,two)
                smallest=min(smallest,result['max_absolute_voltage_difference_mV'])
                mean_diff.append(result['max_absolute_voltage_difference_mV'])
                comparisons+=1
                if result['near_match']:
                    found+=1;candidate_count+=1;source_pair_alerts.add(pair)
        conditions.append({'stage':stage,'temperature_C':temp,'phase':phase,
                           'distinct_publisher_labeled_cell_pairs':15,
                           'source_label_discordant_near_match_alerts':found,
                           'min_observed_full_curve_max_difference_mV':round(smallest,5)})
    if comparisons!=180 or len(all_source_pairs)!=15 or phase_profiles!=72:
        raise ValueError('SOURCE_REVIEW_REQUIRED: benchmark denominator inconsistency')
    return {'schema':'cano.battery.figshare-six-source-blind-condition-screen.v1',
            'dataset_doi':DOI,'license':'CC BY 4.0: cite publisher; source files not redistributed',
            'original_zip_count':MAX_CELLS,'original_csv_count':36,
            'source_rows_processed':sum(c['csv_measurement_rows'] for c in cells),
            'source_identity_pairs_distinct_and_consistent':True,
            'original_checksums_and_zip_crc_verified':True,
            'time_axis':'publisher run_time HH:mm:ss.SSS -> seconds, phase origin zero',
            'conditions':conditions,'source_cells':cells,
            'phase_curve_count':len(views),
            'controlled_derived_same_trace_replay_positives':phase_profiles,
            'controlled_derived_same_trace_replay_detected':phase_profiles,
            'distinct_source_cell_pairs':len(all_source_pairs),
            'cross_source_condition_phase_comparisons':comparisons,
            'source_label_discordant_near_match_alerts':candidate_count,
            'unique_source_cell_pairs_with_any_alert':len(source_pair_alerts),
            'predeclared_max_mV_threshold':TOLERANCE_MV,
            'predeclared_duration_fraction':DURATION_FRACTION,
            'unit_of_negative_denominator':'15 distinct pairs of 6 source-labeled cells; each compared 12 correlated times',
            'positive_control_limitation':'same original trace replayed in code; not independently acquired positive field cases',
            'source_labels_not_independent_physical_custody':True,
            'field_fpr_fnr_established':False,
            'field_release_allowed':False,
            'decision':'SIX_REAL_SOURCE_RECORDS_AUDITED_FPR_FNR_NOT_CERTIFIED'}


def load_archive_directory(directory:Path):
    if directory.is_symlink() or not directory.is_dir() or set(x.name for x in directory.iterdir())!={x[1] for x in PINS}:
        raise ValueError('SOURCE_REVIEW_REQUIRED: exactly six original files required')
    out={}
    for _,name,size,_ in PINS:
        path=directory/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size!=size:
            raise ValueError('SOURCE_REVIEW_REQUIRED: wrong original source file')
        out[name]=path.read_bytes()
    return out


def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if len(args)!=2:
        print('usage: python -m research.battery_curve_audit.figshare_six_source_curve_screen ORIGINAL_DIR RESULT.json',file=sys.stderr)
        return 2
    try:
        source=Path(args[0]);dest=Path(args[1])
        if dest.exists() or not dest.parent.is_dir():
            raise ValueError('SOURCE_REVIEW_REQUIRED: output not exclusive or directory absent')
        report=benchmark(load_archive_directory(source))
        with dest.open('x',encoding='utf-8') as f:
            json.dump(report,f,sort_keys=True,indent=2);f.write('\n')
        print('SIX_REAL_SOURCE_RECORDS_SCREENED',json.dumps({
            'source_rows':report['source_rows_processed'],
            'observations':report['cross_source_condition_phase_comparisons'],
            'source_label_alerts':report['source_label_discordant_near_match_alerts'],
            'independent_source_pairs':report['distinct_source_cell_pairs'],
            'replay_controls_detected':report['controlled_derived_same_trace_replay_detected']}))
        return 0
    except (OSError,ValueError,TypeError,KeyError,csv.Error) as e:
        print('SOURCE_REVIEW_REQUIRED:',str(e)[:250],file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())