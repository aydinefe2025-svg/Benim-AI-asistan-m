"""Graz-original 10-specimen EIS stage transfer; physically independent specimen holdout.

Distinct from spectral odd/even holdout: the entire test physical specimen and
all its stage labels are withheld from training. A measured *same-specimen*
0%-deformation reference is required for each prediction. Not safety, capacity,
causality, or a calibrated clinical/field classifier.
"""
from __future__ import annotations
import csv, json, math, statistics, sys
from pathlib import Path

GOAL='graz-20261124-physical-cell-LOO-stage-transfer-original-eis-v1'
LEVELS=('0% deformation','25% deformation','50% deformation','75% deformation','95% deformation')
STAGES=LEVELS[1:]
PERMUTATIONS=2000
SEED=20261124


def validate_original_cells(cells):
    if len(cells)!=10:raise ValueError('SOURCE_REVIEW_REQUIRED: must have 10 source physical cells')
    ids=[];all_sha=set()
    for c in cells:
        name=c['name'];sha=c['original_sha256'];d=c['diameter_mm'];tables=c['tables']
        if name in ids or not name.startswith('EIS_C') or len(sha)!=64 or d not in (30,180):
            raise ValueError('SOURCE_REVIEW_REQUIRED: invalid specimen provenance')
        if not c['publisher_md5_crc_verified'] or set(tables)!=set(LEVELS):
            raise ValueError('SOURCE_REVIEW_REQUIRED: publisher original workbook integrity/stages')
        ids.append(name);all_sha.add(sha)
        freq=[x[0] for x in tables[LEVELS[0]]]
        if len(freq)!=101 or len(set(freq))!=101 or any(freq[i]<=freq[i+1] for i in range(100)):
            raise ValueError('SOURCE_REVIEW_REQUIRED: bad original frequency grid')
        for level in LEVELS:
            rows=tables[level]
            if len(rows)!=101 or [x[0] for x in rows]!=freq:
                raise ValueError('SOURCE_REVIEW_REQUIRED: original same-specimen frequencies not aligned')
            if any(len(row)!=3 or not all(math.isfinite(v) for v in row) or row[1]<=0 or abs(row[2])>360 for row in rows):
                raise ValueError('SOURCE_REVIEW_REQUIRED: malformed publisher physical EIS')
    if len(all_sha)!=10 or sum(c['diameter_mm']==30 for c in cells)!=5 or sum(c['diameter_mm']==180 for c in cells)!=5:
        raise ValueError('SOURCE_REVIEW_REQUIRED: wrong independent physical specimen/geometry count')
    return True


def exact_two_sided_sign_p(pos,n):
    if not 0<=pos<=n or n<1:raise ValueError('invalid exact sign test')
    tail=sum(math.comb(n,k) for k in range(0,min(pos,n-pos)+1))
    return min(1.,2*tail/(2**n))


def _complex_rows(rows):
    import numpy as np
    return np.asarray([mag*complex(math.cos(math.radians(phase)),math.sin(math.radians(phase))) for _,mag,phase in rows],complex)


def _arrays(cells):
    import numpy as np
    validate_original_cells(cells)
    features=[];metrics=[];raw=[]
    for c in cells:
        z0=_complex_rows(c['tables'][LEVELS[0]])
        f=np.asarray([x[0] for x in c['tables'][LEVELS[0]]],float)
        fvec=[]
        for level in LEVELS:
            rows=c['tables'][level];z=_complex_rows(rows)
            for (hz,mag,phase) in rows:
                raw.append({'source_specimen':c['name'].replace('EIS_','').replace('.xlsx',''),
                            'original_workbook_sha256':c['original_sha256'],
                            'source_diameter_mm':c['diameter_mm'],'deformation_stage':level,
                            'frequency_hz':hz,'impedance_ohm':mag,'phase_deg':phase})
            if level==LEVELS[0]:continue
            # Entire 0% spectrum measured from this specimen, no other specimen's baseline.
            delta=(z-z0)/np.abs(z0)
            fvec.append(delta)
            # Independent-of-model source signal metrics; NOT repeated-run measurement noise.
            rms=100*math.sqrt(float(np.sum(np.abs(z-z0)**2)/np.sum(np.abs(z0)**2)))
            median_point=float(100*np.median(np.abs(delta)))
            band_medians=[]
            for indices in (slice(0,33),slice(33,67),slice(67,101)):
                band_medians.append(round(float(100*np.median(np.abs(delta[indices]))),8))
            metrics.append({'source_specimen':c['name'].replace('EIS_','').replace('.xlsx',''),
                            'source_diameter_mm':c['diameter_mm'],'deformation_stage':level,
                            'source_workbook_sha256':c['original_sha256'],
                            'complex_shift_rms_vs_same_cell_0pct':round(rms,8),
                            'median_pointwise_complex_shift_vs_same_cell_0pct':round(median_point,8),
                            'three_original_frequency_band_medians_high_mid_low_pct':band_medians})
        features.append(np.asarray(fvec,complex))
    return np.asarray(features,complex),metrics,raw


