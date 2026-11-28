"""Sandia V5: observed MPP change, calibration sensitivity, and condition provenance.
No causal degradation or calibrated correction claimed. Source: DOI 10.11578/3818365.
"""
import csv, hashlib, json, math, pathlib, statistics, collections, sys
SOURCE_PIN='8fe450440d989f9aa469f0fc206c76b13021a93dbb6071ddc3a1967fd083440e'
FIELDS=('RefA','RefRefA','Measured_Temperature_(C)','Simulator_Make','Simulator_Model','IV_Lab_Location','Temp_Measurement_Method','IV_Date','IV_Time','Mod_ID')
def number(s,positive=False):
    try:x=float(s)
    except (TypeError,ValueError):return None
    return x if math.isfinite(x) and (not positive or x>0) else None

def evaluate(pair, measured, reference):
    a,b=pair['iv_curve'],pair['ref_curve']
    v=100*math.log(a['V_at_sampled_Pmax']/b['V_at_sampled_Pmax']);i=100*math.log(a['I_at_sampled_Pmax']/b['I_at_sampled_Pmax']);p=100*math.log(a['sampled_Pmax_W']/b['sampled_Pmax_W'])
    if not math.isclose(v+i,p,abs_tol=1e-9):raise ValueError('power identity failure')
    m=measured or {};r=reference or {};c=number(m.get('RefA'),True);rc=number(m.get('RefRefA'),True);actual_ref=number(r.get('RefA'),True)
    t=number(m.get('Measured_Temperature_(C)'));rt=number(r.get('Measured_Temperature_(C)'))
    proxy=100*((a['sampled_Pmax_W']/b['sampled_Pmax_W'])*rc/c-1) if c is not None and rc is not None else None
    same_setup=bool(reference) and all(m.get(k) and m.get(k)==r.get(k) for k in ('Simulator_Make','Simulator_Model','IV_Lab_Location'))
    if a['sha256']==b['sha256']:status='SELF_REFERENCE'
    elif c is None or rc is None:status='CALIBRATION_UNVERIFIED'
    elif not reference or t is None or rt is None or actual_ref is None:status='REFERENCE_CONDITIONS_UNVERIFIED'
    elif not math.isclose(rc,actual_ref,rel_tol=1e-6,abs_tol=1e-8):status='CALIBRATION_CONFLICT'
    elif not same_setup or abs(t-rt)>1:status='CONDITION_DIFFERENCE'
    else:status='CONDITION_COMPARABLE_SCREEN'
    pd=pair['published_Pmp_difference_pct']
    return dict(module=pair['module'],iv=pair['iv'],ref=pair['ref'],date=pair['date'],ref_date=pair['ref_date'],days=pair['days'],status=status,causal_status='NOT_IDENTIFIED',raw_change_pct=pair['change_pct'],log_voltage_pct=v,log_current_pct=i,log_power_pct=p,calibration_A=c,reference_calibration_A=rc,reference_metadata_calibration_A=actual_ref,measured_temperature_C=t,reference_temperature_C=rt,current_proxy_adjusted_change_pct=proxy,same_setup=same_setup,pmp_review=pd is None or abs(pd)>1)

def summary(xs):
    return dict(n=len(xs),median=statistics.median(xs),min=min(xs),max=max(xs),negative=sum(x<0 for x in xs),positive=sum(x>0 for x in xs)) if xs else {'n':0}

def audit(receipt, metadata=None):
    pairs=receipt['pairs'];assert len(pairs)==613 and len({p['module'] for p in pairs})==438
    idx=collections.defaultdict(list)
    if metadata is not None:
        for m in metadata:idx[m['IVPath'].removeprefix('./')].append(m)
    def lookup(path):
        g=idx.get(path,[])
        if not g or len({tuple(m.get(k,'') for k in FIELDS) for m in g})!=1:return None
        return g[0]
    pair_idx={p['iv']:p for p in pairs}; out=[]
    for p in pairs:
        m=lookup(p['iv']);ref_path='IV/'+p['ref'].split('/')[-1];other=pair_idx.get(ref_path);r=None
        # Only reuse reference conditions from an exact same module, date and byte-identical IV curve.
        if other and other['module']==p['module'] and other['date']==p['ref_date'] and other['iv_curve']['sha256']==p['ref_curve']['sha256']:
            r=lookup(ref_path)
        out.append(evaluate(p,m,r))
    by=collections.defaultdict(list)
    for x in out:by[x['module']].append(x)
    latest=[max(g,key=lambda x:x['date']) for g in by.values()];later=[x for x in latest if x['days']>0 and x['status']!='SELF_REFERENCE'];comparable=[x for x in later if x['status']=='CONDITION_COMPARABLE_SCREEN'];proxy=[x for x in later if x['current_proxy_adjusted_change_pct'] is not None]
    return {'status':'SANDIA_V5_CONDITION_GATE','metadata_loaded':metadata is not None,'metadata_rows':len(metadata) if metadata is not None else None,'all_count':len(out),'latest_count':len(latest),'later_count':len(later),'all_status':dict(collections.Counter(x['status'] for x in out)),'latest_later_status':dict(collections.Counter(x['status'] for x in later)),'raw_later':summary([x['raw_change_pct'] for x in later]),'voltage_log_later':summary([x['log_voltage_pct'] for x in later]),'current_log_later':summary([x['log_current_pct'] for x in later]),'power_log_later':summary([x['log_power_pct'] for x in later]),'same_subset_raw':summary([x['raw_change_pct'] for x in proxy]),'proxy_adjusted':summary([x['current_proxy_adjusted_change_pct'] for x in proxy]),'proxy_sign_flips':sum((x['raw_change_pct']<0)!=(x['current_proxy_adjusted_change_pct']<0) for x in proxy),'comparable_raw':summary([x['raw_change_pct'] for x in comparable]),'causal_labels':0,'records':out,'limits':'Calibration-current ratio is a first-order sensitivity assuming linear effective irradiance response and no other change, not certified correction. 1 C and 1% Pmp screen thresholds are analyst-selected. Matching reference metadata requires exact byte-identical archived IV, module and date. No reference temperature imputation. No causal degradation or physical calibration claim.'}

def main():
    p=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else 'SANDIA_PAIRED_POWER_RECEIPT.json'); d=json.loads(p.read_text());meta=None
    if len(sys.argv)>2:
        q=pathlib.Path(sys.argv[2]);assert hashlib.sha256(q.read_bytes()).hexdigest()==SOURCE_PIN,'metadata hash mismatch'
        with q.open(encoding='utf-8-sig',newline='') as f:meta=list(csv.DictReader(f))
        assert len(meta)==616
    result=audit(d,meta);pathlib.Path('SANDIA_CONDITION_GATE_V5.json').write_text(json.dumps(result,indent=2,allow_nan=False));print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
if __name__=='__main__':main()
