"""Explain and test Graz 2026 EIS high-frequency Re(Z) increase.

This is a SOURCE-DERIVED EXPLORATORY physical circuit-family repair: a
positive-real fractional series inductive dispersion Z=K*(j*f/fref)^alpha
with 0<alpha<1, plus Rs and nonnegative Debye RC relaxations. It is not
independent confirmation of the *family*, because family was suggested by
observing the original source spectra. Alpha selection is separately nested
across whole physical cells to prevent tuning alpha on the test specimen.
"""
from __future__ import annotations
import csv,json,math,statistics,sys
from pathlib import Path

GOAL='graz-20261124-fractional-series-positive-real-high-frequency-repair-50-original-v1'
LEVELS=('0% deformation','25% deformation','50% deformation','75% deformation','95% deformation')
CANDIDATE_ALPHAS=(.88,.89,.90,.905,.91,.915,.92,.925,.93,.94)
BASELINE_ALPHA=1.
FIXED_ALPHA=.90
REGULARIZATION=.0003
N_RELAXATIONS=24
ACCEPTANCE_PCT=5.


def validate_spectrum(spectrum):
    if len(spectrum)!=101:raise ValueError('SOURCE_REVIEW_REQUIRED: must be 101 original EIS points')
    arr=[];prev=None
    for row in spectrum:
        if len(row)!=3 or not all(isinstance(x,(float,int)) and math.isfinite(x) for x in row):
            raise ValueError('SOURCE_REVIEW_REQUIRED: invalid EIS triple')
        f,mag,phase=map(float,row)
        if f<=0 or mag<=0 or abs(phase)>360 or prev is not None and f>=prev:
            raise ValueError('SOURCE_REVIEW_REQUIRED: nonmonotonic or invalid original EIS')
        prev=f
        arr.append((f,mag*complex(math.cos(math.radians(phase)),math.sin(math.radians(phase)))))
    return arr


def _basis(freq,tau,reference_frequency,alpha):
    import numpy as np
    return np.column_stack([np.ones(len(freq)),(1j*freq/reference_frequency)**alpha,
                            *[1/(1+1j*2*math.pi*freq*t) for t in tau]])


def _fit_and_score(train,test,alpha):
    import numpy as np
    from scipy.optimize import nnls
    if not (.5<=alpha<=1):raise ValueError('SOURCE_REVIEW_REQUIRED: nonpassive/unsupported fractional alpha')
    f=np.array([x[0] for x in train],float);z=np.array([x[1] for x in train],complex)
    ft=np.array([x[0] for x in test],float);zt=np.array([x[1] for x in test],complex)
    if len(f)<12 or len(ft)<10 or set(f)&set(ft):raise ValueError('SOURCE_REVIEW_REQUIRED: invalid frequency holdout')
    scale=float(np.median(abs(z)));fref=float(max(f))
    if not scale>0 or not fref>0:raise ValueError('SOURCE_REVIEW_REQUIRED: degenerate source')
    tau=np.geomspace(1/(2*math.pi*max(f)*30),30/(2*math.pi*min(f)),N_RELAXATIONS)
    A=_basis(f,tau,fref,alpha);b=z/scale
    # Train-only complex least squares, same absolute loss and fixed regularizer
    # for alpha=1 baseline and fractional-alpha diagnostic.
    A=np.concatenate([A.real,A.imag],axis=0)
    b=np.r_[b.real,b.imag]
    D=np.zeros((N_RELAXATIONS-2,N_RELAXATIONS+2),float)
    for j in range(N_RELAXATIONS-2):D[j,j+2:j+5]=[1,-2,1]
    A=np.vstack([A,math.sqrt(REGULARIZATION)*D]);b=np.r_[b,np.zeros(N_RELAXATIONS-2)]
    x,_=nnls(A,b,maxiter=3000)
    if len(x)!=N_RELAXATIONS+2 or not np.all(np.isfinite(x)) or not np.all(x>=0):
        raise ValueError('SOURCE_REVIEW_REQUIRED: nonpositive/invalid physical coefficients')
    prediction=scale*_basis(ft,tau,fref,alpha).dot(x)
    return float(np.sum(abs(prediction-zt)**2)),float(np.sum(abs(zt)**2))


