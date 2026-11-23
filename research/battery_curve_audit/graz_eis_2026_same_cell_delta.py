"""Publisher-original *same-file, same-frequency* EIS shifts at Graz 2026 levels.

Compute impedance magnitude and measured phase contrasts without treating
EIS as capacity, inferring cause, or certifying electrochemical damage/safety.
Original publisher MD5 / ZIP CRC are independently checked by source_audit.
"""
from __future__ import annotations
import io, json, math, statistics, sys, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile
from research.battery_curve_audit import graz_eis_2026_source_audit as audit

LEVELS=('0% deformation','25% deformation','50% deformation','75% deformation','95% deformation')
FREQUENCIES_HZ=(10.,1000.)

def tables_from_original(raw:bytes)->dict:
    """Extract 5 original worksheets, each with 101 genuine triple measurements."""
    with ZipFile(io.BytesIO(raw)) as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            sr=audit._xml(z,'xl/sharedStrings.xml')
            shared=[''.join(x.text or '' for x in si.iter(audit.X+'t')) for si in sr.findall(audit.X+'si')]
        wb=audit._xml(z,'xl/workbook.xml')
        rels=audit._xml(z,'xl/_rels/workbook.xml.rels')
        mapping={x.attrib['Id']:x.attrib['Target'] for x in rels.findall(audit.PKG+'Relationship')}
        result={}
        for sheet in wb.findall('.//'+audit.X+'sheet'):
            name=sheet.attrib.get('name','')
            if name not in LEVELS or name in result:raise ValueError('SOURCE_REVIEW_REQUIRED: unexpected deformation worksheet')
            target=mapping.get(sheet.attrib.get(audit.R+'id',''),'')
            if not target:raise ValueError('SOURCE_REVIEW_REQUIRED: missing original worksheet target')
            path=(target.lstrip('/') if target.startswith('/xl/') else
                  target if target.startswith('xl/') else 'xl/'+target.lstrip('/'))
            if not path.startswith('xl/worksheets/'):
                raise ValueError('SOURCE_REVIEW_REQUIRED: bad original sheet reference')
            root=audit._xml(z,path)
            sheetrows=root.findall('.//'+audit.X+'sheetData/'+audit.X+'row')
            if len(sheetrows)!=102:raise ValueError('SOURCE_REVIEW_REQUIRED: unexpected EIS frequency count')
            header={c.attrib.get('r'):audit._cell_text(c,shared).strip().casefold() for c in sheetrows[0].findall(audit.X+'c')}
            if header!={'A1':'frequency\\hz','B1':'impedance\\ohm','C1':'phase\\deg'}:
                raise ValueError('SOURCE_REVIEW_REQUIRED: source frequency/EIS/phase header changed')
            points=[]
            for j,row in enumerate(sheetrows[1:],start=2):
                cells={c.attrib.get('r'):c for c in row.findall(audit.X+'c')}
                if set(cells)!={f'{x}{j}' for x in 'ABC'}:
                    raise ValueError('SOURCE_REVIEW_REQUIRED: incomplete original frequency triplet')
                v=[float(audit._cell_text(cells[f'{x}{j}'],shared)) for x in 'ABC']
                if not all(math.isfinite(x) for x in v) or v[0]<=0 or v[1]<=0 or abs(v[2])>360:
                    raise ValueError('SOURCE_REVIEW_REQUIRED: invalid physical source EIS row')
                if points and v[0]>=points[-1][0]:
                    raise ValueError('SOURCE_REVIEW_REQUIRED: source frequency grid is not descending')
                points.append(tuple(v))
            result[name]=points
        if set(result)!=set(LEVELS):raise ValueError('SOURCE_REVIEW_REQUIRED: incomplete deformation sequence')
        reference=[x[0] for x in result[LEVELS[0]]]
        for level in LEVELS[1:]:
            if [x[0] for x in result[level]]!=reference:
                raise ValueError('SOURCE_REVIEW_REQUIRED: different frequency grid across same original specimen')
        return result

