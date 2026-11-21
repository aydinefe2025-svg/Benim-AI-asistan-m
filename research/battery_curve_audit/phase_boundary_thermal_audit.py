"""Public Figshare Stroebl T10 raw-data temperature and boundary sensitivity audit.

Only source-verified aggregates are written; the original measured waveforms remain
in user's library as separate source archives. No calibration or field claim.
"""
from __future__ import annotations
import csv
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
from zipfile import ZipFile
SOURCES = (
    ("TP_k01_04", "TP_k01_04_FIGSHARE_47639005_ORJINAL.zip", 7150834, "8e4f64b05547738d52f8e34a53c578d9"),
    ("TP_k01_05", "TP_k01_05_FIGSHARE_47627092_ORJINAL.zip", 7042134, "fe9d2c2d84050af909926795a55a0e58"),
    ("TP_k04_05", "TP_k04_05_FIGSHARE_47627110_ORIGINAL.zip", 11468262, "93956f361b84a623b258c53e0193225c"),
    ("TP_k04_06", "TP_k04_06_FIGSHARE_47627104_ORIGINAL.zip", 11660912, "17c9445e56c1d3ed6292ac0cf5046fc8"),
)
# Original publisher-source-derived preserved k01/k04 aggregate receipts.
# Only these reported channel capacities are pinned here, not the waveforms.
PUBLISHED_SOURCE_REPLAY_AH = {
 "TP_k01_04": {"ET": {"charge": 4.76654, "discharge": 4.725518}, "AT": {"charge": 4.706347, "discharge": 4.730241}},
 "TP_k01_05": {"ET": {"charge": 4.777712, "discharge": 4.769923}, "AT": {"charge": 4.714905, "discharge": 4.773346}},
 "TP_k04_05": {"ET": {"charge": 4.716242, "discharge": 4.676770}, "AT": {"charge": 4.689056, "discharge": 4.688123}},
 "TP_k04_06": {"ET": {"charge": 4.779681, "discharge": 4.743692}, "AT": {"charge": 4.745840, "discharge": 4.752992}},
}
BASELINE_RECEIPT_SHA256 = {
 "k01": "ed1d831c97a3fea7a0f273a9143e22b0f8732426ce843b22b0af11b080809c10",
 "k04": "8206b68156e0c4f0ff5f703682a8627ec7fbafbc4b1206bde6dd1033d8dc7463",
}

def as_seconds(x:str)->float:
    x=x.strip()
    if ':' not in x:
        sec=float(x)
    else:
        match=re.fullmatch(r'(\d{1,7}):([0-5]\d):([0-5]\d)(?:\.(\d{1,6}))?',x)
        if match is None: raise ValueError('SOURCE_REVIEW_REQUIRED: malformed run_time')
        h,m,s,fract=match.groups()
        sec=int(h)*3600+int(m)*60+int(s)+(float('0.'+fract) if fract else 0)
    if not math.isfinite(sec) or sec<0:raise ValueError('SOURCE_REVIEW_REQUIRED: source time invalid')
    return sec


PHASES = {21: 'charge', 22: 'discharge'}


def sidecar_identity(z:ZipFile, csv_member:str)->dict:
    name=csv_member[:-4]+"_meta.txt"
    if name not in z.namelist() or z.getinfo(name).file_size>50_000:
        raise ValueError('SOURCE_REVIEW_REQUIRED: source measurement sidecar missing/oversized')
    raw=z.read(name)
    fields={}
    for line in raw.decode('utf-8-sig').splitlines():
        if ': ' in line:
            k,v=line.split(': ',1)
            fields[k.strip()]=v.strip()
    names=('Laboratory identifier','Internal cell serial','Testpoint','Measurement start date',
           'Measurement device used','Test channel','Climate chamber used',
           'Climate chamber temperature setpoint','Position within climate chamber')
    if any(not fields.get(n) for n in names):
        raise ValueError('SOURCE_REVIEW_REQUIRED: incomplete source instrument metadata')
    if fields['Climate chamber temperature setpoint'].replace(' ','')!='10°C':
        raise ValueError('SOURCE_REVIEW_REQUIRED: source sidecar is not 10 degrees setpoint')
    try:
        day=datetime.strptime(fields['Measurement start date'],'%d.%m.%Y').date()
    except ValueError as exc:
        raise ValueError('SOURCE_REVIEW_REQUIRED: malformed source measurement date') from exc
    return {'source_sidecar_sha256':hashlib.sha256(raw).hexdigest(),
            'lab':fields['Laboratory identifier'],
            'internal_cell_serial':fields['Internal cell serial'],
            'source_testpoint_label':fields['Testpoint'],
            'instrument':fields['Measurement device used'],
            'channel':fields['Test channel'],
            'chamber':fields['Climate chamber used'],
            'chamber_position':fields['Position within climate chamber'],
            'setpoint_C':10, 'measurement_date':day.isoformat()}


