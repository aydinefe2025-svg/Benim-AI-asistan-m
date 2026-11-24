"""Source-pinned Graz EIS: nonnegative RC relaxation distribution + effective inductance.

This is a finite linear passive equivalent-circuit *diagnostic*, not a
Kramers-Kronig measurement certification or an electrochemical state-of-health
measurement. The fixed relaxation-grid & penalty are determined before reading
source responses; held-out frequencies never enter their model's fit.
"""
from __future__ import annotations
import csv, json, math, statistics, sys
from pathlib import Path

GOAL='graz-20261123-50-original-eis-passive-positive-relaxation-blind-frequency-v1'
REGULARIZATION=0.0003
N_RELAXATIONS=24
FRACTION_BLOCK_START=1/3
FRACTION_BLOCK_END=2/3
PHYSICAL_ERROR_THRESHOLD_PCT=5.0


def validate_source(spectrum):
    if not isinstance(spectrum,(list,tuple)) or len(spectrum)<12:
        raise ValueError('SOURCE_REVIEW_REQUIRED: insufficient measured source points')
    arr=[];direction=None;last=None
    for row in spectrum:
        if not isinstance(row,(tuple,list)) or len(row)!=3 or any(type(x) not in (float,int) or not math.isfinite(x) for x in row):
            raise ValueError('SOURCE_REVIEW_REQUIRED: invalid source frequency / amplitude / phase')
        f,mag,phase=(float(x) for x in row)
        if f<=0 or mag<=0 or abs(phase)>360:
            raise ValueError('SOURCE_REVIEW_REQUIRED: invalid finite measured physics')
        if last is not None:
            sign=1 if f>last else -1 if f<last else 0
            if sign==0 or direction is not None and sign!=direction:
                raise ValueError('SOURCE_REVIEW_REQUIRED: repeated or nonmonotonic frequency')
            direction=sign
        last=f
        arr.append((f,mag*complex(math.cos(math.radians(phase)),math.sin(math.radians(phase)))))
    return arr


def _basis(freq,tau_grid,fref):
    import numpy as np
    rows=[]
    for f in freq:
        t=[1+0j,1j*f/fref]
        for tau in tau_grid:
            t.append(1/(1+1j*2*math.pi*f*tau))
        rows.append(t)
    return np.asarray(rows,complex)


def _fit(train,weighting):
    import numpy as np
    from scipy.optimize import nnls
    if weighting not in ('relative','absolute'):
        raise ValueError('SOURCE_REVIEW_REQUIRED: unknown source fitting weight')
    freq=np.asarray([x[0] for x in train],float)
    z=np.asarray([x[1] for x in train],complex)
    scale=float(np.median(np.abs(z)))
    if not math.isfinite(scale) or scale<=0:raise ValueError('SOURCE_REVIEW_REQUIRED: invalid impedance scale')
    y=z/scale
    fmin=float(min(freq));fmax=float(max(freq))
    tmin=1/(2*math.pi*fmax*30)
    tmax=30/(2*math.pi*fmin)
    tau=np.geomspace(tmin,tmax,N_RELAXATIONS)
    a=_basis(freq,tau,fmax)
    weights=(1/np.abs(y)) if weighting=='relative' else np.ones_like(freq)
    a=a*weights[:,None]
    b=y*weights
    A=np.concatenate((a.real,a.imag),axis=0)
    B=np.concatenate((b.real,b.imag),axis=0)
    # Smooth the *real RC relaxation* distribution. No penalty for Ohmic R/L,
    # avoiding arbitrary bias on independently observable endpoints.
    d=np.zeros((N_RELAXATIONS-2,N_RELAXATIONS+2),float)
    for j in range(N_RELAXATIONS-2):
        d[j,j+2:j+5]=[1,-2,1]
    A=np.concatenate((A,math.sqrt(REGULARIZATION)*d),axis=0)
    B=np.concatenate((B,np.zeros(N_RELAXATIONS-2)),axis=0)
    x,res=nnls(A,B,maxiter=3000)
    if len(x)!=N_RELAXATIONS+2 or any(not math.isfinite(float(v)) or v<0 for v in x):
        raise ValueError('SOURCE_REVIEW_REQUIRED: invalid nonnegative RC relaxation fit')
    return x,tau,scale,fmax


