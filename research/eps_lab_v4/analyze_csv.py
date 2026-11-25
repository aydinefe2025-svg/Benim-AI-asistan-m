"""Analyze one IV curve; never assign a fault label based on curve fit."""
import argparse,csv,json,hashlib,pathlib,sys
from pv_measured import audit,sparse_audit

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('csv',type=pathlib.Path,help='CSV headers V,I_A; strictly ascending voltage, at least 16 rows for default split');p.add_argument('--train',type=int,help='Fixed equally spaced index training count >=8; endpoints included');p.add_argument('--out',type=pathlib.Path,default=pathlib.Path('IV_RESULT.json'));args=p.parse_args()
    with args.csv.open(encoding='utf-8-sig',newline='') as f:
        rd=csv.DictReader(f)
        if rd.fieldnames!=['V','I_A']:raise ValueError('CSV must have exact headers V,I_A')
        rows=list(rd)
    v=[float(x['V']) for x in rows];i=[float(x['I_A']) for x in rows]
    r=audit(v,i) if args.train is None else sparse_audit(v,i,args.train)
    result={'status':'USER_CURVE_WITHIN_CURVE_HOLDOUT','source_csv_sha256':hashlib.sha256(args.csv.read_bytes()).hexdigest(),'result':r,'limits':'Same curve holdout, not device-independent validation or fault diagnosis. No instrument calibration or extrapolation guarantee.'};args.out.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8');print(json.dumps({k:r[k] for k in ('train_n','test_n','model','linear','pchip')},indent=2))
if __name__=='__main__':main()