def source_phase_summary(z: ZipFile, member: str) -> dict:
    """Source row stream, phase-segment isolation, temperature and time diagnostics."""
    results = {21: [], 22: []}
    counts = {21: 0, 22: 0}
    tprevious = None
    active = None
    all_rows = 0
    nan_surface = 0
    with z.open(member) as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig', newline=''))
        expected = {'run_time', 'step_type', 'c_cur', 'c_vol', 'c_surf_temp', 'amb_temp'}
        if not expected.issubset(reader.fieldnames or []):
            raise ValueError('SOURCE_REVIEW_REQUIRED: required source fields absent')
        for line in reader:
            all_rows += 1
            t = as_seconds(line['run_time'])
            cur = float(line['c_cur']);vol=float(line['c_vol']);sur=float(line['c_surf_temp'])
            amb=float(line['amb_temp'])
            step = int(line['step_type'])
            if not all(math.isfinite(x) for x in (t, cur, vol)):
                raise ValueError('SOURCE_REVIEW_REQUIRED: nonfinite time/current/voltage')
            if tprevious is not None and t < tprevious:
                raise ValueError('SOURCE_REVIEW_REQUIRED: backwards source time')
            tprevious = t
            phase = step if ((step == 21 and cur > 0) or (step == 22 and cur < 0)) else None
            if phase != active:
                if phase is not None: results[phase].append([])
                active = phase
            if phase is not None:
                counts[phase] += 1
                if not math.isfinite(sur): nan_surface += 1
                results[phase][-1].append((t, cur, vol, sur, amb))
    summary={'file':Path(member).name,'all_csv_rows':all_rows, 'nonfinite_surface_phase_rows':nan_surface,
             'phases':{}}
    for code,label in PHASES.items():
        if len(results[code]) != 1 or len(results[code][0]) < 50:
            raise ValueError('SOURCE_REVIEW_REQUIRED: source missing/multiple valid phase segments')
        pts=results[code][0];ts=[x[0] for x in pts];curr=[abs(x[1]) for x in pts]
        intervals=[]
        temp_weighted=0.;temp_weight_s=0.;above15=0.;above20=0.
        for i in range(1,len(pts)):
            dt=pts[i][0]-pts[i-1][0]
            if dt<0 or dt>120:raise ValueError('SOURCE_REVIEW_REQUIRED: invalid segment cadence')
            if dt>0:
                intervals.append((dt,curr[i]*dt/3600))
                if math.isfinite(pts[i][3]) and math.isfinite(pts[i-1][3]):
                    mean2=(pts[i][3]+pts[i-1][3])/2
                    temp_weighted+=dt*mean2;temp_weight_s+=dt
                    if mean2>15:above15+=dt
                    if mean2>20:above20+=dt
        charge=sum(x[1] for x in intervals)
        surf=[x[3] for x in pts if math.isfinite(x[3])]
        amb=[x[4] for x in pts if math.isfinite(x[4])]
        def numeric(xs):
            return dict(n=len(xs),min=round(min(xs),4),max=round(max(xs),4),mean=round(statistics.fmean(xs),4),first=round(xs[0],4),last=round(xs[-1],4)) if xs else dict(n=0)
        def critical_trim_seconds(target_mAh:float,from_start:bool):
            # One-sided AT phase shortening: remove interval contributions until
            # target full-source capacity difference is exhausted. Interpolate
            # within the crossing interval; not evidence of a real transition.
            target_Ah=target_mAh/1000
            if target_Ah<=0:return None
            accAh=0.;accS=0.;interval_order=intervals if from_start else reversed(intervals)
            for dt,dAh in interval_order:
                if dAh<=0:continue
                if accAh + dAh >= target_Ah:
                    frac=(target_Ah-accAh)/dAh
                    return round(accS+frac*dt,4)
                accAh+=dAh;accS+=dt
            return None
        summary['phases'][label]={'step':code,'source_rows':len(pts),'duration_seconds':round(ts[-1]-ts[0],4),
            'capacity_right_Ah':round(charge,9), 'start_voltage_V':round(pts[0][2],6),
            'end_voltage_V':round(pts[-1][2],6), 'abs_current_mean_A':round(statistics.fmean(curr),5),
            'interval_count':len(intervals), 'zero_dt_intervals':len(pts)-1-len(intervals),
            'interval_dt_median_s':round(statistics.median(x[0] for x in intervals),4),
            'interval_dt_max_s':round(max(x[0] for x in intervals),4),
            'first_positive_dt_s':round(intervals[0][0],6),
            'first_interval_capacity_mAh':round(intervals[0][1]*1000,6),
            'last_positive_dt_s':round(intervals[-1][0],6),
            'last_interval_capacity_mAh':round(intervals[-1][1]*1000,6),
            'time_weighted_surface_temp_C':round(temp_weighted/temp_weight_s,4) if temp_weight_s>0 else None,
            'time_fraction_surface_interval_above_15C':round(above15/temp_weight_s,5) if temp_weight_s>0 else None,
            'time_fraction_surface_interval_above_20C':round(above20/temp_weight_s,5) if temp_weight_s>0 else None,
            'mean_surface_temperature_C':numeric(surf),
            'mean_ambient_temperature_C':numeric(amb),
            'number_positive_temperature_over_0':sum(x>=0 for x in surf),
            'duration_threshold_callable':True,
            'first_3_points':[[round(p[0]-pts[0][0],4), round(p[2],5),round(p[1],5),round(p[3],3) if math.isfinite(p[3]) else None] for p in pts[:3]],
            'last_3_points':[[round(p[0]-pts[0][0],4), round(p[2],5),round(p[1],5),round(p[3],3) if math.isfinite(p[3]) else None] for p in pts[-3:]],
            '_intervals':intervals}
    return summary



