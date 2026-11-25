"""Independent publisher archive: external domain check, not COM4 firmware proof."""
import csv, io, json, hashlib, math, sys, urllib.request, zipfile, re, collections
from pathlib import Path
from research.battery_curve_audit.graz_full_com4_threshold import select_lag, lag_feasible
URL='https://zenodo.org/records/13759419/files/Dataset_3_280Ah_battery_2.zip?download=1'
MD5='482af84591ffa307d8dfbf654d7816d4'
LIMIT=80_000_000
def numeric(x):
    x=x.strip()
    try:return float(x)
    except ValueError:
        if ':' in x:
            p=x.split(':')
            try:return sum(float(v)*60**i for i,v in enumerate(reversed(p)))
            except ValueError:pass
        raise
def matches(h):
    return len(h) in (17,21) and all(any(s in h[k].lower() for s in names) for k,names in [(6,('current','电流')),(7,('voltage','电压')),(15,('power','功率'))])
def scan_csv(raw):
    for enc in ('utf-8-sig','gb18030','utf-16'):
        try:
            sample=raw[:8192].decode(enc,errors='strict')
            break
        except UnicodeError:continue
    else:return {'status':'unknown_encoding'}
    try:dialect=csv.Sniffer().sniff(sample,delimiters=',;\t')
    except csv.Error:dialect=csv.excel
    reader=csv.reader(io.TextIOWrapper(io.BytesIO(raw),encoding=enc,newline=''),dialect)
    header=next(reader,[])
    if not matches(header):return {'status':'schema_unverified','header':header[:25]}
    c=collections.Counter(); prev=collections.deque(maxlen=2); first=None
    for line,row in enumerate(reader,2):
        if not row or not any(x.strip() for x in row):continue
        c['rows']+=1
        try:
            i,v,p=map(numeric,(row[6],row[7],row[15]))
            if not all(math.isfinite(x) for x in (i,v,p)):raise ValueError()
        except (ValueError,IndexError):
            c['invalid_signal']+=1;prev.clear();continue
        try:t=numeric(row[5])
        except (ValueError,IndexError):t=None
        if abs(p-v*i)<=1e-6:c['native_vi_equal_1e6']+=1
        if abs(abs(p)-abs(v*i))<=1e-6:c['native_abs_vi_equal_1e6']+=1
        if p==0 and abs(v*i)>=1:c['native_zero_nonzero_vi']+=1
        if i>=100 and v>0 and p>0:
            c['high_current_positive']+=1
            # Intentional re-quantization to Graz numeric grid; not native device calibration.
            vv,ii,pp=round(v,2),round(i,1),round(p)
            if pp>0:
                base=lag_feasible(vv,ii,pp)
                c['coarsened_baseline_pass' if base else 'coarsened_baseline_fail']+=1
                if len(prev)==2 and t is not None and prev[0][0] is not None and prev[1][0] is not None and 0<t-prev[0][0]<=4 and prev[0][0]<prev[1][0]<t and prev[0][1]>0 and prev[0][2]>=0 and prev[1][1]>0 and prev[1][2]>=0:
                    c['paired']+=1
                    _,pv,pi=prev[0]; pv,pi=round(pv,2),round(pi,1)
                    chosen=select_lag(vv,ii,pv,pi)
                    if chosen:c['triggered']+=1
                    shift=lag_feasible(pv,pi,pp) if chosen else base
                    k=('pass' if base else 'fail')+'_to_'+('pass' if shift else 'fail')
                    c[k]+=1
                    if not (base or shift):c['union_fail']+=1
                    if k in ('pass_to_fail','fail_to_pass') and first is None:first={'line':line,'outcome':k}
        prev.append((t,v,i))
    return {'status':'parsed','header':header,'counts':dict(c),'first_changed':first}
def selftest():
    header=['index','cycle','step','mode','time','total time','Current(A)','Voltage(V)','cap','cc','dc','energy','ce','de','abs time','Power(W)','temp']
    data=','.join(header)+'\n'+','.join(['1','1','1','charge','1','1','112.6','3.62','0','0','0','0','0','0','0','407.612','25'])+'\n'
    r=scan_csv(data.encode());assert r['counts']['native_vi_equal_1e6']==1
    assert r['counts']['high_current_positive']==1
    assert scan_csv(b'a,b,c\n1,2,3\n')['status']=='schema_unverified'
    print('3 external synthetic checks passed')
def main():
    selftest()
    if '--selftest' in sys.argv:return
    with urllib.request.urlopen(urllib.request.Request(URL,headers={'User-Agent':'CANO-research/1.0'}),timeout=120) as r:blob=r.read(LIMIT+1)
    if len(blob)>LIMIT or hashlib.md5(blob).hexdigest()!=MD5:raise ValueError('publisher checksum/size mismatch')
    out={'doi':'10.5281/zenodo.13759419','md5':MD5,'sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob),'files':{},'scope':'external different device; native P independence not established; Graz quantization imposed only for transfer stress test','physical_root_cause_proven':False}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        members=sorted((m for m in z.infolist() if not m.is_dir()),key=lambda m:m.filename)
        if sum(m.file_size for m in members)>800_000_000 or z.testzip() is not None:raise ValueError('unsafe/corrupt archive')
        csvs=[m for m in members if m.filename.lower().endswith('.csv')]
        out['inventory']=[{'name':m.filename,'bytes':m.file_size} for m in members]
        for m in csvs:
            out['files'][m.filename]=scan_csv(z.read(m))
    totals=collections.Counter()
    for f in out['files'].values():totals.update(f.get('counts',{}))
    out['totals']=dict(totals)
    out['parsed_csv_count']=sum(f['status']=='parsed' for f in out['files'].values())
    Path(sys.argv[1]).write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2))
    print('EXTERNAL_RESULT '+json.dumps({k:v for k,v in out.items() if k not in ('inventory','files')},sort_keys=True))
    print('EXTERNAL_SCHEMA '+json.dumps([{ 'file':k,'status':v['status'],'header':v.get('header')} for k,v in list(out['files'].items())[:5]],ensure_ascii=False))
if __name__=='__main__':main()