def heldout(spectrum,alpha,mode):
    pts=validate_spectrum(spectrum)
    n=len(pts)
    if mode=='parity':
        folds=[([i for i in range(n) if i%2==k],[i for i in range(n) if i%2!=k]) for k in (0,1)]
    elif mode=='middle_band':
        test=list(range(n//3,2*n//3));blocked=set(test)
        folds=[([i for i in range(n) if i not in blocked],test)]
    else:raise ValueError('SOURCE_REVIEW_REQUIRED: unknown holdout mode')
    e=norm=0.
    for train_idx,test_idx in folds:
        if set(train_idx)&set(test_idx):raise ValueError('SOURCE_REVIEW_REQUIRED: train/test frequency overlap')
        ee,nn=_fit_and_score([pts[i] for i in train_idx],[pts[i] for i in test_idx],alpha)
        e+=ee;norm+=nn
    if norm<=0:raise ValueError('SOURCE_REVIEW_REQUIRED: no test reference norm')
    return 100*math.sqrt(e/norm)


def select_alpha_without_test_cell(error_grid,test_cell):
    """Only nine other original physical specimens may choose the model alpha."""
    cells={k[0] for k in error_grid}
    if len(cells)!=10 or test_cell not in cells:raise ValueError('SOURCE_REVIEW_REQUIRED: invalid original cell selection')
    training=[k for k in error_grid if k[0]!=test_cell]
    if len(training)!=45:raise ValueError('SOURCE_REVIEW_REQUIRED: incomplete nine-cell training stages')
    scores=[]
    for alpha in CANDIDATE_ALPHAS:
        errors=[error_grid[k][alpha]['middle_band'] for k in training]
        scores.append((statistics.median(errors),alpha))
    return min(scores)[1]


def compute(cells):
    if len(cells)!=10 or len({c['name'] for c in cells})!=10:
        raise ValueError('SOURCE_REVIEW_REQUIRED: 10 independent source cells required')
    geometry=[c['diameter_mm'] for c in cells]
    if geometry.count(30)!=5 or geometry.count(180)!=5:
        raise ValueError('SOURCE_REVIEW_REQUIRED: source geometry counts')
    if not all(c['publisher_md5_crc_verified'] and len(c['original_sha256'])==64 for c in cells):
        raise ValueError('SOURCE_REVIEW_REQUIRED: original source hashes not verified')
    grid={};hf=[];meta={}
    for c in cells:
        cell=c['name'].replace('EIS_','').replace('.xlsx','')
        if set(c['tables'])!=set(LEVELS):raise ValueError('SOURCE_REVIEW_REQUIRED: source stages missing')
        reference=[r[0] for r in c['tables'][LEVELS[0]]]
        for stage in LEVELS:
            spectrum=c['tables'][stage]
            pts=validate_spectrum(spectrum)
            if [r[0] for r in spectrum]!=reference:raise ValueError('SOURCE_REVIEW_REQUIRED: mismatched physical cell frequencies')
            # Exact original high-frequency points: 100kHz and ~10.175kHz.
            if not 99999<=pts[0][0]<=100001 or not 10000<=pts[20][0]<=10300:
                raise ValueError('SOURCE_REVIEW_REQUIRED: source high-frequency anchor changed')
            high=pts[0][1].real;low=pts[20][1].real
            if not high>0 or not low>0:raise ValueError('SOURCE_REVIEW_REQUIRED: invalid high-frequency physical Re(Z)')
            hf.append({'source_specimen':cell,'deformation_stage':stage,
                       'original_workbook_sha256':c['original_sha256'],
                       'source_100khz_real_milliohm':round(high*1000,8),
                       'source_near_10khz_real_milliohm':round(low*1000,8),
                       'source_high_frequency_real_increase':high>low,
                       'source_real_ratio_100khz_over_near10khz':round(high/low,8)})
            key=(cell,stage)
            meta[key]={'source_specimen':cell,'deformation_stage':stage,
                       'source_diameter_mm':c['diameter_mm'],'original_workbook_sha256':c['original_sha256']}
            grid[key]={}
            for alpha in (*CANDIDATE_ALPHAS,BASELINE_ALPHA):
                grid[key][alpha]={'parity':heldout(spectrum,alpha,'parity'),
                                  'middle_band':heldout(spectrum,alpha,'middle_band')}
    results=[];selections={}
    for c in cells:
        cell=c['name'].replace('EIS_','').replace('.xlsx','')
        chosen=select_alpha_without_test_cell(grid,cell)
        selections[cell]=chosen
        for stage in LEVELS:
            key=(cell,stage)
            results.append({**meta[key],
                'alpha_selected_by_other_nine_physical_cells':chosen,
                'source_test_cell_excluded_from_alpha_selection':True,
                'test_cell_frequencies_used_to_fit_amplitudes':True,
                'ideal_L_parity_rmse_pct':round(grid[key][BASELINE_ALPHA]['parity'],8),
                'ideal_L_middle_band_rmse_pct':round(grid[key][BASELINE_ALPHA]['middle_band'],8),
                'nested_fractional_parity_rmse_pct':round(grid[key][chosen]['parity'],8),
                'nested_fractional_middle_band_rmse_pct':round(grid[key][chosen]['middle_band'],8),
                'fixed_0p90_fractional_parity_rmse_pct':round(grid[key][FIXED_ALPHA]['parity'],8),
                'fixed_0p90_fractional_middle_band_rmse_pct':round(grid[key][FIXED_ALPHA]['middle_band'],8),
                'passes_5pct_ideal_L_parity':grid[key][BASELINE_ALPHA]['parity']<ACCEPTANCE_PCT,
                'passes_5pct_nested_fractional_parity':grid[key][chosen]['parity']<ACCEPTANCE_PCT,
                'passes_5pct_nested_fractional_middle_band':grid[key][chosen]['middle_band']<ACCEPTANCE_PCT,
                'production_release_allowed':False})
    keys=['ideal_L_parity_rmse_pct','ideal_L_middle_band_rmse_pct',
          'nested_fractional_parity_rmse_pct','nested_fractional_middle_band_rmse_pct',
          'fixed_0p90_fractional_parity_rmse_pct','fixed_0p90_fractional_middle_band_rmse_pct']
    summary={
        'goal_key':GOAL,'source_doi':'10.5281/zenodo.18213931',
        'source_original_workbooks':10,'source_original_spectra':50,
        'original_frequency_magnitude_phase_triplets':5050,
        'original_source_md5_crc_sha256_verified':True,
        'original_100khz_real_increase_count':sum(r['source_high_frequency_real_increase'] for r in hf),
        'median_original_100khz_to_near10khz_real_ratio':round(statistics.median(r['source_real_ratio_100khz_over_near10khz'] for r in hf),8),
        'high_frequency_real_source_evidence':hf,
        'nested_test_cell_excluded_from_alpha_choice':True,
        'source_test_cell_frequency_train_test_disjoint':True,
        'candidate_fractional_orders':CANDIDATE_ALPHAS,
        'alpha_selected_by_nine_other_cells':selections,
        'selection_metric':'median whole-middle-frequency-band relative complex RMSE over 45 spectra of 9 other source cells',
        'selection_is_exploratory_after_observing_source_family':True,
        'fixed_smoothness_regularization':REGULARIZATION,'positive_rc_relaxation_count':N_RELAXATIONS,
        'fractional_series_model':'Rs + K*(j*f/fmax)^alpha + sum_positive_Rk/(1+j*2*pi*f*tauk)',
        'all_nonnegative_coefficients_enforced':True,
        'source_spectral_median_rmse_pct':{k:round(statistics.median(r[k] for r in results),8) for k in keys},
        'ideal_L_parity_pass_count':sum(r['passes_5pct_ideal_L_parity'] for r in results),
        'nested_fractional_parity_pass_count':sum(r['passes_5pct_nested_fractional_parity'] for r in results),
        'nested_fractional_middle_band_pass_count':sum(r['passes_5pct_nested_fractional_middle_band'] for r in results),
        'fixed_0p90_parity_pass_count':sum(r['fixed_0p90_fractional_parity_rmse_pct']<ACCEPTANCE_PCT for r in results),
        'fixed_0p90_middle_band_pass_count':sum(r['fixed_0p90_fractional_middle_band_rmse_pct']<ACCEPTANCE_PCT for r in results),
        'fifty_original_source_spectra':results,
        'not_physical_cell_out_of_sample_impedance_prediction':True,
        'not_independent_confirmation_of_model_family':True,
        'not_independent_instrument_calibration':True,
        'not_full_kramers_kronig_measurement_validation':True,
        'physical_mechanism_causality_unverified':True,
        'actual_battery_capacity_Ah_measured':False,
        'field_safety_certified':False,'production_release_allowed':False,
    }
    return summary


def run():
    from research.battery_curve_audit.graz_eis_two_cpe_holdout import _source_originals
    return compute(_source_originals())


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=2:return 2
    try:
        paths=[Path(x) for x in args]
        if paths[0]==paths[1] or any(x.exists() or not x.parent.is_dir() for x in paths):
            raise ValueError('SOURCE_REVIEW_REQUIRED: invalid output path')
        result=run()
        paths[0].write_text(json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        fields=list(result['fifty_original_source_spectra'][0])
        with paths[1].open('x',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(result['fifty_original_source_spectra'])
        print('FRACTIONAL_SOURCE_HIGH_FREQ_REAL_INCREASE',result['original_100khz_real_increase_count'],'/50')
        print('NESTED_9_CELL_ALPHA',result['alpha_selected_by_nine_other_cells'])
        print('SOURCE_ORIGINAL_50_MODEL_RMSE',result['source_spectral_median_rmse_pct'])
        print('SOURCE_ORIGINAL_50_PASSES',result['ideal_L_parity_pass_count'],
              result['nested_fractional_parity_pass_count'],result['nested_fractional_middle_band_pass_count'])
        return 0
    except (ValueError,TypeError,KeyError,IndexError,OSError,ArithmeticError) as e:
        print('SOURCE_REVIEW_REQUIRED',str(e)[:250],file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())