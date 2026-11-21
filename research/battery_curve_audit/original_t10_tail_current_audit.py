"""Source-specific, non-causal original current-profile decomposition.

Reproduce only the original Stroebl et al. 2024 Figshare ET/AT T10 CSV
waveforms selected by immutable publisher ID and archive MD5.
Measured current-time distribution can explain a numerical capacity contrast;
this cannot infer instrument calibration, temperature causality, or field FPR.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
import re
import stat
from pathlib import PurePosixPath
from pathlib import Path
from zipfile import ZipFile

from research.battery_curve_audit.phase_boundary_thermal_audit import (
    SOURCES, PUBLISHED_SOURCE_REPLAY_AH, as_seconds, sidecar_identity,
)

def verify_original_zip(raw:bytes)->None:
    """Bounded safe member scan and full publisher-original CRC, not extraction."""
    with ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist()
        if not infos or len(infos)>800:raise ValueError('SOURCE_REVIEW_REQUIRED: archive file count')
        seen=set();expanded=0
        for item in infos:
            name=item.filename;p=PurePosixPath(name)
            if (name in seen or p.is_absolute() or any(seg=='..' for seg in p.parts)
                or '\\' in name or item.flag_bits & 1 or stat.S_ISLNK(item.external_attr>>16)):
                raise ValueError('SOURCE_REVIEW_REQUIRED: unsafe original archive member')
            seen.add(name)
            if item.file_size>100_000_000:raise ValueError('SOURCE_REVIEW_REQUIRED: oversized archive member')
            expanded+=item.file_size
            if expanded>150_000_000:raise ValueError('SOURCE_REVIEW_REQUIRED: ZIP expansion cap')
            if item.file_size>1_000_000 and item.file_size>max(item.compress_size,1)*250:
                raise ValueError('SOURCE_REVIEW_REQUIRED: ZIP compression ratio')
        if z.testzip() is not None:raise ValueError('SOURCE_REVIEW_REQUIRED: original publisher ZIP CRC')

SOURCE_IDS={'TP_k01_04':47639005, 'TP_k01_05':47627092,
            'TP_k04_05':47627110, 'TP_k04_06':47627104}
# Descriptive intervals are classified by measured absolute current at the
# interval's right endpoint, following author's current-time integration.
BINS=((0.,1.,'below_1A'),(1.,4.,'1_to_4A'),
      (4.,4.8,'4_to_4p8A'),(4.8,float('inf'),'at_least_4p8A'))
MAX_CSV_MEMBER_BYTES=60_000_000
MAX_ROWS=800_000
MIN_PHASE_POINTS=50
MAX_GAP_SECONDS=120.


def integrate_discharge(z:ZipFile, member:str)->dict:
    if member not in z.namelist() or z.getinfo(member).file_size>MAX_CSV_MEMBER_BYTES:
        raise ValueError('SOURCE_REVIEW_REQUIRED: oversized/missing CSV')
    if not re.fullmatch(r'TP_k0[14]_0[456]_\d{2}_(ET|AT)_T10\.csv', Path(member).name):
        raise ValueError('SOURCE_REVIEW_REQUIRED: wrong original experiment')
    totals={key:0. for _,_,key in BINS}
    durations={key:0. for _,_,key in BINS}
    near_cutoff={key:[0,0] for _,_,key in BINS}
    n=0; total_rows=0; first_t=None; previous_t=None; previous_any_t=None
    active=False; done=False; last_t=None; first_v=None; last_v=None
    with z.open(member) as f:
        reader=csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig',newline=''))
        needed={'run_time','c_cur','c_vol','step_type'}
        if reader.fieldnames is None or not needed.issubset(set(reader.fieldnames)):
            raise ValueError('SOURCE_REVIEW_REQUIRED: original waveform fields missing')
        for row in reader:
            total_rows+=1
            if total_rows>MAX_ROWS or None in row:
                raise ValueError('SOURCE_REVIEW_REQUIRED: source row budget/malformed record')
            try:
                t=as_seconds(row['run_time']);i=float(row['c_cur']);v=float(row['c_vol']);step=int(row['step_type'])
            except (ValueError,OverflowError,TypeError) as e:
                raise ValueError('SOURCE_REVIEW_REQUIRED: invalid source datum') from e
            if not math.isfinite(i) or not math.isfinite(v):
                raise ValueError('SOURCE_REVIEW_REQUIRED: nonfinite current/voltage')
            if previous_any_t is not None and t<previous_any_t:
                raise ValueError('SOURCE_REVIEW_REQUIRED: clock backwards')
            previous_any_t=t
            keep=step==22 and i<0
            if not keep:
                if active:done=True;active=False
                continue
            if done:raise ValueError('SOURCE_REVIEW_REQUIRED: more than one source discharge segment')
            if not active:active=True;first_t=t;first_v=v;previous_t=t
            n+=1;last_t=t;last_v=v
            dt=t-previous_t
            if dt<0 or dt>MAX_GAP_SECONDS:
                raise ValueError('SOURCE_REVIEW_REQUIRED: invalid source discharge sampling interval')
            if dt>0:
                current=abs(i)
                label=next(k for lo,hi,k in BINS if lo<=current<hi)
                q_mAh=current*dt/3.6
                totals[label]+=q_mAh
                durations[label]+=dt
                near_cutoff[label][0]+=1
                if abs(v-2.5)<=.005:near_cutoff[label][1]+=1
            previous_t=t
    if n<MIN_PHASE_POINTS or first_t is None or last_t is None or last_t<=first_t:
        raise ValueError('SOURCE_REVIEW_REQUIRED: missing/short source discharge phase')
    return {'original_file':Path(member).name,'source_csv_rows':total_rows,'discharge_rows':n,
            'capacity_mAh':round(sum(totals.values()),9),
            'duration_s':round(last_t-first_t,6),
            'effective_current_mA':round(1000*sum(totals.values())*3.6/(last_t-first_t),6),
            'start_voltage_V':round(first_v,6),'end_voltage_V':round(last_v,6),
            'bin_duration_s':{k:round(v,6) for k,v in durations.items()},
            'bin_capacity_mAh':{k:round(v,9) for k,v in totals.items()},
            'bin_near_2p5V_fraction':{k:(round(near_cutoff[k][1]/near_cutoff[k][0],6) if near_cutoff[k][0] else None)
                                      for _,_,k in BINS}}


def audit(source_dir:Path)->dict:
    if not source_dir.is_dir() or {x.name for x in source_dir.iterdir()}!={x[1] for x in SOURCES}:
        raise ValueError('SOURCE_REVIEW_REQUIRED: offline original archive set missing/unexpected')
    results=[]
    for stem,name,size,expected_md5 in SOURCES:
        loc=source_dir/name
        if loc.is_symlink() or not loc.is_file() or loc.stat().st_size!=size:
            raise ValueError('SOURCE_REVIEW_REQUIRED: source filename/size invalid')
        raw=loc.read_bytes()
        if hashlib.md5(raw).hexdigest()!=expected_md5:
            raise ValueError('SOURCE_REVIEW_REQUIRED: publisher MD5 mismatch')
        verify_original_zip(raw)
        obj={'source_cell':stem,'publisher_file_id':SOURCE_IDS[stem],
             'original_zip_md5':expected_md5,'original_zip_sha256':hashlib.sha256(raw).hexdigest(),
             'original_zip_crc_verified':True}
        with ZipFile(io.BytesIO(raw)) as z:
            names=z.namelist()
            identities=[]
            for phase in ('ET','AT'):
                matches=[f for f in names if re.fullmatch(re.escape(stem)+r'_\d{2}_'+phase+r'_T10\.csv',Path(f).name)]
                if len(matches)!=1:
                    raise ValueError('SOURCE_REVIEW_REQUIRED: nonunique original ET/AT source')
                source=matches[0]
                identities.append(sidecar_identity(z,source))
                obj[phase]=integrate_discharge(z,source)
                original=PUBLISHED_SOURCE_REPLAY_AH[stem][phase]['discharge']
                if abs(obj[phase]['capacity_mAh']/1000-original)>1.1e-6:
                    raise ValueError('SOURCE_REVIEW_REQUIRED: independent result differs from accepted original source receipt')
            if any(identities[0][field]!=identities[1][field] for field in
                   ('lab','internal_cell_serial','instrument','channel','chamber','setpoint_C')):
                raise ValueError('SOURCE_REVIEW_REQUIRED: ET/AT source provenance mismatch')
            if identities[0]['measurement_date']>=identities[1]['measurement_date']:
                raise ValueError('SOURCE_REVIEW_REQUIRED: ET/AT chronological order invalid')
        et,at=obj['ET'],obj['AT'];keys=[b[2] for b in BINS]
        dq={k:round(at['bin_capacity_mAh'][k]-et['bin_capacity_mAh'][k],6) for k in keys}
        dt={k:round(at['bin_duration_s'][k]-et['bin_duration_s'][k],6) for k in keys}
        q=at['capacity_mAh']-et['capacity_mAh'];duration=at['duration_s']-et['duration_s']
        obj.update({'delta_capacity_mAh':round(q,6),'delta_duration_s':round(duration,6),
                    'delta_effective_current_mA':round(at['effective_current_mA']-et['effective_current_mA'],6),
                    'delta_capacity_by_current_mAh':dq,'delta_duration_by_current_s':dt,
                    'absolute_current_bins_are_descriptive_not_ground_truth_phases':True,
                    'midcurrent_voltage_near_cutoff_in_both_recordings':all(
                       x['bin_near_2p5V_fraction']['1_to_4A']>=.995 for x in (et,at)),
                    'source_instrument_lab':identities[0]['lab'],
                    'instrument_consistent_within_ET_AT':True,
                    'source_device_accuracy_or_calibration_verified':False})
        if abs(sum(dq.values())-q)>1e-5 or abs(sum(dt.values())-duration)>1e-4:
            raise ValueError('SOURCE_REVIEW_REQUIRED: current-bin arithmetic failed')
        if not (-90<duration<0 and 0<q<15):
            raise ValueError('SOURCE_REVIEW_REQUIRED: observed source profile differs from predeclared real cases')
        if not (dq['1_to_4A']>0 and dq['below_1A']<0 and
                obj['midcurrent_voltage_near_cutoff_in_both_recordings']):
            raise ValueError('SOURCE_REVIEW_REQUIRED: source current-taper pattern not established')
        results.append(obj)
    return {'schema':'cano.battery.original-four-T10-current-taper-decomposition.v1',
            'source_doi':'10.6084/m9.figshare.25975315','four_publisher_originals_md5_crc_verified':True,
            'original_source_cells':4,'original_csv_files':8,
            'original_csv_rows':sum(c[p]['source_csv_rows'] for c in results for p in ('ET','AT')),
            'four_of_four_midcurrent_tail_contribution_increased':sum(c['delta_capacity_by_current_mAh']['1_to_4A']>0 for c in results),
            'four_of_four_lowcurrent_tail_contribution_decreased':sum(c['delta_capacity_by_current_mAh']['below_1A']<0 for c in results),
            'observations':results,
            'independently_calibrated_instruments':False,'actual_physical_capacity_growth_proven':False,
            'temperature_causality_proven':False,'population_field_FPR_FNR_established':False,
            'production_release_allowed':False}


def main(args=None):
    import sys
    argv=sys.argv[1:] if args is None else args
    if len(argv)!=2:raise SystemExit('usage: python -m research.battery_curve_audit.original_t10_tail_current_audit SOURCE_DIRECTORY RESULT_JSON')
    output=Path(argv[1])
    if output.exists() or not output.parent.is_dir():raise ValueError('SOURCE_REVIEW_REQUIRED: output must not exist')
    ans=audit(Path(argv[0]));output.write_text(json.dumps(ans,sort_keys=True,indent=2)+'\n',encoding='utf8')
    print('FOUR_ORIGINAL_10C_CURRENT_TAPER_CONFIRMED',ans['original_csv_rows'],
          [(r['source_cell'],r['delta_capacity_mAh'],r['delta_capacity_by_current_mAh']['1_to_4A']) for r in ans['observations']])

if __name__=='__main__':main()