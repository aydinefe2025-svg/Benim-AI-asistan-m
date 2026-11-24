"""Source-pinned numerical V*I reconstruction, not measured power or calibrated energy."""
from __future__ import annotations
import argparse, hashlib, io, json, math, statistics, zipfile
from pathlib import Path
from research.battery_curve_audit import graz_source_preflight as source
from research.battery_curve_audit import graz_current_power_audit as prior
from research.battery_curve_audit import graz_com4_transition_audit as boundary

DIGEST='9d6557fbae8e988d17031b6d82b997c92ed66e75ba6e339df3a53a491b32578b'

def flagged(r):
    return r.device=='COM4' and r.p==0 and abs(r.v*r.i)>=1

def estimate(r):
    if not all(math.isfinite(x) for x in (r.v,r.i,r.p,r.t)) or not flagged(r):
        raise ValueError('not a finite flagged COM4 row')
    return {'logged_power_numeric':r.p,'derived_vi_numeric':r.v*r.i,
            'independent_power_measurement':False,'si_units_verified':False}

def integrate(rows):
    sec=[];energy=[];gaps=0;intervals=0
    for a,b in zip(rows,rows[1:]):
        if not(flagged(a) and flagged(b)):continue
        dt=b.t-a.t
        if not (0<dt<=2.5) or b.line!=a.line+1:
            gaps+=1;continue
        sec.append(dt);energy.append(dt*(estimate(a)['derived_vi_numeric']+estimate(b)['derived_vi_numeric'])/7200)
        intervals+=1
    return {'covered_seconds':math.fsum(sec),'derived_vi_hour_numeric':math.fsum(energy),
            'logged_power_hour_numeric':0.,'integrated_intervals':intervals,'excluded_long_gap_count':gaps,
            'physical_energy_Wh_verified':False}

def validate_comparators(rows):
    # Fixed rectangular region before observing results. Do NOT filter by residual.
    es=[];ab=[]
    for r in rows:
        if r.device=='COM4' and 4.30<=r.v<=4.40 and 3.5<=r.i<=5 and r.p!=0:
            vi=r.v*r.i;es.append(abs(r.p-vi)/abs(vi));ab.append(abs(r.p-vi))
    es.sort();n=len(es)
    return {'n':n,'within_5pct':sum(x<=.05 for x in es),
            'median_abs_relative_error':statistics.median(es) if n else None,
            'p95_abs_relative_error':es[math.ceil(.95*n)-1] if n else None,
            'max_abs_relative_error':max(es) if n else None,
            'mean_absolute_numeric_residual':math.fsum(ab)/n if n else None,
            'comparison_is_logged_field_not_independent_ground_truth':True}

def inspect(blob,size):
    cert=source.inspect_archive(blob,size)
    if cert['original_zip_sha256']!=prior.EXPECTED_SHA256:raise ValueError('source sha')
    cells={};ids=[];out=[];all_comparators=[]
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for cell in prior.CELLS:
            logs=[m for m in z.infolist() if not m.is_dir() and source.explicit_cell_in_path(m.filename)==cell and source.role_for_member(m.filename)=='charge_discharge_log_candidate']
            if len(logs)!=1:raise ValueError('log count')
            m=logs[0];rows,hashes=boundary.parse_member(z,m);ids.extend(hashes)
            h_by_line={n:h for path,n,h in hashes}
            flags=[r for r in rows if flagged(r)]
            if set(h_by_line)!={r.line for r in flags}:raise ValueError('identity mismatch')
            for r in flags:
                out.append({'cell':cell,'member':m.filename,'line':r.line,'raw_row_sha256':h_by_line[r.line],**estimate(r)})
            all_comparators.extend(r for r in rows if r.device=='COM4' and 4.30<=r.v<=4.40 and 3.5<=r.i<=5 and r.p!=0)
            cells[cell]={'source_rows':len(rows),'flagged_rows':len(flags),'comparator':validate_comparators(rows),
                         'integration':integrate(rows),'min_vi':min(r.v*r.i for r in flags),'max_vi':max(r.v*r.i for r in flags)}
    if sum(x['source_rows'] for x in cells.values())!=prior.EXPECTED_ROWS or [x['flagged_rows'] for x in cells.values()]!=[284,352,308,450,506]:raise ValueError('source counts')
    digest=hashlib.sha256(json.dumps(sorted(ids),separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    if digest!=DIGEST:raise ValueError('prior 1900 identity digest mismatch')
    return {'goal_key':'graz-20261124-numeric-power-reconstruction-1900-v1','source_doi':source.DOI,'original_sha256':prior.EXPECTED_SHA256,'flagged_identity_sha256':digest,
            'cells':cells,'comparator_all':validate_comparators(all_comparators),'rows':out,
            'covered_seconds':math.fsum(c['integration']['covered_seconds'] for c in cells.values()),
            'derived_vi_hour_numeric':math.fsum(c['integration']['derived_vi_hour_numeric'] for c in cells.values()),
            'logged_power_hour_numeric':0.,'source_changed':False,'actual_power_recovered':False,
            'physical_energy_Wh_verified':False,'phase_verified':False,'physical_production_release_allowed':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args()
    b,n=source.get_original();d=inspect(b,n);a.output.write_text(json.dumps(d,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')
    print('SOURCE',d['original_sha256'],'RECONSTRUCTED_NUMERIC_ONLY',len(d['rows']),'COVERED_SECONDS',d['covered_seconds'],'PRODUCT_HOURS',d['derived_vi_hour_numeric'],'CONTROL',d['comparator_all'])
if __name__=='__main__':main()
