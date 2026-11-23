"""Complex-plane EIS identity audit of ten publisher-original Graz cells.

Novel observable beyond published same-cell |Z| percent-change:
  V = 100 * |Z_deformed - Z_undeformed| / |Z_undeformed|
where the original source has |Z| ohm and phase degrees. This does not
measure discharge capacity, force, causality, or battery safety.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

from research.battery_curve_audit import graz_eis_2026_source_audit as source
from research.battery_curve_audit import graz_eis_2026_same_cell_delta as polar
from research.battery_curve_audit import graz_eis_group_geometry_audit as geometry

FOCAL_HZ=(10.0,1000.0)
RECORD=18213931

def _focal(baseline,stage,target):
    idx=min(range(len(baseline)),key=lambda i:abs(math.log(baseline[i][0]/target)))
    if abs(math.log(baseline[idx][0]/target))>=0.14:
        raise ValueError('SOURCE_REVIEW_REQUIRED: source frequency too far from target')
    a,b=baseline[idx],stage[idx]
    re0,minus_i0=polar.cartesian_nyquist(a)
    re1,minus_i1=polar.cartesian_nyquist(b)
    phase_delta=math.degrees(math.atan2(math.sin(math.radians(b[2]-a[2])),
                                        math.cos(math.radians(b[2]-a[2]))))
    return {
        'nominal_hz':target, 'original_frequency_hz':a[0],
        'complex_vector_change_pct':round(polar.complex_shift_pct(a,b),8),
        'magnitude_only_absolute_change_pct':round(polar.abs_magnitude_shift_pct(a,b),8),
        'delta_real_milliohm':round((re1-re0)*1000,10),
        'delta_nyquist_minus_imag_milliohm':round((minus_i1-minus_i0)*1000,10),
        'wrapped_phase_change_deg':round(phase_delta,8),
    }

def compare_same_original(tables,cellname):
    if set(tables)!=set(polar.LEVELS):
        raise ValueError('SOURCE_REVIEW_REQUIRED: incomplete source stages')
    baseline=tables[polar.LEVELS[0]]
    if len(baseline)!=101:raise ValueError('SOURCE_REVIEW_REQUIRED: missing source frequencies')
    if any((not isinstance(t,(tuple,list)) or len(t)!=3) for t in baseline):
        raise ValueError('SOURCE_REVIEW_REQUIRED: wrong baseline data')
    stages=[]
    for level in polar.LEVELS[1:]:
        observed=tables[level]
        if len(observed)!=101:raise ValueError('SOURCE_REVIEW_REQUIRED: changed frequency count')
        complex_deltas=[]
        magnitude_deltas=[]
        phase_dominant_count=0
        for original,new in zip(baseline,observed):
            v=polar.complex_shift_pct(original,new)
            m=polar.abs_magnitude_shift_pct(original,new)
            if v+1e-9<m:raise ValueError('SOURCE_REVIEW_REQUIRED: reverse triangle violated')
            complex_deltas.append(v)
            magnitude_deltas.append(m)
            if v>2*m+0.01:phase_dominant_count+=1
        stages.append({
            'stage':level, 'frequencies_compared':101,
            'median_complex_vector_pct':round(statistics.median(complex_deltas),8),
            'median_absolute_magnitude_pct':round(statistics.median(magnitude_deltas),8),
            'phase_sensitive_frequencies_2x_magnitude_count':phase_dominant_count,
            'focal_original_frequency_comparisons':[
                _focal(baseline,observed,hz) for hz in FOCAL_HZ
            ],
        })
    return {'filename':cellname,'stages':stages,
            '95pct_median_complex_vector_pct':stages[-1]['median_complex_vector_pct'],
            '95pct_median_absolute_magnitude_pct':stages[-1]['median_absolute_magnitude_pct'],
            '95pct_phase_sensitive_2x_count':stages[-1]['phase_sensitive_frequencies_2x_magnitude_count']}

def run():
    md=geometry.real_readme()
    if not md.get('original_publisher_readme_mapping_verified'):
        raise ValueError('SOURCE_REVIEW_REQUIRED: original geometry mapping absent')
    mapping={}
    for group in md['publisher_documented_groups']:
        for physical_id in group['original_specimen_ids']:
            key=f'EIS_{physical_id}.xlsx'
            if key in mapping:raise ValueError('SOURCE_REVIEW_REQUIRED: duplicate geometry claim')
            mapping[key]=group['indenter_diameter_mm']
    if set(mapping)!=set(source.PINS):
        raise ValueError('SOURCE_REVIEW_REQUIRED: original README identity coverage mismatch')
    metadata=json.loads(source.fetch(f'https://zenodo.org/api/records/{RECORD}',600000))
    if metadata.get('id')!=RECORD or metadata.get('doi')!=source.DOI:
        raise ValueError('SOURCE_REVIEW_REQUIRED: original Zenodo record changed')
    entry={v['key']:v for v in metadata.get('files',[]) if v.get('key') in source.PINS}
    if len(entry)!=10:raise ValueError('SOURCE_REVIEW_REQUIRED: original workbook list incomplete')
    per_cell=[]
    for filename,pin in source.PINS.items():
        e=entry[filename]
        if e.get('checksum')!='md5:'+pin:
            raise ValueError('SOURCE_REVIEW_REQUIRED: publisher MD5 mismatch')
        url=e.get('links',{}).get('self','')
        if not isinstance(url,str) or not url.startswith('https://zenodo.org/'):
            raise ValueError('SOURCE_REVIEW_REQUIRED: bad source URL')
        original=source.fetch(url,source.MAX_FILE_BYTES)
        provenance=source.inspect_original_workbook(original,filename,pin)
        real_sheets=polar.tables_from_original(original)
        cell=compare_same_original(real_sheets,filename)
        cell.update({
            'publisher_original_workbook_sha256':provenance['source_sha256'],
            'publisher_md5_and_crc_verified':True,
            'source_documented_impactor_mm':mapping[filename],
        })
        per_cell.append(cell)
    per_cell.sort(key=lambda c:c['filename'])
    groups=[]
    for diameter in (30,180):
        members=[c for c in per_cell if c['source_documented_impactor_mm']==diameter]
        if len(members)!=5:raise ValueError('SOURCE_REVIEW_REQUIRED: source group count')
        groups.append({
            'source_documented_impactor_mm':diameter,'original_physical_cells':5,
            'median_of_cell_median_complex_95pct':round(
                statistics.median(x['95pct_median_complex_vector_pct'] for x in members),8),
            'median_of_cell_median_abs_magnitude_95pct':round(
                statistics.median(x['95pct_median_absolute_magnitude_pct'] for x in members),8),
            'median_cell_phase_sensitive_frequency_count_95pct':statistics.median(
                x['95pct_phase_sensitive_2x_count'] for x in members),
        })
    return {
        'goal_key':'graz-20261123-10-original-eis-complex-vectors-source-pinned-v1',
        'original_source_doi':source.DOI,'source_readme_md5_verified':True,
        'original_workbook_count':len(per_cell),
        'original_spectral_triplets':len(per_cell)*5*101,
        'total_frequency_contrasts':len(per_cell)*4*101,
        'mathematical_reverse_triangle_all_frequencies_pass':True,
        'publisher_documented_diameter_groups':{'30mm':5,'180mm':5},
        'per_cell_95pct':per_cell, 'source_diameter_group_descriptives':groups,
        'relative_complex_vector_is_not_total_impedance_magnitude':True,
        'independent_physical_custody_verified':False,
        'absolute_eis_calibration_verified':False,
        'capacity_Ah_measured':False,
        'individual_force_calibration_verified':False,
        'damage_causality_proven':False,
        'production_release_allowed':False,
        'scientific_decision':'SOURCE_MEASURED_EIS_COMPLEX_VECTOR_CONTRAST_ONLY',
    }

def main(args=None):
    argv=sys.argv[1:] if args is None else args
    if len(argv)!=1:return 2
    target=Path(argv[0])
    try:
        if target.exists() or not target.parent.is_dir():
            raise ValueError('SOURCE_REVIEW_REQUIRED: output exists or parent absent')
        result=run()
        with target.open('x',encoding='utf-8') as file:
            json.dump(result,file,indent=2,sort_keys=True);file.write('\n')
        print('GRAZ_REAL_EIS_COMPLEX_VECTORS',result['original_workbook_count'],
              result['total_frequency_contrasts'])
        for x in result['source_diameter_group_descriptives']:
            print('SOURCE_DOCUMENTED_IMPACTOR_GROUP',x)
        return 0
    except (ValueError,OSError,TypeError,KeyError,IndexError,OverflowError) as exc:
        print('SOURCE_REVIEW_REQUIRED',str(exc)[:250],file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
