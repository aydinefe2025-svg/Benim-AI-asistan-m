"""Source-authenticated Graz 2026 ten-cell EIS: falsifiable single-RC frequency holdout.

The *deliberately oversimplified* equivalent circuit:
    Z(f) = Rs + Rp/(1 + j*2*pi*f*tau)
with Rs>=0, Rp>=0, tau>0. This is a predictive software simulation,
not electrochemical mechanism identification, physical calibration or safety.

Each held-out frequency is predicted from a model trained on the
complementary parity indices. Adjacent frequency points are correlated:
this is NOT a new specimen-level independent experiment.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

from research.battery_curve_audit import graz_eis_2026_source_audit as source
from research.battery_curve_audit import graz_eis_2026_same_cell_delta as original
from research.battery_curve_audit import graz_eis_group_geometry_audit as geometry

LEVELS=original.LEVELS
GOAL='graz-20261123-50-original-eis-spectra-single-rc-blind-frequency-holdout-v1'
RECORD=18213931
GRID_COUNT=181

def _validated(spectrum):
    if not isinstance(spectrum,(tuple,list)) or len(spectrum)<8:
        raise ValueError('SOURCE_REVIEW_REQUIRED: insufficient independent source frequencies')
    vals=[]
    prev=None
    direction=None
    for p in spectrum:
        if not isinstance(p,(list,tuple)) or len(p)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) for x in p):
            raise ValueError('SOURCE_REVIEW_REQUIRED: invalid measured EIS triple')
        f,mag,phase=(float(x) for x in p)
        if f<=0 or mag<=0 or abs(phase)>360:
            raise ValueError('SOURCE_REVIEW_REQUIRED: zero/negative source frequency or invalid impedance')
        if prev is not None:
            step=f-prev
            if step==0 or (direction is not None and (step>0)!=direction):
                raise ValueError('SOURCE_REVIEW_REQUIRED: duplicated/non-monotonic source frequencies')
            direction=(step>0) if direction is None else direction
        prev=f
        z=complex(mag*math.cos(math.radians(phase)),mag*math.sin(math.radians(phase)))
        vals.append((f,z,phase))
    return vals

def model_z(f,rs,rp,tau):
    if any(not math.isfinite(p) or p<0 for p in (rs,rp,tau)) or f<=0 or tau==0:
        raise ValueError('SOURCE_REVIEW_REQUIRED: circuit parameters must be nonnegative with tau>0')
    return rs+rp/(1+1j*2*math.pi*f*tau)

def _coefficients(train,tau):
    n=len(train)
    a12=a22=b1=b2=0.0
    terms=[]
    for f,z,_ in train:
        k=1/(1+1j*2*math.pi*f*tau)
        kr=k.real
        a12+=kr
        a22+=k.real*k.real+k.imag*k.imag
        b1+=z.real
        b2+=z.real*kr+z.imag*k.imag
        terms.append((f,z,k))
    det=n*a22-a12*a12
    candidates=[(0.,0.),(max(0.,b1/n),0.),(0.,max(0.,b2/a22) if a22>0 else 0.)]
    if det>max(1e-20,1e-12*n*a22):
        rs=(b1*a22-b2*a12)/det
        rp=(n*b2-a12*b1)/det
        if rs>=0 and rp>=0:candidates.append((rs,rp))
    best=None
    for rs,rp in candidates:
        error=sum(abs(z-(rs+rp*k))**2 for _,z,k in terms)
        if best is None or error<best[0]:best=(error,rs,rp)
    return best

def _fit(train):
    freqs=[p[0] for p in train]
    min_hz=min(freqs);max_hz=max(freqs)
    min_tau=1/(2*math.pi*max_hz*100)
    max_tau=100/(2*math.pi*min_hz)
    low=math.log(min_tau);high=math.log(max_tau)
    grid=[]
    for i in range(GRID_COUNT):
        u=low+(high-low)*i/(GRID_COUNT-1)
        obj,rs,rp=_coefficients(train,math.exp(u))
        grid.append((obj,u,rs,rp))
    ix=min(range(len(grid)),key=lambda i:grid[i][0])
    # Local 1-D golden-section refinement of the best *training only* fit.
    a=grid[max(0,ix-1)][1];b=grid[min(GRID_COUNT-1,ix+1)][1]
    phi=(math.sqrt(5)-1)/2
    c=b-phi*(b-a);d=a+phi*(b-a)
    for _ in range(28):
        if _coefficients(train,math.exp(c))[0] < _coefficients(train,math.exp(d))[0]:
            b=d;d=c;c=b-phi*(b-a)
        else:
            a=c;c=d;d=a+phi*(b-a)
    tau=math.exp((a+b)/2)
    obj,rs,rp=_coefficients(train,tau)
    best=min(((obj,rs,rp,tau),(grid[ix][0],grid[ix][2],grid[ix][3],math.exp(grid[ix][1]))),key=lambda v:v[0])
    _,rs,rp,tau=best
    if any(not math.isfinite(x) for x in (rs,rp,tau)):
        raise ValueError('SOURCE_REVIEW_REQUIRED: numerical fit nonfinite')
    return rs,rp,tau

def cross_validate(spectrum):
    v=_validated(spectrum)
    folds=[]
    error_sum=norm_sum=0.
    abs_relative_errors=[]
    for parity in (0,1):
        train=[p for j,p in enumerate(v) if j%2==parity]
        holdout=[p for j,p in enumerate(v) if j%2!=parity]
        rs,rp,tau=_fit(train)
        err=sum(abs(model_z(f,rs,rp,tau)-z)**2 for f,z,_ in holdout)
        norm=sum(abs(z)**2 for _,z,_ in holdout)
        if norm<=0:raise ValueError('SOURCE_REVIEW_REQUIRED: zero EIS signal')
        error_sum+=err;norm_sum+=norm
        abs_relative_errors.extend(100*abs(model_z(f,rs,rp,tau)-z)/abs(z) for f,z,_ in holdout)
        folds.append({
            'fit_train_parity':parity,'training_frequencies':len(train),
            'heldout_frequencies':len(holdout),'Rs_ohm':rs,'Rp_ohm':rp,'tau_s':tau,
            'heldout_complex_relative_rmse_pct':100*math.sqrt(err/norm)
        })
    if sorted([len(v[1::2]),len(v[::2])])!=sorted([len(v)-len(v[::2]),len(v)-len(v[1::2])]):
        raise ValueError('SOURCE_REVIEW_REQUIRED: broken frequency partition')
    return {
        'observed_frequency_count':len(v),'fold_train_counts':[f['training_frequencies'] for f in folds],
        'fold_test_counts':[f['heldout_frequencies'] for f in folds],
        'heldout_relative_complex_rmse_pct':round(100*math.sqrt(error_sum/norm_sum),8),
        'heldout_median_point_relative_complex_error_pct':round(statistics.median(abs_relative_errors),8),
        'heldout_max_point_relative_complex_error_pct':round(max(abs_relative_errors),8),
        'positive_phase_frequency_count':sum(ph>0 for _,_,ph in v),
        'real_impedance_negative_frequency_count':sum(z.real<0 for _,z,_ in v),
        'folds':folds,
        'fitted_parameters_not_identifiable_physical_components':True,
        'absolute_parameter_identification_verified':False,
        'independent_calibration_verified':False,
        'production_release_allowed':False,
    }

def compare_source_stages(tables,filename):
    if set(tables)!=set(LEVELS):
        raise ValueError('SOURCE_REVIEW_REQUIRED: missing or extra deformation source level')
    reference=[v[0] for v in tables[LEVELS[0]]]
    if len(reference)!=101:raise ValueError('SOURCE_REVIEW_REQUIRED: publisher sheet frequency count differs')
    stages=[]
    for level in LEVELS:
        triplets=tables[level]
        if len(triplets)!=101 or [x[0] for x in triplets]!=reference:
            raise ValueError('SOURCE_REVIEW_REQUIRED: frequency grids differ within original workbook')
        r=cross_validate(triplets)
        stages.append({'source_deformation_level':level,**r})
    return {'source_filename':filename,'stages':stages}

def _download_originals():
    # Repeat full publisher byte authentication, never trust a copy that
    # merely matches a saved derived ledger.
    md=geometry.real_readme()
    if not md['original_publisher_readme_mapping_verified']:
        raise ValueError('SOURCE_REVIEW_REQUIRED: original README diameter mapping missing')
    diameter={}
    for group in md['publisher_documented_groups']:
        for identity in group['original_specimen_ids']:
            fn=f'EIS_{identity}.xlsx'
            if fn in diameter:raise ValueError('SOURCE_REVIEW_REQUIRED: source mapping duplicated')
            diameter[fn]=group['indenter_diameter_mm']
    if set(diameter)!=set(source.PINS):
        raise ValueError('SOURCE_REVIEW_REQUIRED: missing original diameter mapping')
    data=json.loads(source.fetch('https://zenodo.org/api/records/18213931',600000))
    if data.get('id')!=RECORD or data.get('doi')!=source.DOI:
        raise ValueError('SOURCE_REVIEW_REQUIRED: original metadata or DOI changed')
    indexed={f['key']:f for f in data.get('files',[]) if f.get('key') in source.PINS}
    if len(indexed)!=10:raise ValueError('SOURCE_REVIEW_REQUIRED: ten original workbooks not found')
    result=[]
    for filename,pin in source.PINS.items():
        meta=indexed[filename]
        url=meta.get('links',{}).get('self','')
        if meta.get('checksum')!='md5:'+pin or not isinstance(url,str) or not url.startswith('https://zenodo.org/'):
            raise ValueError('SOURCE_REVIEW_REQUIRED: original source pin invalid')
        original_bytes=source.fetch(url,source.MAX_FILE_BYTES)
        provenance=source.inspect_original_workbook(original_bytes,filename,pin)
        table=original.tables_from_original(original_bytes)
        item=compare_source_stages(table,filename)
        item.update({
            'source_sha256':provenance['source_sha256'],
            'publisher_original_md5_and_zip_crc_verified':True,
            'publisher_readme_indenter_diameter_mm':diameter[filename]
        })
        result.append(item)
    return sorted(result,key=lambda item:item['source_filename'])

def run():
    per_file=_download_originals()
    flatten=[]
    for x in per_file:
        for stage in x['stages']:
            flatten.append({
                'source_cell':x['source_filename'].replace('EIS_','').replace('.xlsx',''),
                'source_documented_impactor_mm':x['publisher_readme_indenter_diameter_mm'],
                'source_deformation_level':stage['source_deformation_level'],
                'source_sha256':x['source_sha256'],
                'heldout_relative_complex_rmse_pct':stage['heldout_relative_complex_rmse_pct'],
                'heldout_median_point_relative_complex_error_pct':stage['heldout_median_point_relative_complex_error_pct'],
                'heldout_max_point_relative_complex_error_pct':stage['heldout_max_point_relative_complex_error_pct'],
                'positive_phase_frequency_count':stage['positive_phase_frequency_count'],
                'real_impedance_negative_frequency_count':stage['real_impedance_negative_frequency_count'],
                'observed_frequency_count':stage['observed_frequency_count'],
                'fold_train_counts':stage['fold_train_counts'],
                'fold_test_counts':stage['fold_test_counts'],
                'per_fold_parameters':stage['folds'],
                'absolute_parameter_identification_verified':False,
                'independent_calibration_verified':False,
                'production_release_allowed':False,
            })
    groups={}
    for diameter in (30,180):
        observed=[r for r in flatten if r['source_documented_impactor_mm']==diameter]
        med=[]
        for stage in LEVELS:
            obs=[r['heldout_relative_complex_rmse_pct'] for r in observed if r['source_deformation_level']==stage]
            if len(obs)!=5:raise ValueError('SOURCE_REVIEW_REQUIRED: original specimen/stage missing')
            med.append({'stage':stage,'five_original_cells':5,'median_heldout_relative_complex_rmse_pct':round(statistics.median(obs),8),
                'individual_complex_rmse_below_5pct_count':sum(x<5.0 for x in obs)})
        groups[str(diameter)+'mm']={'spectra':len(observed),'stage_summary':med,
            'source_cell_level_validation_only':True}
    return {
        'goal_key':GOAL,'source_doi':source.DOI,'source_readme_md5_verified':True,
        'original_workbooks':len(per_file),'physical_source_specimens':len(per_file),
        'original_spectra':len(flatten),'original_frequency_phase_magnitude_triples':len(flatten)*101,
        'total_heldout_predictions_across_folds':sum(x['observed_frequency_count'] for x in flatten),
        'equivalent_circuit':'Rs+Rp/(1+j*2*pi*f*tau), Rs>=0 Rp>=0 tau>0',
        'frequency_holdout':'two parity folds, no heldout frequency used to fit its own model',
        'neighbor_frequency_correlation_prevents_specimen_independence_claim':True,
        'source_documented_geometry_summaries':groups,
        'publisher_documented_impactor_group_sizes':{'30mm':5,'180mm':5},
        'spectra':flatten,
        'independent_lab_calibration_verified':False,'physical_damage_causality_established':False,
        'capacity_Ah_or_post_impact_risk_measured':False,
        'one_rc_model_is_not_kk_validation':True,
        'one_rc_model_is_not_mechanistic_certification':True,
        'production_release_allowed':False,
        'decision':'ORIGINAL_EIS_FREQUENCY_HOLDOUT_SIMPLE_RC_FALSIFIABILITY_ONLY'
    }

def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=2:return 2
    target=Path(args[0]);csv_target=Path(args[1])
    try:
        if target.exists() or csv_target.exists() or not target.parent.is_dir() or not csv_target.parent.is_dir():
            raise ValueError('SOURCE_REVIEW_REQUIRED: evidence file already exists or invalid parent')
        data=run()
        with target.open('x',encoding='utf-8') as dest:
            json.dump(data,dest,indent=2,sort_keys=True);dest.write('\n')
        fields=['source_cell','source_documented_impactor_mm','source_deformation_level',
                'heldout_relative_complex_rmse_pct','heldout_median_point_relative_complex_error_pct',
                'heldout_max_point_relative_complex_error_pct','positive_phase_frequency_count',
                'real_impedance_negative_frequency_count','source_sha256']
        with csv_target.open('x',newline='',encoding='utf-8') as dest:
            writer=csv.DictWriter(dest,fieldnames=fields,extrasaction='ignore')
            writer.writeheader();writer.writerows(data['spectra'])
        print('REAL_GRAZ_10CELL_50EIS_ODD_EVEN_FREQUENCY_HOLDOUT',data['original_spectra'],data['total_heldout_predictions_across_folds'])
        for diam,g in data['source_documented_geometry_summaries'].items():
            print('SOURCE_GEOMETRY_DIAGNOSTIC',diam,g['stage_summary'])
        return 0
    except (ValueError,KeyError,TypeError,OSError,IndexError,OverflowError,ZeroDivisionError) as e:
        print('SOURCE_REVIEW_REQUIRED',str(e)[:250],file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
