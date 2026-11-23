"""Falsifiable constrained one/two-R-CPE+L equivalent circuits on Graz-original EIS.

Publisher Drießen et al, Batteries 12(2):54 (2026) describes R0, L0,
R1||CPE1 and R2||CPE2. We model their two parallel R-CPE branches in
series with R0 and L0, with bounds and per-frequency *train-only* fitting.

Original measured EIS does not prove cause, actual component identities,
physical capacity or battery safety. Nearby frequency points remain
correlated and held-out prediction is not an independent specimen replication.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

GOAL = 'graz-20261123-paper-two-cpe-source-50-101-frequency-holdout-v1'
DOI = '10.5281/zenodo.18213931'
LEVELS = ('0% deformation', '25% deformation', '50% deformation',
          '75% deformation', '95% deformation')
THRESHOLD_PCT = 5.0


def validate_spectrum(spectrum):
    """Return source frequencies and measured complex Z without interpolation."""
    import numpy as np
    if not isinstance(spectrum, (tuple, list)) or len(spectrum) < 12:
        raise ValueError('SOURCE_REVIEW_REQUIRED: insufficient original points')
    entries=[]
    last=None
    sign=None
    for row in spectrum:
        if not isinstance(row, (tuple, list)) or len(row) != 3:
            raise ValueError('SOURCE_REVIEW_REQUIRED: malformed EIS triple')
        if any(type(x) not in (float,int) or not math.isfinite(x) for x in row):
            raise ValueError('SOURCE_REVIEW_REQUIRED: nonfinite EIS source')
        f, magnitude, angle = (float(x) for x in row)
        if f <= 0 or magnitude <= 0 or abs(angle)>360:
            raise ValueError('SOURCE_REVIEW_REQUIRED: physically invalid source')
        if last is not None:
            direction=1 if f>last else -1 if f<last else 0
            if not direction or sign is not None and direction!=sign:
                raise ValueError('SOURCE_REVIEW_REQUIRED: duplicated/nonmonotonic frequency')
            if sign is None: sign=direction
        last=f
        entries.append((f, magnitude*complex(math.cos(math.radians(angle)),
                                             math.sin(math.radians(angle)))))
    if len({f for f,_ in entries})!=len(entries):
        raise ValueError('SOURCE_REVIEW_REQUIRED: duplicated source frequency')
    return entries


def _model_numpy(freq, x, two, f_ref):
    """Normalized Z with nonnegative effective L coefficient at fmax."""
    import numpy as np
    omega=2j*np.pi*freq
    fmax=f_ref
    if two:
        rs,rp1,rp2,lh,logt1,logt2,a1,a2=x
        return (rs + 1j*lh*freq/fmax +
                rp1/(1+(omega*np.exp(logt1))**a1)+
                rp2/(1+(omega*np.exp(logt2))**a2))
    rs,rp,lh,logt,a=x
    return rs+1j*lh*freq/fmax+rp/(1+(omega*np.exp(logt))**a)


def _fit(train, model):
    import numpy as np
    from scipy.optimize import least_squares
    two=model=='two_cpe'
    f=np.array([p[0] for p in train],float)
    observed=np.array([p[1] for p in train],complex)
    scale=float(np.median(np.abs(observed)))
    if not math.isfinite(scale) or scale<=0:
        raise ValueError('SOURCE_REVIEW_REQUIRED: invalid EIS scale')
    y=observed/scale
    smallest,largest=float(np.min(f)),float(np.max(f))
    min_tau=1/(2*math.pi*largest*100)
    max_tau=100/(2*math.pi*smallest)
    lo=math.log(min_tau);hi=math.log(max_tau)
    r0=max(1e-4,min(float(np.min(y.real)),1))
    rtotal=max(0.1,float(np.max(y.real)-r0))
    lh=max(0.01,float(y[int(np.argmax(f))].imag))
    def ln_tau(position):
        characteristic=smallest**(1-position)*largest**position
        return math.log(1/(2*math.pi*characteristic))
    if two:
        lower=[0,0,0,0,lo,lo,0.25,0.25]
        upper=[100000,100000,100000,100000,hi,hi,1,1]
        seeds=[
            [r0,rtotal/2,rtotal/2,lh,ln_tau(p1),ln_tau(p2),a1,a2]
            for p1,p2,a1,a2 in [(.72,.25,.85,.65),(.60,.15,.75,.9),(.85,.4,1.,.6)]
        ]
    else:
        lower=[0,0,0,lo,0.25]
        upper=[100000,100000,100000,hi,1]
        seeds=[[r0,rtotal,lh,ln_tau(pos),alpha] for pos,alpha in
               [(.35,.75),(.65,.9),(.18,.6)]]
    def residual(x):
        estimated=_model_numpy(f,x,two,largest)
        difference=estimated-y
        return np.concatenate((difference.real,difference.imag))
    best=None
    for seed in seeds:
        start=np.maximum(np.array(lower,float)+1e-11,
                         np.minimum(np.array(seed,float),np.array(upper,float)-1e-11))
        fit=least_squares(residual,start,bounds=(lower,upper),
                          max_nfev=260,x_scale='jac',ftol=5e-10,xtol=5e-10,gtol=5e-10)
        score=float(np.sum(fit.fun**2))
        if not math.isfinite(score):continue
        if best is None or score<best[0]:best=(score,fit.x,scale)
    if best is None:raise ValueError('SOURCE_REVIEW_REQUIRED: bounded optimizer did not converge')
    return best[1],best[2],largest


def _score(train,heldout,model):
    import numpy as np
    params,scale,f_ref=_fit(train,model)
    freq=np.array([p[0] for p in heldout],float)
    measured=np.array([p[1] for p in heldout],complex)
    estimated=scale*_model_numpy(freq,params,model=='two_cpe',f_ref)
    residual=estimated-measured
    err=float(np.sum(np.abs(residual)**2))
    norm=float(np.sum(np.abs(measured)**2))
    if norm<=0:raise ValueError('SOURCE_REVIEW_REQUIRED: degenerate heldout impedance')
    relative_errors=100*np.abs(residual)/np.abs(measured)
    p=[float(x) for x in params]
    # Numerical parameters in normalized ohm and effective L; not physical identities.
    return {
        'squared_error':err,'squared_reference_norm':norm,
        'median_point_relative_error_pct':float(np.median(relative_errors)),
        'model_parameters_normalized':p,
        'bounded_parameter_constraints_passed':bool(all(x>=0 for x in p[:4 if model=='two_cpe' else 3])),
    }


def _aggregate(folds,measured_len,model):
    numerator=sum(f['squared_error'] for f in folds)
    denominator=sum(f['squared_reference_norm'] for f in folds)
    value=100*math.sqrt(numerator/denominator)
    return {
        'model':model,
        'heldout_relative_complex_rmse_pct':round(value,8),
        'heldout_median_fold_median_point_pct':round(statistics.median(f['median_point_relative_error_pct'] for f in folds),8),
        'folds':folds,
        'unique_heldout_frequency_count':sum(f['test_count'] for f in folds),
        'disjoint_train_test_indices_verified':True,
        'mechanistic_identifiability_proven':False,
        'production_release_allowed':False,
        'capacity_loss_Ah_measured':False,
    }


def cross_validate(spectrum,model='two_cpe'):
    if model not in ('one_cpe','two_cpe'):
        raise ValueError('SOURCE_REVIEW_REQUIRED: unsupported EIS model')
    points=validate_spectrum(spectrum)
    folds=[]
    for parity in (0,1):
        train_idx=[i for i in range(len(points)) if i%2==parity]
        test_idx=[i for i in range(len(points)) if i%2!=parity]
        if set(train_idx)&set(test_idx) or len(train_idx)+len(test_idx)!=len(points):
            raise ValueError('SOURCE_REVIEW_REQUIRED: training/test frequency overlap')
        score=_score([points[i] for i in train_idx],[points[i] for i in test_idx],model)
        folds.append({
            'fold':parity,'train_count':len(train_idx),'test_count':len(test_idx),
            'constraints_passed':score.pop('bounded_parameter_constraints_passed'),
            **score,
        })
    return _aggregate(folds,len(points),model)


def contiguous_block_holdout(spectrum,model='two_cpe'):
    if model not in ('one_cpe','two_cpe'):
        raise ValueError('SOURCE_REVIEW_REQUIRED: unsupported EIS model')
    points=validate_spectrum(spectrum)
    # Mid-spectrum log-frequency *band* unobserved in training.
    n=len(points)
    testing=list(range(n//3,(2*n)//3))
    training=[i for i in range(n) if i not in set(testing)]
    if set(training)&set(testing):raise ValueError('SOURCE_REVIEW_REQUIRED: blocked spectral leakage')
    score=_score([points[i] for i in training],[points[i] for i in testing],model)
    result={
        'train_count':len(training),'test_count':len(testing),
        'heldout_relative_complex_rmse_pct':round(100*math.sqrt(score['squared_error']/score['squared_reference_norm']),8),
        'heldout_middle_frequency_band_no_training_examples':True,
        'disjoint_train_test_indices_verified':True,
        'production_release_allowed':False,
    }
    return result


def _source_originals():
    from research.battery_curve_audit import graz_eis_2026_source_audit as source
    from research.battery_curve_audit import graz_eis_2026_same_cell_delta as original
    from research.battery_curve_audit import graz_eis_group_geometry_audit as geometry
    readme=geometry.real_readme()
    if not readme.get('original_publisher_readme_mapping_verified'):
        raise ValueError('SOURCE_REVIEW_REQUIRED: original publisher geometry provenance missing')
    group={}
    for q in readme['publisher_documented_groups']:
        for id in q['original_specimen_ids']:
            fn='EIS_'+id+'.xlsx'
            if fn in group:raise ValueError('SOURCE_REVIEW_REQUIRED: duplicate specimen identity')
            group[fn]=q['indenter_diameter_mm']
    if set(group)!=set(source.PINS):raise ValueError('SOURCE_REVIEW_REQUIRED: incomplete publisher geometry mapping')
    meta=json.loads(source.fetch('https://zenodo.org/api/records/18213931',600000))
    if meta.get('id')!=18213931 or meta.get('doi')!=source.DOI:
        raise ValueError('SOURCE_REVIEW_REQUIRED: publisher DOI mismatch')
    entries={x['key']:x for x in meta.get('files',[]) if x.get('key') in source.PINS}
    if set(entries)!=set(source.PINS):raise ValueError('SOURCE_REVIEW_REQUIRED: original workbook inventory mismatch')
    result=[]
    for name,pin in source.PINS.items():
        e=entries[name]
        url=e.get('links',{}).get('self','')
        if e.get('checksum')!='md5:'+pin or not url.startswith('https://zenodo.org/'):
            raise ValueError('SOURCE_REVIEW_REQUIRED: publisher original MD5 or URL changed')
        raw=source.fetch(url,source.MAX_FILE_BYTES)
        p=source.inspect_original_workbook(raw,name,pin)
        sheets=original.tables_from_original(raw)
        if set(sheets)!=set(LEVELS):raise ValueError('SOURCE_REVIEW_REQUIRED: 5 stage provenance mismatch')
        original_frequency_grid=[x[0] for x in sheets[LEVELS[0]]]
        result.append({
            'name':name,'diameter_mm':group[name],'original_sha256':p['source_sha256'],
            'publisher_md5_crc_verified':True,'tables':sheets,
            'exact_stage_frequency_grids_identical':all([x[0] for x in sheets[lev]]==original_frequency_grid for lev in LEVELS),
        })
    return result


def run():
    from research.battery_curve_audit import graz_eis_rlc_frequency_holdout as previous
    sources=_source_originals()
    records=[]
    for cell in sources:
        if not cell['exact_stage_frequency_grids_identical']:
            raise ValueError('SOURCE_REVIEW_REQUIRED: original stage frequency mismatch')
        for stage in LEVELS:
            sp=cell['tables'][stage]
            one=previous.cross_validate_rlc(sp)
            one_cpe=cross_validate(sp,'one_cpe')
            two_cpe=cross_validate(sp,'two_cpe')
            block=contiguous_block_holdout(sp,'two_cpe')
            if one_cpe['unique_heldout_frequency_count']!=len(sp) or two_cpe['unique_heldout_frequency_count']!=len(sp):
                raise ValueError('SOURCE_REVIEW_REQUIRED: original frequency holdout leakage')
            records.append({
                'original_physical_specimen':cell['name'].replace('EIS_','').replace('.xlsx',''),
                'source_documented_impactor_mm':cell['diameter_mm'],
                'deformation_stage':stage,
                'publisher_original_xlsx_sha256':cell['original_sha256'],
                'original_frequency_triplets':len(sp),
                'source_phase_positive_frequency_count':sum(phi>0 for f,mag,phi in sp),
                'base_rc_plus_l_heldout_complex_rmse_pct':one['heldout_relative_complex_rmse_pct'],
                'one_cpe_plus_l_heldout_complex_rmse_pct':one_cpe['heldout_relative_complex_rmse_pct'],
                'two_cpe_plus_l_heldout_complex_rmse_pct':two_cpe['heldout_relative_complex_rmse_pct'],
                'two_cpe_plus_l_heldout_middle_third_rmse_pct':block['heldout_relative_complex_rmse_pct'],
                'two_cpe_below_5pct_odd_even':two_cpe['heldout_relative_complex_rmse_pct']<THRESHOLD_PCT,
                'two_cpe_below_5pct_middle_third':block['heldout_relative_complex_rmse_pct']<THRESHOLD_PCT,
                'fold_a_train_count':two_cpe['folds'][0]['train_count'],
                'fold_a_test_count':two_cpe['folds'][0]['test_count'],
                'fold_b_train_count':two_cpe['folds'][1]['train_count'],
                'fold_b_test_count':two_cpe['folds'][1]['test_count'],
                'two_cpe_source_fit_constraints_passed':all(x['constraints_passed'] for x in two_cpe['folds']),
                'mechanistic_identifiability_proven':False,
                'production_release_allowed':False,
            })
    metrics=['base_rc_plus_l_heldout_complex_rmse_pct','one_cpe_plus_l_heldout_complex_rmse_pct',
             'two_cpe_plus_l_heldout_complex_rmse_pct','two_cpe_plus_l_heldout_middle_third_rmse_pct']
    group_summaries=[]
    for diameter in (30,180):
        for stage in LEVELS:
            subset=[q for q in records if q['source_documented_impactor_mm']==diameter and q['deformation_stage']==stage]
            if len(subset)!=5:raise ValueError('SOURCE_REVIEW_REQUIRED: insufficient source specimen group')
            group_summaries.append({'source_documented_impactor_mm':diameter,'stage':stage,
                'source_cells':5,**{'median_'+m:round(statistics.median(x[m] for x in subset),8) for m in metrics},
                'two_cpe_pass_5pct_count':sum(x['two_cpe_below_5pct_odd_even'] for x in subset),
                'two_cpe_middle_band_pass_5pct_count':sum(x['two_cpe_below_5pct_middle_third'] for x in subset)})
    summary={'original_source_doi':DOI,'goal_key':GOAL,'original_xlsx_count':len(sources),
             'original_source_spectra':len(records),'source_frequency_triples':sum(r['original_frequency_triplets'] for r in records),
             'blind_odd_even_total_predictions':sum(r['original_frequency_triplets'] for r in records),
             'source_documented_indenter_groups':{'30mm':5,'180mm':5},
             'model_interpretation':'published L0-R0-(R1||CPE1)-(R2||CPE2) two relaxation branches, parameters effective only',
             'original_publisher_md5_and_crc_verified':all(x['publisher_md5_crc_verified'] for x in sources),
             'frequency_holdout_no_same_point_training':True,'contiguous_middle_band_generalization_tested':True,
             'five_percent_acceptance_criterion_fixed_before_run':True,
             'ten_group_stage_summaries':group_summaries,
             'fifty_physical_source_stage_records':records,
             'global_spectral_medians':{m:round(statistics.median(r[m] for r in records),8) for m in metrics},
             'two_cpe_odd_even_pass_5pct_count':sum(r['two_cpe_below_5pct_odd_even'] for r in records),
             'two_cpe_middle_band_pass_5pct_count':sum(r['two_cpe_below_5pct_middle_third'] for r in records),
             'independent_physical_cell_holdout_not_performed':True,
             'independent_calibration_verified':False,
             'capacity_Ah_measured':False,'causal_damage_mechanism_established':False,
             'field_safety_certified':False,'production_release_allowed':False}
    return summary


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=2:return 2
    dest=Path(args[0]);csv_out=Path(args[1])
    try:
        if dest.exists() or csv_out.exists() or not dest.parent.exists() or not csv_out.parent.exists():
            raise ValueError('SOURCE_REVIEW_REQUIRED: output already exists or parent missing')
        result=run()
        dest.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+'\n',encoding='utf-8')
        fields=['original_physical_specimen','source_documented_impactor_mm','deformation_stage','publisher_original_xlsx_sha256',
                'source_phase_positive_frequency_count','base_rc_plus_l_heldout_complex_rmse_pct',
                'one_cpe_plus_l_heldout_complex_rmse_pct','two_cpe_plus_l_heldout_complex_rmse_pct',
                'two_cpe_plus_l_heldout_middle_third_rmse_pct','two_cpe_below_5pct_odd_even','two_cpe_below_5pct_middle_third']
        with csv_out.open('x',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(result['fifty_physical_source_stage_records'])
        print('ORIGINAL_REAL_GRAZ_EIS_TWO_CPE',result['original_source_spectra'],result['source_frequency_triples'],result['global_spectral_medians'])
        print('PREDEFINED_5PCT_GATE',result['two_cpe_odd_even_pass_5pct_count'],result['two_cpe_middle_band_pass_5pct_count'])
        for e in result['ten_group_stage_summaries']:
            if e['stage']=='95% deformation':print('REAL_GEOMETRY_95',e)
        return 0
    except (ValueError,TypeError,KeyError,OSError,ZeroDivisionError,OverflowError) as e:
        print('SOURCE_REVIEW_REQUIRED:',str(e)[:250],file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())