def leave_one_specimen_out(features,geometry=None):
    """Strict source-cell LOO: no test cell's deformed EIS in any prototype."""
    import numpy as np
    arr=np.asarray(features,complex)
    if arr.shape!=(10,4,101) or not np.all(np.isfinite(arr)):
        raise ValueError('SOURCE_REVIEW_REQUIRED: expected ten physical cells x four stages x 101 Hz')
    if geometry is not None and (len(geometry)!=10 or sorted(geometry)!=[30]*5+[180]*5):
        raise ValueError('SOURCE_REVIEW_REQUIRED: invalid published geometry groups')
    predictions=[]
    for i in range(10):
        train=[j for j in range(10) if j!=i and (geometry is None or geometry[j]==geometry[i])]
        if i in train or len(train)!=(9 if geometry is None else 4):
            raise ValueError('SOURCE_REVIEW_REQUIRED: physical specimen training leakage')
        prototype=np.mean(arr[train],axis=0)
        distances=np.mean(np.abs(arr[i,:,None,:]-prototype[None,:,:])**2,axis=-1)
        guess=np.argmin(distances,axis=1)
        for stage in range(4):
            predictions.append({'heldout_specimen_index':i,'true_stage_index':stage,
                                'predicted_stage_index':int(guess[stage]),
                                'training_specimen_indices':train,
                                'no_test_specimen_training':i not in train,
                                'squared_feature_distances':[round(float(v),12) for v in distances[stage]]})
    return predictions


def _fast_loo_accuracy(arr,permutation=None,geometry=None):
    """Null-test kernel; preserve whole-specimen blocks, not frequency pseudo-replicates."""
    import numpy as np
    if permutation is not None:
        x=np.stack([arr[i,permutation[i]] for i in range(10)],axis=0)
    else:x=arr
    correct=0
    for i in range(10):
        train=[j for j in range(10) if j!=i and (geometry is None or geometry[j]==geometry[i])]
        p=x[train].mean(axis=0)
        distances=np.mean(np.abs(x[i,:,None,:]-p[None,:,:])**2,axis=-1)
        correct+=int(np.sum(np.argmin(distances,axis=1)==np.arange(4)))
    return correct


def _cluster_bootstrap_ci(predictions,nboot=4000):
    import numpy as np
    acc=np.asarray([int(p['true_stage_index']==p['predicted_stage_index']) for p in predictions],int).reshape(10,4)
    rng=np.random.default_rng(SEED+1)
    samples=rng.integers(0,10,size=(nboot,10))
    values=acc[samples].mean(axis=(1,2))
    return [round(float(v),6) for v in np.quantile(values,[0.025,0.975])]