def capacity_after_edge_trim_Ah(intervals:list, seconds:float, side:str) -> float:
    """Numeric sensitivity only: remove a hypothetical segment-edge duration."""
    if seconds<0 or side not in ('start','end'):
        raise ValueError('SOURCE_REVIEW_REQUIRED: invalid hypothetical trim')
    rem=seconds;acc=0.0
    order=intervals if side=='start' else reversed(intervals)
    for dt, charge in order:
        if rem>=dt:
            rem-=dt
            continue
        elif rem>0:
            acc+=charge*(1-rem/dt)
            rem=0.0
        else:acc+=charge
    return acc


def run(folder:Path):
    folder=Path(folder);base=PUBLISHED_SOURCE_REPLAY_AH;out=[]
    for stem,name,size,md5 in SOURCES:
        path=folder/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size!=size:raise ValueError('SOURCE_REVIEW_REQUIRED: source missing or bad byte count')
        raw=path.read_bytes()
        if hashlib.md5(raw).hexdigest()!=md5:raise ValueError('SOURCE_REVIEW_REQUIRED: source MD5 mismatch')
        with ZipFile(io.BytesIO(raw)) as z:
            if z.testzip() is not None:raise ValueError('SOURCE_REVIEW_REQUIRED: source ZIP CRC mismatch')
            per_phase={}
            for phase in ('ET','AT'):
                matches=[x for x in z.namelist() if re.fullmatch(re.escape(stem)+r'_\d{2}_'+phase+r'_T10\.csv',Path(x).name)]
                if len(matches)!=1:raise ValueError('SOURCE_REVIEW_REQUIRED: wrong original record count')
                per_phase[phase]=source_phase_summary(z,matches[0])
                per_phase[phase]['source_sidecar']=sidecar_identity(z,matches[0])
        a=per_phase['ET']['source_sidecar'];b=per_phase['AT']['source_sidecar']
        stable_fields=('lab','internal_cell_serial','source_testpoint_label','instrument','channel',
                      'chamber','chamber_position','setpoint_C')
        if any(a[k]!=b[k] for k in stable_fields):
            raise ValueError('SOURCE_REVIEW_REQUIRED: original ET/AT device, channel, chamber or identity mismatch')
        if datetime.fromisoformat(a['measurement_date'])>=datetime.fromisoformat(b['measurement_date']):
            raise ValueError('SOURCE_REVIEW_REQUIRED: source ET/AT dates out of order')
        expect=base[stem]
        # Validate exact original right-endpoint integration for both channels.
        for phase in ('ET','AT'):
            for channel in ('charge','discharge'):
                delta=abs(per_phase[phase]['phases'][channel]['capacity_right_Ah']-expect[phase][channel])
                if delta>0.0000011:raise ValueError('SOURCE_REVIEW_REQUIRED: source capacity not reproduced')
        discharge_deltaAh=per_phase['AT']['phases']['discharge']['capacity_right_Ah']-per_phase['ET']['phases']['discharge']['capacity_right_Ah']
        if discharge_deltaAh<=0:raise ValueError('SOURCE_REVIEW_REQUIRED: expected anomalous sign changed')
        at_dis=per_phase['AT']['phases']['discharge'];et_dis=per_phase['ET']['phases']['discharge']
        crossing={}
        for side in ('start','end'):
            target=discharge_deltaAh
            acc_Ah=0;acc_s=0
            vals=at_dis['_intervals'] if side=='start' else reversed(at_dis['_intervals'])
            for dt,dAh in vals:
                if acc_Ah+dAh>=target:
                    crossing[side]=round(acc_s+(target-acc_Ah)*dt/dAh,4);break
                acc_Ah+=dAh;acc_s+=dt
            else:raise ValueError('SOURCE_REVIEW_REQUIRED: no capacity crossing')
        trim_sensitivity=[]
        for trim_s in (0,1,3,5,10,30):
            for side in ('start','end'):
                aet=capacity_after_edge_trim_Ah(et_dis['_intervals'],trim_s,side)
                aat=capacity_after_edge_trim_Ah(at_dis['_intervals'],trim_s,side)
                trim_sensitivity.append({'symmetric_trim_seconds':trim_s,'edge':side,
                                         'AT_minus_ET_discharge_mAh':round((aat-aet)*1000,6),
                                         'positive_sign_retained':aat> aet})
        for phase in ('ET','AT'):
            for channel in ('charge','discharge'):
                del per_phase[phase]['phases'][channel]['_intervals']
        out.append({'source_cell':stem,'original_zip_sha256':hashlib.sha256(raw).hexdigest(),
                    'publisher_md5_crc_verified':True,
                    'source_ET_AT_instrument_channel_chamber_stable':True,
                    'source_days_ET_to_AT':(datetime.fromisoformat(b['measurement_date'])-datetime.fromisoformat(a['measurement_date'])).days,
                    'raw_csv_rows':sum(a['all_csv_rows'] for a in per_phase.values()),
                    'original_source':per_phase,
                    'discharge_at_minus_et_mAh':round(1000*discharge_deltaAh,6),
                    'discharge_critical_AT_trim_s':crossing,
                    'symmetric_discharge_edge_trim_sensitivity':trim_sensitivity,
                    'first_AT_discharge_interval_alone_exceeds_positive_delta':at_dis['first_interval_capacity_mAh']>discharge_deltaAh*1000,
                    'critical_AT_first_interval_contrast_mAh':round(at_dis['first_interval_capacity_mAh']-discharge_deltaAh*1000,6),
                    'ET_to_AT_time_weighted_surface_delta_C':round(at_dis['time_weighted_surface_temp_C']-et_dis['time_weighted_surface_temp_C'],4) if at_dis['time_weighted_surface_temp_C'] is not None and et_dis['time_weighted_surface_temp_C'] is not None else None,
                    'critical_relative_current_shift_mA':round(1000*discharge_deltaAh*3600/at_dis['duration_seconds'],5),
                    'caveat':'Critical trim/offset are hypothetical sensitivity thresholds, NOT observed source instrument errors.'})
    return {'schema':'cano.battery.four-original-10C-phase-thermal-boundary-sensitivity.v1',
            'data_doi':'10.6084/m9.figshare.25975315',
            'original_k01_k04_aggregate_receipt_sha256':BASELINE_RECEIPT_SHA256,
            'four_original_publisher_zip_hash_crc_verified':True,
            'author_method_current_sign_step21_22_reproduced':True,
            'original_csv_files_processed':8,
            'original_measurement_rows':sum(x['raw_csv_rows'] for x in out),
            'cells':out,'possible_calibration_error_established':False,'temperature_causality_established':False,
            'independent_boundary_acceptance_established':False,'population_field_FPR_FNR_established':False,
            'commercial_release_allowed':False}

if __name__=='__main__':
    import sys
    obj=run(Path(sys.argv[1]));target=Path(sys.argv[2]);target.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
    for x in obj['cells']:
        print(x['source_cell'], 'delta_mAh',x['discharge_at_minus_et_mAh'], 'critical_trim_s',x['discharge_critical_AT_trim_s'], 'critical_current_mA',x['critical_relative_current_shift_mA'])
        for phase in ('ET','AT'):
            print(' ',phase,'DCH temp',x['original_source'][phase]['phases']['discharge']['mean_surface_temperature_C'])