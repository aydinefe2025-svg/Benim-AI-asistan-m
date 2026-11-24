"""Full source threshold falsification; no physical calibration or root-cause claim."""
import collections, hashlib, io, json, math, sys, zipfile
from pathlib import Path
from research.battery_curve_audit import graz_source_preflight as source
from research.battery_curve_audit import graz_current_power_audit as prior
from research.battery_curve_audit import graz_com4_transition_audit as boundary
from research.battery_curve_audit.graz_power_reconstruction import DIGEST

def interval(v,i):
    vc=round(v*100); ic=round(i*10)
    if v<0 or i<0 or abs(v*100-vc)>1e-7 or abs(i*10-ic)>1e-7:
        raise ValueError("hypothetical grid does not cover record")
    return max(0,2*vc-1)*max(0,2*ic-1), (2*vc+1)*(2*ic+1)

MODELS=("pre_nearest","pre_floor","pre_ceil","post_nearest","post_floor","post_ceil")
def compatible(lo,hi,p,model):
    # All bounds in units of 1/4000, conservative closed ties.
    if p<0 or p!=round(p):return False
    n=int(p); scale=4000
    kind,rule=model.split('_')
    offsets={'nearest':(-2000,2000),'floor':(0,4000),'ceil':(-4000,0)}
    a,b=offsets[rule]
    if n==0:
        cutoff=20*scale if kind=='pre' else 20*scale+a
        return lo<=cutoff
    if kind=='post' and n<20:return False
    left=n*scale+a
    if kind=='pre':left=max(left,20*scale)
    return max(lo,left)<=min(hi,n*scale+b)

def magnitude_gap(lo,hi,p):
    # Additive error in positive reported power only, after the latent 20-unit gate.
    # Numerator units are 1/4000 of a logged power unit; closed intervals.
    if p<=0 or p!=round(p):raise ValueError('positive integer power required')
    lo=max(lo,80000)
    if lo>hi:raise ValueError('latent gate infeasible')
    target=int(p)*4000
    return max(0,lo-(target+2000),(target-2000)-hi)

def holdout(histograms):
    out={}
    for cell,test in histograms.items():
        train=collections.Counter()
        for other,h in histograms.items():
            if other!=cell:train.update(h)
        n=sum(train.values())
        limit=max(train)
        q99=next(k for k in sorted(train) if sum(train[j] for j in train if j<=k)*100>=99*n)
        out[cell]={'train_positive_rows':n,'test_positive_rows':sum(test.values()),
                   'train_max_tolerance':limit/4000,'train_q99_tolerance':q99/4000,
                   'test_max_required_tolerance':max(test)/4000,
                   'test_outside_train_max':sum(v for k,v in test.items() if k>limit),
                   'test_outside_train_q99':sum(v for k,v in test.items() if k>q99)}
    return out

def scan(rows):
    counts=collections.Counter(); extrema={}; model_bad=collections.Counter(); witnesses={}; gaps=collections.Counter()
    def witness(key,val,row,maximum):
        if key not in extrema or (val>extrema[key]['numerator'] if maximum else val<extrema[key]['numerator']):
            extrema[key]={'numerator':val,'line':row.line,'v':row.v,'i':row.i,'p':row.p}
    for r in rows:
        if r.device!='COM4': continue
        counts['COM4']+=1
        zero=r.p==0
        counts['zero' if zero else 'nonzero']+=1
        if not all(math.isfinite(x) for x in (r.v,r.i,r.p)):raise ValueError('nonfinite')
        try: lo,hi=interval(r.v,r.i)
        except ValueError:
            counts['off_grid']+=1; continue
        # exact integer arithmetic, power numerator /4000. Closed upper interval
        # is conservative: an impossibility remains impossible with open ends.
        if not zero:
            gaps[magnitude_gap(lo,hi,r.p)]+=1
        for model in MODELS:
            if not compatible(lo,hi,r.p,model):
                model_bad[model]+=1
                witnesses.setdefault(model,{'line':r.line,'v':r.v,'i':r.i,'p':r.p,'lo':lo/4000,'hi':hi/4000})
        if zero:
            witness('max_zero_lower',lo,r,True)
            if lo>=80000:counts['zero_impossible_T20']+=1
        else:
            witness('min_nonzero_upper',hi,r,False)
            if hi<80000:counts['nonzero_impossible_T20']+=1
        if (r.v*r.i<20)!=zero:counts['logged_product_T20_mismatch']+=1
    a=extrema['max_zero_lower']['numerator']; b=extrema['min_nonzero_upper']['numerator']
    return {'counts':dict(counts),'extrema':extrema,'necessary_interval_T':{'strict_lower':a/4000,'conservative_upper':b/4000},'any_threshold_possible_on_grid':a<b,'model_incompatible':{m:model_bad[m] for m in MODELS},'model_witnesses':witnesses,'positive_gap_histogram':dict(gaps)}

