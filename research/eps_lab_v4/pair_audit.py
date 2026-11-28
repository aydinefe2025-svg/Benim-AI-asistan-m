"""Pinned Sandia IV data: exact metadata links, sampled max power, no causal ageing claim."""
import csv, collections, io, json, math, pathlib, hashlib, statistics, zipfile, datetime
PINS={'AnonDB.csv':'8fe450440d989f9aa469f0fc206c76b13021a93dbb6071ddc3a1967fd083440e','IV.zip':'8635883ce49c51d015bdbf315c1408fda39d12d55a671d1ddc8b21284334edd7','RefIV.zip':'ab4376f7d04b5accde42e194253592a1abe6831d153f96377808c08b92b27ce4'}
def name(path,folder):
    path=path.removeprefix('./')
    if not path.startswith(folder+'/') or len(path.split('/'))!=2 or not path.endswith('.csv'):raise ValueError('invalid member path')
    return path

def curve(raw):
    r=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not {'V','I'}.issubset(r.fieldnames or []):raise ValueError('missing V/I')
    pts=[(float(x['V']),float(x['I'])) for x in r]
    if len(pts)<8 or not all(math.isfinite(v) and math.isfinite(i) for v,i in pts):raise ValueError('invalid samples')
    q=[(v*i,v,i) for v,i in pts if v>=0 and i>=0]
    if not q or max(q)[0]<=0:raise ValueError('no positive power')
    p,v,i=max(q)
    return {'n':len(pts),'sampled_Pmax_W':p,'V_at_sampled_Pmax':v,'I_at_sampled_Pmax':i,'sha256':hashlib.sha256(raw).hexdigest(),'nonincreasing_V_pairs':sum(b[0]<=a[0] for a,b in zip(pts,pts[1:]))}

def summarize(xs):
    return dict(n=len(xs),median=statistics.median(xs),min=min(xs),max=max(xs),negative=sum(x<0 for x in xs),positive=sum(x>0 for x in xs)) if xs else {'n':0}

def main():
    for n,h in PINS.items():
        if hashlib.sha256(pathlib.Path(n).read_bytes()).hexdigest()!=h:raise ValueError('source hash mismatch: '+n)
    rows=list(csv.DictReader(open('AnonDB.csv',encoding='utf-8-sig',newline='')))
    outcomes=[];excluded=[];cache={}
    with zipfile.ZipFile('IV.zip') as iv,zipfile.ZipFile('RefIV.zip') as ref:
        if iv.testzip() or ref.testzip():raise ValueError('CRC')
        for j,r in enumerate(rows,2):
            try:
                a=name(r['IVPath'],'IV'); b=name(r['RefIVPath'],'RefIV');mid=r['Mod_ID'].strip()
                if not mid or a.split('/')[-1].split('_')[0]!=mid or b.split('/')[-1].split('_')[0]!=mid:raise ValueError('module ID mismatch')
                dt=datetime.datetime.strptime(r['IV_Date'],'%m/%d/%Y').date(); dr=datetime.datetime.strptime(r['Ref_IV_Date'],'%m/%d/%Y').date()
                if dt<dr:raise ValueError('reference after measurement')
                for z,k in [(iv,a),(ref,b)]:
                    if k not in cache:cache[k]=curve(z.read(k))
                x,y=cache[a],cache[b]; change=100*(x['sampled_Pmax_W']/y['sampled_Pmax_W']-1)
                try:
                    published=float(r['Pmp_(W)']); residual=100*(x['sampled_Pmax_W']/published-1) if published>0 and math.isfinite(published) else None
                except ValueError:residual=None
                outcomes.append({'metadata_row':j,'module':mid,'iv':a,'ref':b,'days':(dt-dr).days,'iv_curve':x,'ref_curve':y,'change_pct':change,'published_Pmp_difference_pct':residual,'date':str(dt),'ref_date':str(dr),'temperature_C':r['Measured_Temperature_(C)']})
            except (ValueError,KeyError,TypeError,UnicodeError) as e:excluded.append({'metadata_row':j,'module':r.get('Mod_ID'),'reason':str(e),'iv':r.get('IVPath'),'ref':r.get('RefIVPath')})
        iv_names={n for n in iv.namelist() if n.startswith('IV/') and n.endswith('.csv')};ref_names={n for n in ref.namelist() if n.startswith('RefIV/') and n.endswith('.csv')}
    by=collections.defaultdict(list)
    for r in outcomes:by[r['iv']].append(r)
    unique=[];conflicts=[]
    for a,group in sorted(by.items()):
        if len({(x['module'],x['ref'],x['date'],x['ref_date']) for x in group})!=1:conflicts.append(a);continue
        unique.append(group[0])
    modules=collections.defaultdict(list)
    for r in unique:modules[r['module']].append(r)
    # One latest observation per module, only if reference unambiguous and date not tied.
    latest=[];ambiguous=[]
    for m,g in sorted(modules.items()):
        last=max(x['date'] for x in g);l=[x for x in g if x['date']==last]
        if len(l)!=1 or len({x['ref'] for x in g})!=1:ambiguous.append(m);continue
        latest.append(l[0])
    out={'status':'SANDIA_EXACT_METADATA_LINKED_RAW_POWER_COMPARISON','source_hashes':PINS,'metadata_rows':len(rows),'valid_metadata_rows':len(outcomes),'excluded':excluded,'duplicate_metadata_rows':len(outcomes)-len(by),'conflicting_iv_links':conflicts,'unique_iv_pairs':len(unique),'unique_modules':len(modules),'unmatched_iv_names':sorted(iv_names-{r['iv'] for r in unique}),'unmatched_ref_names':sorted(ref_names-{r['ref'] for r in unique}),'latest_ambiguous_modules':ambiguous,'latest_module_count':len(latest),'all_pairs_change_pct':summarize([r['change_pct'] for r in unique]),'latest_per_module_change_pct':summarize([r['change_pct'] for r in latest]),'published_pmp_difference_pct':summarize([abs(r['published_Pmp_difference_pct']) for r in unique if r['published_Pmp_difference_pct'] is not None]),'raw_sample_counts':{k:sum(v['n'] for n,v in cache.items() if n.startswith(k+'/')) for k in ('IV','RefIV')},'pairs':unique,'limits':'Sampled maximum VI in positive quadrant; not calibrated true MPP or normalized degradation; illumination/temperature and protocol may differ. Metadata links require exact paths, IDs, chronology. Module latest descriptive only, not iid.'}
    pathlib.Path('SANDIA_PAIRED_POWER_RECEIPT.json').write_text(json.dumps(out,indent=2,allow_nan=False));print(json.dumps({k:v for k,v in out.items() if k!='pairs'},indent=2))
if __name__=='__main__':main()