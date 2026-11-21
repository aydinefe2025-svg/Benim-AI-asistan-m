"""Evidence-bound ET/AT 10 C CCCV capacity split from four original Figshare ZIPs.

Source article Table 1: RPT step 6 discharges at 1 C until Umin, then CV
until |I|< C/20. Author Table 6 explicitly assigns step_type 22 to 2.5 V CV / C/20 cutoff.
The binary split is an approximate segmentation of continuous measured I(t),U(t),
not an assertion that a proprietary instrument's state log was supplied.
No physical recalibration or cell-capacity recovery claims are made.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
import re
from pathlib import Path
from zipfile import ZipFile
from research.battery_curve_audit.phase_boundary_thermal_audit import (
    SOURCES, PUBLISHED_SOURCE_REPLAY_AH, as_seconds, sidecar_identity,
)
from research.battery_curve_audit.original_t10_tail_current_audit import (
    verify_original_zip, SOURCE_IDS,
)

# Table 6 explicitly specifies discharge CV hold at 2.5 V. Nominal C/20 = 0.245 A.
VOLTAGE_SWITCH_THRESHOLDS = (2.505, 2.510, 2.515)
C20_A = 4.9 / 20
MIN_PHASE_ROWS = 50
MAX_CSV_ROWS = 800_000


def split_measured_discharge(z: ZipFile, member: str) -> dict:
    """Right-endpoint coulometry, tracking voltage-vs-current taper switch.

    Threshold sensitivity is measured in the *same pass* over original source.
    No original row data are returned or persisted; only aggregates.
    """
    if member not in z.namelist() or z.getinfo(member).file_size > 60_000_000:
        raise ValueError('SOURCE_REVIEW_REQUIRED: missing/oversized original measurement')
    if not re.fullmatch(r'TP_k0[14]_0[456]_\d{2}_(ET|AT)_T10\.csv', Path(member).name):
        raise ValueError('SOURCE_REVIEW_REQUIRED: not the original T10 source')
    buckets = {f'{v:.3f}': {
        'CC_capacity_mAh':0., 'CV_capacity_mAh':0.,
        'CC_duration_s':0., 'CV_duration_s':0.,
        'CV_near_2p5V_n':0, 'CV_interval_n':0,
        'switch_time_s':None, 'switch_current_A':None, 'switch_voltage_V':None, 'switch_source_cadence_s':None,
    } for v in VOLTAGE_SWITCH_THRESHOLDS}
    buckets['current_taper_4p75A'] = dict(
        CC_capacity_mAh=0.,CV_capacity_mAh=0.,CC_duration_s=0.,CV_duration_s=0.,
        CV_near_2p5V_n=0,CV_interval_n=0,
        switch_time_s=None,switch_current_A=None,switch_voltage_V=None,switch_source_cadence_s=None,
    )
    ever_one_C=False
    previous_any_time=None;previous_phase_time=None
    phase_active=False;phase_ended=False
    total_rows=0;phase_rows=0;first_time=None;last_time=None
    last_i=None;last_v=None;first_v=None
    with z.open(member) as handle:
        r=csv.DictReader(io.TextIOWrapper(handle,encoding='utf-8-sig',newline=''))
        needed={'run_time','c_cur','c_vol','step_type'}
        if not needed.issubset(r.fieldnames or []):
            raise ValueError('SOURCE_REVIEW_REQUIRED: original columns missing')
        for row in r:
            total_rows+=1
            if total_rows>MAX_CSV_ROWS or None in row:
                raise ValueError('SOURCE_REVIEW_REQUIRED: source row budget / malformed record')
            try:
                t=as_seconds(row['run_time']);i=float(row['c_cur']);v=float(row['c_vol']);step=int(row['step_type'])
            except (ValueError,TypeError,OverflowError) as ex:
                raise ValueError('SOURCE_REVIEW_REQUIRED: invalid source sample') from ex
            if not (math.isfinite(i) and math.isfinite(v) and t>=0):
                raise ValueError('SOURCE_REVIEW_REQUIRED: nonfinite source sample')
            if previous_any_time is not None and t<previous_any_time:
                raise ValueError('SOURCE_REVIEW_REQUIRED: backwards source clock')
            previous_any_time=t
            in_phase=(step==22 and i<0)
            if not in_phase:
                if phase_active:phase_ended=True;phase_active=False
                continue
            if phase_ended:
                raise ValueError('SOURCE_REVIEW_REQUIRED: multiple discharge segments')
            if not phase_active:
                phase_active=True
                first_time=t;first_v=v;previous_phase_time=t
            phase_rows+=1
            dt=t-previous_phase_time
            if dt<0 or dt>120:
                raise ValueError('SOURCE_REVIEW_REQUIRED: invalid discharge cadence')
            previous_phase_time=t
            current=abs(i)
            if 4.80<=current<=5.10 and v>2.52:
                ever_one_C=True
            for th in VOLTAGE_SWITCH_THRESHOLDS:
                b=buckets[f'{th:.3f}']
                if b['switch_time_s'] is None and ever_one_C and v<=th:
                    b.update(switch_time_s=t,switch_current_A=current,switch_voltage_V=v,switch_source_cadence_s=round(dt,4))
            taper=buckets['current_taper_4p75A']
            if taper['switch_time_s'] is None and ever_one_C and current<=4.75 and abs(v-2.5)<=.010:
                taper.update(switch_time_s=t,switch_current_A=current,switch_voltage_V=v,switch_source_cadence_s=round(dt,4))
            if dt>0:
                q_mAh=current*dt/3.6
                for b in buckets.values():
                    prefix='CV' if b['switch_time_s'] is not None else 'CC'
                    b[prefix+'_capacity_mAh']+=q_mAh
                    b[prefix+'_duration_s']+=dt
                    if prefix=='CV':
                        b['CV_interval_n']+=1
                        if abs(v-2.5)<=.005:b['CV_near_2p5V_n']+=1
            last_time=t;last_i=current;last_v=v
    if phase_rows<MIN_PHASE_ROWS or not ever_one_C:
        raise ValueError('SOURCE_REVIEW_REQUIRED: original 1C discharge segment not present')
    if not (0.23<=last_i<=0.26 and abs(last_v-2.5)<=.006):
        raise ValueError('SOURCE_REVIEW_REQUIRED: no original C/20 at 2.5V termination')
    if any(b['switch_time_s'] is None for b in buckets.values()):
        raise ValueError('SOURCE_REVIEW_REQUIRED: source CCCV transition absent')
    duration=last_time-first_time
    for b in buckets.values():
        cc=b['CC_capacity_mAh'];cv=b['CV_capacity_mAh']
        b['CC_capacity_mAh']=round(cc,8)
        b['CV_capacity_mAh']=round(cv,8)
        b['CC_duration_s']=round(b['CC_duration_s'],4)
        b['CV_duration_s']=round(b['CV_duration_s'],4)
        b['CV_near_2p5V_fraction']=round(b.pop('CV_near_2p5V_n')/b.pop('CV_interval_n'),6)
        b['switch_time_s_from_phase_start']=round(b.pop('switch_time_s')-first_time,4)
        b['switch_voltage_V']=round(b['switch_voltage_V'],6)
        b['switch_current_A']=round(b['switch_current_A'],6)
        if abs(b['CC_duration_s']+b['CV_duration_s']-duration)>1e-3:
            raise ValueError('SOURCE_REVIEW_REQUIRED: phase intervals not partitioned')
        if not (b['CV_near_2p5V_fraction']>.95):
            raise ValueError('SOURCE_REVIEW_REQUIRED: voltage hold not supported')
    return dict(original_file=Path(member).name, original_rows=total_rows,
        discharge_rows=phase_rows, duration_s=round(duration,4),
        full_discharge_capacity_mAh=round(buckets['2.505']['CC_capacity_mAh']+buckets['2.505']['CV_capacity_mAh'],8),
        terminal_current_A=round(last_i,6),terminal_voltage_V=round(last_v,6),
        c20_reference_A=C20_A,
        terminal_current_absolute_deviation_from_nominal_C20_A=round(abs(last_i-C20_A),6),
        measured_first_voltage_V=round(first_v,6),
        boundaries=buckets)


def audit(directory:Path)->dict:
    if not directory.is_dir() or {x.name for x in directory.iterdir()}!={x[1] for x in SOURCES}:
        raise ValueError('SOURCE_REVIEW_REQUIRED: original source set missing/unexpected')
    obs=[]
    for stem,name,size,expected_md5 in SOURCES:
        f=directory/name
        if f.is_symlink() or not f.is_file() or f.stat().st_size!=size:
            raise ValueError('SOURCE_REVIEW_REQUIRED: missing original publisher file')
        raw=f.read_bytes()
        if hashlib.md5(raw).hexdigest()!=expected_md5:
            raise ValueError('SOURCE_REVIEW_REQUIRED: publisher original MD5 mismatch')
        verify_original_zip(raw)
        cell={'source_cell':stem,'publisher_file_id':SOURCE_IDS[stem],
              'source_sha256':hashlib.sha256(raw).hexdigest(),'publisher_md5_verified':True}
        with ZipFile(io.BytesIO(raw)) as z:
            sidecars=[]
            for phase in ('ET','AT'):
                matches=[n for n in z.namelist() if re.fullmatch(re.escape(stem)+r'_\d{2}_'+phase+r'_T10\.csv',Path(n).name)]
                if len(matches)!=1:raise ValueError('SOURCE_REVIEW_REQUIRED: nonunique source ET AT file')
                sidecars.append(sidecar_identity(z,matches[0]))
                cell[phase]=split_measured_discharge(z,matches[0])
                expected=PUBLISHED_SOURCE_REPLAY_AH[stem][phase]['discharge']
                if abs(cell[phase]['full_discharge_capacity_mAh']/1000-expected)>1.1e-6:
                    raise ValueError('SOURCE_REVIEW_REQUIRED: source capacities not reproduced')
            for field in ('lab','internal_cell_serial','instrument','channel','chamber','setpoint_C'):
                if sidecars[0][field]!=sidecars[1][field]:
                    raise ValueError('SOURCE_REVIEW_REQUIRED: source instrument identity changed')
            if sidecars[0]['measurement_date']>=sidecars[1]['measurement_date']:
                raise ValueError('SOURCE_REVIEW_REQUIRED: source measurement chronology incorrect')
        delta={}
        for method in cell['ET']['boundaries']:
            et=cell['ET']['boundaries'][method];at=cell['AT']['boundaries'][method]
            delta[method]={
                'CC_change_mAh':round(at['CC_capacity_mAh']-et['CC_capacity_mAh'],6),
                'CV_change_mAh':round(at['CV_capacity_mAh']-et['CV_capacity_mAh'],6),
                'total_change_mAh':round(cell['AT']['full_discharge_capacity_mAh']-cell['ET']['full_discharge_capacity_mAh'],6),
                'CV_duration_change_s':round(at['CV_duration_s']-et['CV_duration_s'],4),
            }
            if abs(delta[method]['CC_change_mAh']+delta[method]['CV_change_mAh']-delta[method]['total_change_mAh'])>2e-5:
                raise ValueError('SOURCE_REVIEW_REQUIRED: ET AT CC CV changes do not close')
        ccchanges=[delta[f'{thr:.3f}']['CC_change_mAh'] for thr in VOLTAGE_SWITCH_THRESHOLDS]
        attribution_span=round(max(ccchanges)-min(ccchanges),6)
        total_abs=abs(delta['2.505']['total_change_mAh'])
        cell['voltage_threshold_CC_attribution_span_mAh']=attribution_span
        cell['voltage_threshold_CC_span_exceeds_total_source_delta']=attribution_span>total_abs
        cell['CC_CV_phase_allocation_not_source_state_logged']=True
        cell['ET_AT_source_discharge_split']=delta
        obs.append(cell)
    return dict(schema='cano.battery.original-four-10C-rpt-cccv-mechanism.v1',
        source_article_doi='10.1038/s41597-024-03859-z',source_dataset_doi='10.6084/m9.figshare.25975315',
        author_protocol_table1='RPT step 6 discharge CCCV, I=1C, U=Umin, terminate |I|<C/20',
        author_explicit_voltage_hold_V=2.5,
        author_protocol_table6='step_type=22: CCCV discharge 1C, CV at 2.5 V, cut off at C/20',
        nominal_C20_A=C20_A,source_cell_count=len(obs),original_ET_AT_csv_count=2*len(obs),
        total_original_measurement_rows=sum(c[p]['original_rows'] for c in obs for p in ('ET','AT')),
        publisher_zip_md5_crc_all_verified=True,thresholds_V=list(VOLTAGE_SWITCH_THRESHOLDS),
        author_original_source_capacity_reproduced=True,
        source_cells_with_CC_CV_assignment_span_exceeding_total_change=sum(c['voltage_threshold_CC_span_exceeds_total_source_delta'] for c in obs),
        source_provenance_consistent=True,
        actual_instrument_program_export_or_calibration_obtained=False,
        observed_CCCV_protocol_consistent_not_proof_of_cause=True,
        physical_capacity_recovery_proven=False,independent_physical_custody_proven=False,
        population_field_FPR_FNR_proven=False,commercial_release_allowed=False,
        observations=obs)


def main(argv=None):
    import sys
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=2:raise SystemExit('usage: python -m research.battery_curve_audit.cccv_protocol_split SOURCE_DIR OUT.json')
    out=Path(args[1])
    if out.exists() or not out.parent.is_dir():raise ValueError('SOURCE_REVIEW_REQUIRED: output exists/bad parent')
    obj=audit(Path(args[0]))
    out.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print('FOUR_SOURCE_AUTHOR_RPT_CCCV_PROTO_SPLIT_VERIFIED',obj['total_original_measurement_rows'])
    for c in obj['observations']:
        print(c['source_cell'],'ET_AT_CCCV_DELTA_mAh',c['ET_AT_source_discharge_split']['2.505'])

if __name__=='__main__':main()