def _heldout(train,test,weighting):
    import numpy as np
    x,tau,scale,fref=_fit(train,weighting)
    f=np.asarray([v[0] for v in test],float)
    obs=np.asarray([v[1] for v in test],complex)
    predicted=scale*_basis(f,tau,fref).dot(x)
    residual=predicted-obs
    error=np.abs(residual)
    energy=float(np.sum(error**2));ref=float(np.sum(np.abs(obs)**2))
    pct=100*error/np.abs(obs)
    if not ref>0:raise ValueError('SOURCE_REVIEW_REQUIRED: no physical heldout impedance')
    return {'squared_error':energy,'squared_reference_norm':ref,'test_count':len(test),
            'median_point_relative_error_pct':round(float(np.median(pct)),8),
            'max_point_relative_error_pct':round(float(max(pct)),8),
            'all_nonnegative_relaxation_coefficients':bool(np.all(x>=-1e-12)),
            'nonzero_relaxation_coefficients':int(np.count_nonzero(x[2:]>1e-8)),
            'relaxation_grid_count':len(tau),
            'fitted_normalized_ohmic_R':round(float(x[0]),9),
            'fitted_normalized_effective_inductance_at_train_fmax':round(float(x[1]),9),
            'unmeasured_frequency_bands_not_a_new_physical_sample':True}


def cross_validate(spectrum,weighting='absolute'):
    pts=validate_source(spectrum)
    if weighting not in ('absolute','relative'):raise ValueError('SOURCE_REVIEW_REQUIRED: invalid model weight')
    folds=[]
    for parity in (0,1):
        train_idx=[i for i in range(len(pts)) if i%2==parity]
        test_idx=[i for i in range(len(pts)) if i%2!=parity]
        if len(set(train_idx)&set(test_idx)) or len(test_idx)==0:
            raise ValueError('SOURCE_REVIEW_REQUIRED: parity train/test overlap')
        metrics=_heldout([pts[i] for i in train_idx],[pts[i] for i in test_idx],weighting)
        folds.append({'train_count':len(train_idx),**metrics})
    return {'weighting':weighting,'total_frequency_predictions':sum(x['test_count'] for x in folds),
            'heldout_complex_rmse_pct':round(100*math.sqrt(sum(x['squared_error'] for x in folds)/sum(x['squared_reference_norm'] for x in folds)),8),
            'fold_median_point_pct':round(statistics.median(x['median_point_relative_error_pct'] for x in folds),8),
            'all_nonnegative_relaxation_coefficients':all(x['all_nonnegative_relaxation_coefficients'] for x in folds),
            'no_train_test_frequency_overlap':True,
            'kramers_kronig_consistency_proven':False,
            'independent_instrument_calibration_verified':False,
            'production_release_allowed':False,
            'folds':folds}


