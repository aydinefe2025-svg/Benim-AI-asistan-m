"""Real same-source time-sample joins for original Graz cell02/03 logs and SP traces.

Source authentication precedes every calculation; no mechanical-impact interpretation,
no field FPR/FNR, no causality and no certified experiment-step equivalence.
"""
from __future__ import annotations
import argparse,bisect,datetime as dt,io,json,math,statistics,zipfile
from pathlib import Path
from research.battery_curve_audit import graz_source_preflight as core
from research.battery_curve_audit import graz_source_time_gate as timegate

TIME_FMT_SP='%d/%m/%Y %H:%M:%S'
TIME_FMT_LOG='%Y-%m-%d_%H-%M-%S-%f'

def _value(x:str)->float:
    f=float(x.strip())
    if not math.isfinite(f): raise ValueError('nonfinite original physical reading')
    return f

def log_samples(z:zipfile.ZipFile, member:zipfile.ZipInfo)->list[tuple[float,str,float,float]]:
    """Parse exact original header and source's local clock, preserving Device."""
    data=[]
    with z.open(member) as raw:
        header=raw.readline().decode('utf-8-sig',errors='strict').strip()
        if [q.strip() for q in header.split(',')]!=['Time','Device','Voltage','Current','Power']:
            raise ValueError('not original electrical log header')
        for ix,line in enumerate(raw,2):
            s=line.decode('utf-8-sig',errors='strict').strip()
            if not s:continue
            fields=[q.strip() for q in s.split(',')]
            if len(fields)!=5:raise ValueError(f'malformed electrical row {ix}')
            t=timegate.parse_log_token(fields[0])
            dev=fields[1]
            if not dev.startswith('COM'):raise ValueError('unknown electrical source Device tag')
            v,i,p=(_value(a) for a in fields[2:])
            if not 0<v<10 or abs(i)>200 or abs(p)>2000:
                raise ValueError('unphysical original electrical field')
            data.append((t,dev,v,i))
    if len(data)<100:raise ValueError('original electrical log too short')
    if len(data)>800000:raise ValueError('unbounded electrical source')
    return sorted(data,key=lambda s:s[0])

def sp_samples(z:zipfile.ZipFile, member:zipfile.ZipInfo)->tuple[list[tuple[float,float,float,float]],float]:
    """SP times are full local dates; sensor values in µm (do not infer force)."""
    sample=[];start=None;header_found=False
    with z.open(member) as raw:
        for ix,line in enumerate(raw,1):
            s=line.decode('utf-8-sig',errors='strict').strip()
            if s.startswith('Start time'):
                if start is not None:raise ValueError('duplicate SP Unix start')
                start=_value(s.split(':',1)[1])
            if 'Sensor 1[micro-m]' in s and 'Sensor 2[micro-m]' in s and 'Sensor 3[micro-m]' in s:
                header_found=True;continue
            if not header_found or not s:continue
            cols=[q.strip() for q in s.split('\t') if q.strip()]
            if len(cols)!=6:raise ValueError(f'malformed six-field SP row {ix}')
            when=dt.datetime.strptime(cols[0],TIME_FMT_SP)
            tm=timegate.vienna_epoch(when)
            x,zpos,s1,s2,s3=(_value(x) for x in cols[1:])
            sample.append((tm,s1,s2,s3))
            if len(sample)>400000:raise ValueError('SP recording too long')
    if start is None or not header_found or len(sample)<100:raise ValueError('SP original missing header or readings')
    if abs(sample[0][0]-start)>2.0:raise ValueError('SP source date header first epoch conflict')
    if any(b[0]<=a[0] for a,b in zip(sample,sample[1:])):raise ValueError('SP source time not strictly increasing')
    return sample,start

def _med(values:list[float])->float|None:
    return statistics.median(values) if values else None