def analyze_same_source(raw:bytes,name:str,pin:str)->dict:
    provenance=audit.inspect_original_workbook(raw,name,pin)
    levels=tables_from_original(raw)
    baseline=levels[LEVELS[0]]
    stage=[]
    for level in LEVELS:
        rows=levels[level]
        contrasts=[100*(cur[1]/b[1]-1) for b,cur in zip(baseline,rows)]
        stage.append({'level':level,'spectrum_rows':len(rows),
                      'median_impedance_magnitude_change_pct':round(statistics.median(contrasts),6),
                      'min_impedance_magnitude_change_pct':round(min(contrasts),6),
                      'max_impedance_magnitude_change_pct':round(max(contrasts),6),
                      'positive_frequency_point_count':sum(d>0 for d in contrasts),
                      'negative_frequency_point_count':sum(d<0 for d in contrasts),
                      'sampled_frequencies':[]})
        for hz in FREQUENCIES_HZ:
            i=min(range(len(rows)),key=lambda k:abs(math.log(rows[k][0]/hz)))
            if abs(math.log(rows[i][0]/hz))>0.14:
                raise ValueError('SOURCE_REVIEW_REQUIRED: requested diagnostic frequency not supported')
            b=baseline[i];p=rows[i]
            stage[-1]['sampled_frequencies'].append({'nominal_target_hz':hz,
               'source_frequency_hz':p[0],
               'source_magnitude_ohm':p[1],
               'original_baseline_magnitude_ohm':b[1],
               'impedance_change_pct':round(100*(p[1]/b[1]-1),6),
               'source_phase_deg':p[2],
               'phase_difference_deg':round(p[2]-b[2],6)})
    return {'filename':name,'source_sha256':provenance['source_sha256'],
             'publisher_md5_crc':True,'same_file_frequency_grid_equal':True,
             'per_stage_source_measurement_count':101,'stages':stage}

def run()->dict:
    meta=json.loads(audit.fetch('https://zenodo.org/api/records/18213931',600_000))
    if meta.get('id')!=audit.RECORD:raise ValueError('SOURCE_REVIEW_REQUIRED: source metadata ID conflict')
    lookup={x['key']:(x.get('checksum'),x.get('links',{}).get('self')) for x in meta.get('files',[])}
    out=[]
    for name,pin in audit.PINS.items():
        if name not in lookup or lookup[name][0]!='md5:'+pin:
            raise ValueError('SOURCE_REVIEW_REQUIRED: original publisher inventory changed')
        url=lookup[name][1]
        if not isinstance(url,str) or not url.startswith('https://zenodo.org/'):
            raise ValueError('SOURCE_REVIEW_REQUIRED: untrusted original source URL')
        raw=audit.fetch(url,audit.MAX_FILE_BYTES)
        out.append(analyze_same_source(raw,name,pin))
    final=[]
    for level in LEVELS[1:]:
        obs=[next(x for x in cell['stages'] if x['level']==level) for cell in out]
        per_cell=[o['median_impedance_magnitude_change_pct'] for o in obs]
        final.append({'level':level,'source_cell_count':len(per_cell),
               'median_of_per_cell_spectral_medians_pct':round(statistics.median(per_cell),6),
               'cells_with_positive_spectral_median':sum(x>0 for x in per_cell),
               'cells_with_negative_spectral_median':sum(x<0 for x in per_cell)})
    return {'schema':'cano.graz.2026.original-eis-same-specimen-stage-frequency.v1',
     'source_doi':audit.DOI,'publisher_workbooks_checked':len(out),
     'original_frequency_points_per_stage':101,'stages_per_source':5,
     'total_original_eis_spectrum_triplets':len(out)*101*5,
     'cell_stage_data':out,'cross_cell_description_not_causal':final,
     'within_original_workbook_frequency_grid_aligned':True,
     'source_spreadsheet_same_cell_id_is_publisher_record_not_independent_custody':True,
     'instrument_calibration_independently_verified':False,
     'mechanical_force_calibration_independently_verified':False,
     'actual_capacity_Ah_measured':False,
     'eis_magnitude_not_battery_capacity':True,
     'field_FPR_FNR_established':False,'production_release_allowed':False,
     'decision':'REAL_ORIGINAL_SAME_PUBLISHER_CELL_DEFORMATION_EIS_RESEARCH_ONLY'}

def main(argv=None)->int:
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=1:return 2
    try:
        path=Path(args[0])
        if path.exists() or not path.parent.is_dir():raise ValueError('SOURCE_REVIEW_REQUIRED: output must not exist')
        result=run()
        with path.open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
        print('GRAZ_REAL_EIS_MEASURED_STAGE',result['publisher_workbooks_checked'],result['total_original_eis_spectrum_triplets'])
        print('GRAZ_DEFORMATION_95_COMPARISON',json.dumps(result['cross_cell_description_not_causal'][-1],sort_keys=True))
        return 0
    except (ValueError,OSError,UnicodeError,KeyError,TypeError,OverflowError) as e:
        print('SOURCE_REVIEW_REQUIRED:',str(e)[:180],file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())