def block_holdout(spectrum,weighting='relative'):
    pts=validate_source(spectrum)
    n=len(pts)
    test_idx=list(range(n//3,2*n//3))
    test_set=set(test_idx)
    train_idx=[i for i in range(n) if i not in test_set]
    if set(train_idx)&test_set:raise ValueError('SOURCE_REVIEW_REQUIRED: blocked leakage')
    metrics=_heldout([pts[i] for i in train_idx],[pts[i] for i in test_idx],weighting)
    return {'heldout_complex_rmse_pct':round(100*math.sqrt(metrics['squared_error']/metrics['squared_reference_norm']),8),
            'heldout_median_point_pct':metrics['median_point_relative_error_pct'],
            'train_count':len(train_idx),'test_count':len(test_idx),
            'no_train_test_frequency_overlap':True,
            'all_nonnegative_relaxation_coefficients':metrics['all_nonnegative_relaxation_coefficients'],
            'production_release_allowed':False}


def run():
    from research.battery_curve_audit.graz_eis_two_cpe_holdout import _source_originals,LEVELS
    sources=_source_originals()
    out=[]
    for src in sources:
        if not src['exact_stage_frequency_grids_identical']:
            raise ValueError('SOURCE_REVIEW_REQUIRED: publisher original five sheet frequency mismatch')
        for level in LEVELS:
            rows=src['tables'][level]
            absolute=cross_validate(rows,'absolute')
            relative=cross_validate(rows,'relative')
            block=block_holdout(rows,'relative')
            if absolute['total_frequency_predictions']!=101 or relative['total_frequency_predictions']!=101:
                raise ValueError('SOURCE_REVIEW_REQUIRED: incomplete original source frequency holdout')
            out.append({'original_specimen_id':src['name'].replace('EIS_','').replace('.xlsx',''),
                        'source_diameter_mm':src['diameter_mm'],
                        'original_workbook_sha256':src['original_sha256'],
                        'source_deformation_level':level,
                        'original_frequency_points':101,
                        'passive_relaxation_absolute_odd_even_rmse_pct':absolute['heldout_complex_rmse_pct'],
                        'passive_relaxation_relative_odd_even_rmse_pct':relative['heldout_complex_rmse_pct'],
                        'passive_relaxation_relative_middle_band_rmse_pct':block['heldout_complex_rmse_pct'],
                        'passive_relaxation_relative_odd_even_median_point_pct':relative['fold_median_point_pct'],
                        'passive_relaxation_relative_middle_band_median_point_pct':block['heldout_median_point_pct'],
                        'passes_predeclared_5pct_absolute_odd_even':absolute['heldout_complex_rmse_pct']<PHYSICAL_ERROR_THRESHOLD_PCT,
                        'passes_predeclared_5pct_relative_odd_even':relative['heldout_complex_rmse_pct']<PHYSICAL_ERROR_THRESHOLD_PCT,
                        'passes_predeclared_5pct_relative_blocked':block['heldout_complex_rmse_pct']<PHYSICAL_ERROR_THRESHOLD_PCT,
                        'positive_relaxation_coefficients':absolute['all_nonnegative_relaxation_coefficients'] and relative['all_nonnegative_relaxation_coefficients'] and block['all_nonnegative_relaxation_coefficients'],
                        'source_original_measurement_not_simulation':True,
                        'physical_release_allowed':False})
    metrics=['passive_relaxation_absolute_odd_even_rmse_pct',
             'passive_relaxation_relative_odd_even_rmse_pct',
             'passive_relaxation_relative_middle_band_rmse_pct',
             'passive_relaxation_relative_odd_even_median_point_pct',
             'passive_relaxation_relative_middle_band_median_point_pct']
    return {'goal_key':GOAL,'publisher_source_doi':'10.5281/zenodo.18213931','original_workbooks':len(sources),
            'original_spectra':len(out),'original_source_triplets':101*len(out),
            'odd_even_blind_prediction_count_each_objective':101*len(out),
            'relaxation_kernel_count':N_RELAXATIONS,'fixed_smoothness_regularization':REGULARIZATION,
            'source_models':'Rs+jωL+sum_positive_Ri/(1+jωtau_i); fixed source-frequency grid',
            'relative_fitting_is_posthoc_exploratory_sensitivity':True,
            'source_md5_crc_verified':all(x['publisher_md5_crc_verified'] for x in sources),
            'all_nonnegative_model_coefficients':all(x['positive_relaxation_coefficients'] for x in out),
            'global_median_metrics':{m:round(statistics.median(x[m] for x in out),8) for m in metrics},
            'acceptance_5pct_original_absolute_count':sum(x['passes_predeclared_5pct_absolute_odd_even'] for x in out),
            'exploratory_5pct_relative_count':sum(x['passes_predeclared_5pct_relative_odd_even'] for x in out),
            'exploratory_5pct_relative_contiguous_band_count':sum(x['passes_predeclared_5pct_relative_blocked'] for x in out),
            'fifty_original_source_results':out,
            'source_documented_geometry_groups':{'30mm':5,'180mm':5},
            'not_full_kk_measurement_validation':True,
            'independent_lab_calibration_verified':False,
            'measured_capacity_Ah':False,
            'physical_damage_causality_verified':False,
            'field_safety_certification':False,
            'production_release_allowed':False}


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=2:return 2
    dest=Path(args[0]);csvdest=Path(args[1])
    try:
        if dest.exists() or csvdest.exists() or not dest.parent.exists() or not csvdest.parent.exists():
            raise ValueError('SOURCE_REVIEW_REQUIRED: invalid output target or already existing')
        outcome=run()
        dest.write_text(json.dumps(outcome,indent=2,sort_keys=True,ensure_ascii=False)+'\n',encoding='utf-8')
        fields=['original_specimen_id','source_diameter_mm','source_deformation_level','original_workbook_sha256',
                'passive_relaxation_absolute_odd_even_rmse_pct','passive_relaxation_relative_odd_even_rmse_pct',
                'passive_relaxation_relative_middle_band_rmse_pct','passive_relaxation_relative_odd_even_median_point_pct',
                'passive_relaxation_relative_middle_band_median_point_pct',
                'passes_predeclared_5pct_absolute_odd_even','passes_predeclared_5pct_relative_odd_even',
                'passes_predeclared_5pct_relative_blocked']
        with csvdest.open('x',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(outcome['fifty_original_source_results'])
        print('SOURCE_PINNED_50_REAL_POSITIVE_RELAXATION_SPECTRA',outcome['original_spectra'])
        print('SOURCE_POSITIVE_RELAXATION_50_GLOBAL_MEDIANS',outcome['global_median_metrics'])
        print('RETAINED_SOURCE_THRESHOLD_5PCT_COUNTS',outcome['acceptance_5pct_original_absolute_count'],
              outcome['exploratory_5pct_relative_count'],outcome['exploratory_5pct_relative_contiguous_band_count'])
        return 0
    except (ValueError,KeyError,TypeError,OSError,IndexError,ZeroDivisionError,OverflowError) as e:
        print('SOURCE_REVIEW_REQUIRED',str(e)[:220],file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())