def compute(cells,permutations=PERMUTATIONS):
    import numpy as np
    if permutations<100:raise ValueError('SOURCE_REVIEW_REQUIRED: too few cell-block permutations')
    features,metrics,raw=_arrays(cells)
    geometry=[c['diameter_mm'] for c in cells]
    preds=leave_one_specimen_out(features)
    geo_preds=leave_one_specimen_out(features,geometry)
    observed=sum(p['predicted_stage_index']==p['true_stage_index'] for p in preds)
    observed_geo=sum(p['predicted_stage_index']==p['true_stage_index'] for p in geo_preds)
    rng=np.random.default_rng(SEED)
    null=[];null_geo=[]
    for _ in range(permutations):
        perm=np.stack([rng.permutation(4) for _ in range(10)])
        null.append(_fast_loo_accuracy(features,perm))
        null_geo.append(_fast_loo_accuracy(features,perm,geometry))
    permutation_p=(1+sum(v>=observed for v in null))/(permutations+1)
    pgeo=(1+sum(v>=observed_geo for v in null_geo))/(permutations+1)
    cell_delta=[]
    for i,c in enumerate(cells):
        records=metrics[4*i:4*i+4]
        if [x['deformation_stage'] for x in records]!=list(STAGES):raise ValueError('SOURCE_REVIEW_REQUIRED: stage ordering')
        shift25=records[0]['complex_shift_rms_vs_same_cell_0pct']
        shift95=records[3]['complex_shift_rms_vs_same_cell_0pct']
        cell_delta.append({'source_specimen':records[0]['source_specimen'],
                           'source_diameter_mm':c['diameter_mm'],
                           'stage25_shift_pct':shift25,'stage95_shift_pct':shift95,
                           'stage95_minus_25_shift_percentage_points':round(shift95-shift25,8),
                           'all_four_source_shifts_strictly_increasing':all(records[j+1]['complex_shift_rms_vs_same_cell_0pct']>records[j]['complex_shift_rms_vs_same_cell_0pct'] for j in range(3))})
    nonzero=[x['stage95_minus_25_shift_percentage_points'] for x in cell_delta if abs(x['stage95_minus_25_shift_percentage_points'])>1e-12]
    pos=sum(x>0 for x in nonzero)
    all_pred=[]
    for mode,records in [('pooled',preds),('geometry_matched',geo_preds)]:
        for p0 in records:
            p=p0.copy();i=p.pop('heldout_specimen_index');stage=p.pop('true_stage_index');guess=p.pop('predicted_stage_index')
            p.update({'mode':mode,'source_specimen':cell_delta[i]['source_specimen'],
                      'source_diameter_mm':geometry[i],
                      'true_stage':STAGES[stage], 'predicted_stage':STAGES[guess],
                      'correct':stage==guess,
                      'training_specimen_ids':[cell_delta[j]['source_specimen'] for j in p.pop('training_specimen_indices')]})
            all_pred.append(p)
    return {'goal_key':GOAL,'source_doi':'10.5281/zenodo.18213931',
            'original_source_workbooks':10,'original_physical_specimens':10,
            'stages_per_cell_including_reference':5,'original_source_eis_triplets':len(raw),
            'heldout_predictions_per_mode':len(preds),
            'source_original_md5_crc_sha256_verified':True,
            'source_30mm_cells':5,'source_180mm_cells':5,
            'stage25_95_within_cell_signed_shift_differences':cell_delta,
            'stage95_shift_greater_than_stage25_cell_count':pos,
            'nonzero_paired_cells':len(nonzero),
            'stage95_vs_stage25_exact_two_sided_sign_p':round(exact_two_sided_sign_p(pos,len(nonzero)),8),
            'all_four_shift_monotonic_cell_count':sum(x['all_four_source_shifts_strictly_increasing'] for x in cell_delta),
            'median_stage95_minus_25_shift_percentage_points':round(statistics.median(x['stage95_minus_25_shift_percentage_points'] for x in cell_delta),8),
            'pooled_loo_correct':observed,'pooled_loo_accuracy_pct':round(100*observed/40,6),
            'geometry_matched_loo_correct':observed_geo,'geometry_matched_loo_accuracy_pct':round(100*observed_geo/40,6),
            'chance_balanced_four_stage_accuracy_pct':25,
            'pooled_loo_specimen_cluster_bootstrap_accuracy_95pct':_cluster_bootstrap_ci(preds),
            'pooled_loo_cellwise_label_permutation_p':round(permutation_p,6),
            'geometry_matched_loo_cellwise_label_permutation_p':round(pgeo,6),
            'permutations':permutations,'permutation_seed':SEED,
            'per_stage_source_shift_metrics':metrics,
            'heldout_specimen_predictions':all_pred,
            'not_5pct_equivalent_circuit_fit':True,
            'same_cell_reference_required_for_prediction':True,
            'independent_repeat_measurement_noise_established':False,
            'independent_instrument_calibration_verified':False,
            'mechanical_damage_causality_proven':False,
            'actual_capacity_Ah_measured':False,
            'field_deployment_safety_certified':False,
            'production_release_allowed':False},raw


def run():
    from research.battery_curve_audit.graz_eis_two_cpe_holdout import _source_originals
    cells=_source_originals()
    return compute(cells)


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=3:return 2
    try:
        dests=[Path(x) for x in args]
        if len(set(dests))!=3 or any(p.exists() or not p.parent.is_dir() for p in dests):
            raise ValueError('SOURCE_REVIEW_REQUIRED: output path collision/invalid')
        summary,raw=run()
        dests[0].write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        for path,records in ((dests[1],summary['heldout_specimen_predictions']),(dests[2],raw)):
            with path.open('x',encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(records[0]),extrasaction='raise')
                w.writeheader();w.writerows(records)
        print('ORIGINAL_PHYSICAL_CELLS',summary['original_physical_specimens'], 'EIS',summary['original_source_eis_triplets'])
        print('SOURCE_STAGE25_95',summary['stage95_shift_greater_than_stage25_cell_count'],
              summary['stage95_vs_stage25_exact_two_sided_sign_p'],
              summary['median_stage95_minus_25_shift_percentage_points'])
        print('SOURCE_LOO_TRANSFER',summary['pooled_loo_correct'],summary['geometry_matched_loo_correct'],
              'P',summary['pooled_loo_cellwise_label_permutation_p'],summary['geometry_matched_loo_cellwise_label_permutation_p'])
        return 0
    except (ValueError,KeyError,TypeError,ArithmeticError,OSError,IndexError) as e:
        print('SOURCE_REVIEW_REQUIRED',str(e)[:250],file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())