def pair_samples(electric:list[tuple[float,str,float,float]],sp:list[tuple[float,float,float,float]],tolerance_s:float=2.5)->dict:
    """A nearest timestamp match, not an inferred phase match or lab certification."""
    if not (0<tolerance_s<=2.5):raise ValueError('time tolerance unsafe')
    if len(set(e[0] for e in electric))<2:raise ValueError('empty electrical time range')
    stamps=[a[0] for a in electric]
    if stamps!=sorted(stamps):raise ValueError('electrical data not time sorted')
    matched=[];ambiguous=0
    for s in sp:
        k=bisect.bisect_left(stamps,s[0])
        indices=[q for q in (k-1,k) if 0<=q<len(stamps)]
        near=sorted(((abs(stamps[q]-s[0]),q) for q in indices),key=lambda q:q[0])
        if not near or near[0][0]>tolerance_s:continue
        if len(near)>1 and abs(near[1][0]-near[0][0])<1e-6 and electric[near[1][1]][1:]!=electric[near[0][1]][1:]:
            ambiguous+=1;continue
        e=electric[near[0][1]]
        matched.append((s,e,near[0][0]))
    if not matched:
        return {'matched_sp_samples':0,'total_sp_samples':len(sp),'median_abs_time_error_s':None,
                'unmatched_sp_samples':len(sp),'ambiguous_matches':ambiguous,'overlap_verified':False,
                'sampled_current_sign_counts':None,'sensor1_um_end_minus_start':None,'sensor2_um_end_minus_start':None}
    time_errors=[q[2] for q in matched]
    pos=sum(e[3]>0.1 for s,e,d in matched);neg=sum(e[3]<-0.1 for s,e,d in matched)
    n=len(matched);extent=min(25,max(1,n//10))
    return {'matched_sp_samples':n,'total_sp_samples':len(sp),
            'unmatched_sp_samples':len(sp)-n,'ambiguous_matches':ambiguous,
            'median_abs_time_error_s':_med(time_errors),
            'max_abs_time_error_s':max(time_errors),
            'overlap_verified':True,'first_matched_epoch_s':matched[0][0][0],
            'last_matched_epoch_s':matched[-1][0][0],
            'sampled_current_sign_counts':{'positive':pos,'negative':neg,'near_zero':n-pos-neg},
            'matched_electrical_device_labels':sorted({e[1] for _,e,_ in matched}),
            'sensor1_um_end_minus_start':_med([x[0][1] for x in matched[-extent:]])-_med([x[0][1] for x in matched[:extent]]),
            'sensor2_um_end_minus_start':_med([x[0][2] for x in matched[-extent:]])-_med([x[0][2] for x in matched[:extent]]),
            'sensor3_um_end_minus_start':_med([x[0][3] for x in matched[-extent:]])-_med([x[0][3] for x in matched[:extent]]),
            'sensor_delta_interpretation':'descriptive time-matched sensor displacement only; not a calibrated force or between-cell capacity causal effect'}

def inspect_alignment(blob:bytes,size:int)->dict:
    cert=core.inspect_archive(blob,size)
    result={};pair_index=[]
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for cell in ('02','03'):
            logs=[x for x in z.infolist() if core.explicit_cell_in_path(x.filename)==cell and core.role_for_member(x.filename)=='charge_discharge_log_candidate']
            sps=[x for x in z.infolist() if core.explicit_cell_in_path(x.filename)==cell and core.role_for_member(x.filename)=='thickness_sp_candidate']
            if len(logs)!=1 or len(sps)!=3:raise ValueError('physical specimen original file count mismatch')
            e=log_samples(z,logs[0])
            pairs=[]
            for m in sorted(sps,key=lambda q:q.filename):
                s,start=sp_samples(z,m)
                p=pair_samples(e,s)
                p.update({'sp_filename':Path(m.filename).name,'source_cell':cell,'physical_preload_kN':core.CELL_PRELOAD_KN[cell],
                          'sp_start_epoch':start,'sp_first_epoch':s[0][0],'sp_last_epoch':s[-1][0],
                          'log_start_epoch':e[0][0],'log_last_epoch':e[-1][0],
                          'full_synchronized_lab_phase_verified':False})
                pairs.append(p)
            result[cell]={'electrical_original_rows':len(e),'sp_files':pairs,'source_device_labels':sorted({a[1] for a in e}),
                          'electrical_total_time_span_s':e[-1][0]-e[0][0]}
            pair_index.extend((cell,x) for x in pairs)
    overlapping=sum(p['overlap_verified'] for _,p in pair_index)
    return {'source_doi':core.DOI,'original_zip_sha256':cert['original_zip_sha256'],
       'publisher_md5_crc_verified':True,'cells':result,
       'same_cell_sp_files_total':len(pair_index),'same_cell_timestamp_overlapping_sp_files':overlapping,
       'same_cell_timestamp_disjoint_sp_files':len(pair_index)-overlapping,
       'cross_cell_source_labels_never_joined':True,
       'physical_samples':2,'genuine_original_measurement_series':8,
       'independent_calibration_verified':False,'exact_experiment_step_homology_verified':False,
       'sp_signal_5second_clocks_are_timestamp_joined':True,
       'physical_impact_trial':False,'field_false_positive_rate':None,
       'independent_capacity_loss_estimate':None}

def main()->None:
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);args=p.parse_args()
    blob,size=core.get_original();d=inspect_alignment(blob,size)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(d,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    for cell,v in d['cells'].items():
        print('ORIGINAL_PHYSICAL_CELL',cell,v['electrical_original_rows'])
        for r in v['sp_files']:print('SP_FULL_TIMESERIES',cell,r['sp_filename'],r['matched_sp_samples'],r['total_sp_samples'])
    print('DELAY_AND_CURRENT_SIGN_MATCHED_NOT_CERTIFIED_LAB_PHASE')
if __name__=='__main__':main()