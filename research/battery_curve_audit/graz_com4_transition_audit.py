"""Source-pinned COM4 zero-power boundary audit; numeric states, not real controller phases."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, io, json, math, zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from research.battery_curve_audit import graz_source_preflight as source
from research.battery_curve_audit import graz_current_power_audit as prior

@dataclass(frozen=True, slots=True)
class Row:
    line:int
    t:float
    device:str
    v:float
    i:float
    p:float

def state(r):
    vi=r.v*r.i
    if abs(vi)<.01:return 'small_vi'
    if abs(r.p/vi-1)<=.05:return 'consistent_vi'
    if r.device=='COM4' and r.p==0 and abs(vi)>=1:return 'flagged_zero_p'
    raise ValueError('different discrepancy than pinned prior source')

def describe(r, edge):
    if r is None:return None
    return {'line':r.line,'device':r.device,'numeric_state':state(r),
            'offset_seconds':round(r.t-edge.t,6), 'voltage_numeric':r.v,
            'current_numeric':r.i,'power_numeric':r.p}

def audit_rows(rows):
    flags=[];counts=Counter();old=None
    for j,r in enumerate(rows):
        if (r.device not in ('COM3','COM4') or not all(math.isfinite(x) for x in (r.t,r.v,r.i,r.p))
            or not 0<r.v<10 or abs(r.i)>200 or abs(r.p)>2000
            or (old is not None and (r.line<=old.line or r.t<=old.t))):raise ValueError('invalid original row sequence')
        s=state(r);counts[r.device+'/'+s]+=1
        if s=='flagged_zero_p':flags.append(j)
        old=r
    groups=[]
    for j in flags:
        if not groups or rows[j].line-rows[groups[-1][-1]].line>4:groups.append([j])
        else:groups[-1].append(j)
    episodes=[]
    for g in groups:
        a,b=g[0],g[-1];first,last=rows[a],rows[b]
        prev=rows[a-1] if a else None;nxt=rows[b+1] if b+1<len(rows) else None
        ps=next((rows[j] for j in range(a-1,-1,-1) if rows[j].device=='COM4'),None)
        ns=next((rows[j] for j in range(b+1,len(rows)) if rows[j].device=='COM4'),None)
        # Distinguish immediate boundaries from nearest same-device sample (may be far away).
        episodes.append({'first_line':first.line,'last_line':last.line,'flagged_rows':len(g),
            'intervening_unflagged_rows':b-a+1-len(g),
            'duration_seconds':round(last.t-first.t,6),
            'before_immediate':describe(prev,first),'after_immediate':describe(nxt,last),
            'before_same_device':describe(ps,first),'after_same_device':describe(ns,last),
            'first_flag':describe(first,first),'last_flag':describe(last,last),
            'before_20_rows_states':dict(Counter(x.device+'/'+state(x) for x in rows[max(0,a-20):a])),
            'after_20_rows_states':dict(Counter(x.device+'/'+state(x) for x in rows[b+1:b+21]))})
    return {'rows':len(rows),'flagged_rows':len(flags),'numeric_state_counts':dict(counts),'episodes':episodes}

def parse_member(z,m):
    rows=[];hashes=[]
    with z.open(m) as f:
        if tuple(x.strip() for x in f.readline().decode('utf-8-sig').strip().split(','))!=prior.EXPECTED_COLS:raise ValueError('header')
        for n,raw in enumerate(f,2):
            s=raw.decode('utf-8-sig').strip()
            if not s:continue
            time,dev,v,i,p=(x.strip() for x in s.split(','))
            # Monotonic local recorded time, not physical UTC calibration.
            t=(dt.datetime.strptime(time,'%Y-%m-%d_%H-%M-%S-%f')-dt.datetime(1970,1,1)).total_seconds()
            row=Row(n,t,dev,float(v),float(i),float(p));rows.append(row)
            if state(row)=='flagged_zero_p':hashes.append((m.filename,n,hashlib.sha256(raw).hexdigest()))
            if len(rows)>800000:raise ValueError('source size')
    return rows,hashes

def inspect(blob,size):
    cert=source.inspect_archive(blob,size)
    if cert['original_zip_sha256']!=prior.EXPECTED_SHA256:raise ValueError('source hash')
    cells={};hashes=[]
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for c in prior.CELLS:
            ms=[m for m in z.infolist() if not m.is_dir() and source.explicit_cell_in_path(m.filename)==c and source.role_for_member(m.filename)=='charge_discharge_log_candidate']
            if len(ms)!=1:raise ValueError('log count')
            rows,hh=parse_member(z,ms[0]);hashes.extend(hh);cells[c]=audit_rows(rows)
    if sum(x['rows'] for x in cells.values())!=prior.EXPECTED_ROWS:raise ValueError('source rows')
    if [x['flagged_rows'] for x in cells.values()]!=[284,352,308,450,506]:raise ValueError('source anomaly count')
    if [len(x['episodes']) for x in cells.values()]!=[10,9,9,9,9]:raise ValueError('source episode count')
    # Stable row-ID digest, can independently reproduce from old derived queue.
    row_digest=hashlib.sha256(json.dumps(sorted(hashes),separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    if row_digest!='9d6557fbae8e988d17031b6d82b997c92ed66e75ba6e339df3a53a491b32578b':raise ValueError('flagged source row identities differ from prior independent receipt')
    before=Counter();after=Counter()
    for c in cells.values():
        for e in c['episodes']:
            for k,ct in [('before_immediate',before),('after_immediate',after)]:
                r=e[k];ct['missing' if r is None else r['device']+'/'+r['numeric_state']]+=1
    return {'goal_key':'graz-20261124-original-com4-46-episode-boundary-state-audit','doi':source.DOI,
            'source_sha256':prior.EXPECTED_SHA256,'source_rows':prior.EXPECTED_ROWS,'flagged_rows':1900,'episodes':46,
            'flagged_row_identity_digest':row_digest,'before_immediate_counts':dict(before),'after_immediate_counts':dict(after),
            'cells':cells,'physical_controller_phase_verified':False,'current_power_si_units_verified':False,
            'root_cause_proven':False,'physical_production_release_allowed':False}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('out',type=Path);a=ap.parse_args()
    blob,size=source.get_original();d=inspect(blob,size)
    a.out.write_text(json.dumps(d,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')
    print('ORIGINAL_ROWS',d['source_rows'],'FLAGGED',d['flagged_rows'],'EPISODES',d['episodes'],'BEFORE',d['before_immediate_counts'],'AFTER',d['after_immediate_counts'])
if __name__=='__main__':main()
