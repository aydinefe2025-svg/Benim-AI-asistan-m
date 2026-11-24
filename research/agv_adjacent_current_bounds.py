"""Conditional Ah/operating-hour estimates, no capacity or independent current measurement.
Assume same unit-Ah quantizer (round-to-nearest or floor) at each cumulative endpoint;
then difference error <=1 Ah. Time is used as recorded, not calibrated.
"""
import collections,csv,datetime,hashlib,io,json,pathlib,statistics

def bounds(q,t):
    if t<=0:return None
    return (3600*max(0,q-1)/t,3600*(q+1)/t)

def stats(x):
    return {'n':len(x),'min':min(x),'median':statistics.median(x),'max':max(x)} if x else {'n':0}

def analyze(rows):
    groups=collections.defaultdict(list)
    for r in rows:
        n,t,q=int(r['counter']),int(r['cycletime']),int(r['totaldischarge'])
        if min(n,t,q)<0:raise ValueError('negative raw field')
        groups[r['battery']].append((n,t,q,datetime.date.fromisoformat(r['date'])))
    pairs=[];packs={};gaps=0
    for pack,arr in sorted(groups.items()):
        arr.sort(); pp=[];runs=[];pgaps=0;run=None
        for a,b in zip(arr,arr[1:]):
            if b[0]<=a[0] or b[2]<a[2] or b[3]<a[3]:raise ValueError('counter/date/discharge order violated')
            if b[0]!=a[0]+1:
                gaps+=1;pgaps+=1;run=None;continue
            q=b[2]-a[2];t=b[1];days=(b[3]-a[3]).days
            interval=bounds(q,t)
            p={'pack':pack,'previous_counter':a[0],'counter':b[0],'previous_date':a[3].isoformat(),'date':b[3].isoformat(),'days_between_start_dates':days,'previous_Ah':a[2],'end_Ah':b[2],'delta_Ah':q,'previous_operating_s':a[1],'operating_s':t,'current_interval_A':list(interval) if interval else None,'nominal_A':q*3600/t if t>0 else None,'previous_time_sensitivity_A':q*3600/a[1] if a[1]>0 else None}
            pp.append(p);pairs.append(p)
            if interval is None:run=None;continue
            if run is None:
                run={'first_counter':a[0],'last_counter':b[0],'delta_Ah':q,'seconds':t,'pairs':1};runs.append(run)
            else:
                run['last_counter']=b[0];run['delta_Ah']+=q;run['seconds']+=t;run['pairs']+=1
        valid=[p for p in pp if p['current_interval_A'] is not None]
        sec=sum(r['seconds'] for r in runs);q=sum(r['delta_Ah'] for r in runs)
        lo=sum(max(0,r['delta_Ah']-1) for r in runs);hi=sum(r['delta_Ah']+1 for r in runs)
        local=[p for p in valid if p['days_between_start_dates']<=1]
        packs[pack]={'source_rows':len(arr),'adjacent_count':len(pp),'gap_count':pgaps,'valid_positive_time':len(valid),'zero_time':len(pp)-len(valid),'zero_delta_count':sum(p['delta_Ah']==0 for p in pp),'positive_delta_count':sum(p['delta_Ah']>0 for p in pp),'day_gap_le_1_valid':len(local),'day_gap_gt_1_valid':len(valid)-len(local),'delta_ge_5_valid':sum(p['delta_Ah']>=5 for p in valid),'delta_ge_10_valid':sum(p['delta_Ah']>=10 for p in valid),'nominal_current_A':stats([p['nominal_A'] for p in valid]),'local_day_nominal_current_A':stats([p['nominal_A'] for p in local]),'valid_runs':len(runs),'longest_run_pairs':max((r['pairs'] for r in runs),default=0),'sum_delta_Ah':q,'sum_operating_s':sec,'duration_weighted_nominal_A':3600*q/sec if sec else None,'telescoped_current_interval_A':[3600*lo/sec,3600*hi/sec] if sec else None,'runs':runs}
    return {'adjacent_count':len(pairs),'gap_count':gaps,'packs':packs,'pairs':pairs}

def main():
    from agv_discharge_counter_audit import fetch,PIN
    raw=fetch('dataset.csv');doc=fetch('README.adoc')
    if hashlib.sha256(raw).hexdigest()!='13026bae4a98790a45d43fb6ed28ed0c0777adc098647eb07b5d20b9a034964b':raise ValueError('CSV SHA changed')
    if 'Totally cumulated discharge at the end of the observation cycle' not in doc.decode():raise ValueError('publisher endpoint contract changed')
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))));out=analyze(rows)
    if len(rows)!=57880 or len(out['packs'])!=10 or out['adjacent_count']!=988 or out['gap_count']!=56882:raise ValueError('original source baseline mismatch')
    out.update(status='AGV_CONDITIONAL_ADJACENT_DISCHARGE_RATE_BOUNDS',source_rows=len(rows),source_md5=PIN,csv_sha256=hashlib.sha256(raw).hexdigest(),readme_sha256=hashlib.sha256(doc).hexdigest(),assumptions=['Cumulative Ah at observation END as publisher README; use current row operating time, only adjacent observation counters.','Same 1 Ah quantizer at both endpoints, nearest rounding or truncation; quantization-only envelope +/-1 Ah, nonnegative lower bound. Quantization convention is not verified.','No extra discharge outside recorded operating time between endpoints; not verified.','No time uncertainty or calibration error included. Date is cycle START date only.','Conditional Ah per operating hour, not a measured current waveform or capacity/SoH. Selected pairs do not represent all operations.'])
    pathlib.Path('AGV_ADJACENT_CURRENT_RECEIPT.json').write_text(json.dumps(out,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in out.items() if k not in ('pairs','packs')},indent=2));print(json.dumps({p:{k:v for k,v in x.items() if k!='runs'} for p,x in out['packs'].items()},indent=2))
if __name__=='__main__':main()