def selftest():
    assert interval(4.34,4.6)==(78897,80817)
    a=boundary.Row(1,0,'COM4',4.34,4.6,0)
    b=boundary.Row(2,1,'COM4',4.34,4.6,20)
    assert scan([a,b])['any_threshold_possible_on_grid']
    c=boundary.Row(3,2,'COM4',4.34,3.0,13)
    assert not scan([a,c])['any_threshold_possible_on_grid']
    assert scan([a,c])['counts']['nonzero_impossible_T20']==1
    assert compatible(78897,80817,20,'pre_nearest')
    assert compatible(78897,80817,0,'pre_nearest')
    assert not compatible(78897,80817,0,'post_nearest')
    assert not compatible(78897,80817,99,'pre_nearest')
    assert not compatible(78897,80817,19,'post_floor')
    assert compatible(80000,80000,20,'pre_floor')
    assert magnitude_gap(78897,80817,20)==0
    assert magnitude_gap(522053,524949,130)==53
    assert magnitude_gap(80000,80000,21)==2000
    folds=holdout({'a':{0:99,100:1},'b':{0:98,200:2}})
    assert folds['a']['test_outside_train_max']==0
    assert folds['b']['test_outside_train_max']==2
    assert folds['b']['test_outside_train_q99']==2
    print('16 synthetic checks passed')
def main():
    selftest()
    if '--selftest' in sys.argv:return
    blob,size=source.get_original()
    cert=source.inspect_archive(blob,size)
    if cert['original_zip_sha256']!=prior.EXPECTED_SHA256:raise ValueError('source sha')
    cells={}; ids=[]; rowcount=0
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for cell in prior.CELLS:
            ms=[m for m in z.infolist() if not m.is_dir() and source.explicit_cell_in_path(m.filename)==cell and source.role_for_member(m.filename)=='charge_discharge_log_candidate']
            if len(ms)!=1:raise ValueError('log count')
            rows,h=boundary.parse_member(z,ms[0]); ids.extend(h); rowcount+=len(rows)
            cells[cell]=scan(rows); del rows
    digest=hashlib.sha256(json.dumps(sorted(ids),separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    if digest!=DIGEST or len(ids)!=1900 or rowcount!=prior.EXPECTED_ROWS:raise ValueError('source counts/identity')
    lower=max(c['extrema']['max_zero_lower']['numerator'] for c in cells.values())
    upper=min(c['extrema']['min_nonzero_upper']['numerator'] for c in cells.values())
    total=collections.Counter()
    for c in cells.values():total.update(c['counts'])
    d={'goal_key':'graz-full-com4-threshold-identifiability-20261124','source_sha256':cert['original_zip_sha256'],'source_rows':rowcount,'flagged_identity_sha256':digest,'cells':cells,'all_counts':dict(total),'global_threshold_strict_lower':lower/4000,'global_threshold_conservative_upper':upper/4000,'global_any_threshold_possible_on_grid':lower<upper,'all_rows_grid_covered':not total['off_grid'],'rounding_assumption':'nearest 0.01 V and 0.1 I numeric; closed conservative intervals','model_incompatible_all':{m:sum(c['model_incompatible'][m] for c in cells.values()) for m in MODELS},'model_assumptions':'threshold fixed at 20; integer power quantization, conservative closed bounds; pre vs post clipping', 'holdout':holdout({k:v.pop('positive_gap_histogram') for k,v in cells.items()}),'holdout_scope':'post-hoc model chosen using same five cells, leave-one-cell-out tolerance fitting only; positive power magnitude, not independent physical calibration', 'physical_root_cause_proven':False,'physical_units_verified':False,'physical_production_release_allowed':False}
    Path(sys.argv[1]).write_text(json.dumps(d,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps(d,sort_keys=True))
if __name__=='__main__':main()
