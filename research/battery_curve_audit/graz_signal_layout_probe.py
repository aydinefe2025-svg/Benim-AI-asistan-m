"""Bounded source-authenticated forensic layout probe for Graz's original 02/03 traces.

The probe deliberately avoids lab claims and raw waveform uploads. Its output holds
only column shapes, short beginning/end samples, parsing counts and time ranges.
"""
from __future__ import annotations
import argparse, io, json, re, zipfile
from pathlib import Path
from research.battery_curve_audit import graz_source_preflight as original

MAX_PREVIEW_LINES = 4
MAX_DISPLAY = 160

def summarise_member(z: zipfile.ZipFile, member: zipfile.ZipInfo, kind: str) -> dict:
    start: list[str] = []
    end: list[str] = []
    number_lines = 0
    rows = 0
    first_numeric = None
    last_numeric = None
    sample_shape = {}
    prefix = []
    for raw in z.open(member):
        number_lines += 1
        if number_lines > 1_000_000:
            raise ValueError('Unexpected excessive source lines')
        line = raw.decode('utf-8-sig', errors='replace').strip('\ufeff\r\n')
        if len(prefix)<20: prefix.append(line[:MAX_DISPLAY])
        if not line.strip(): continue
        if kind == 'electrical':
            if line.lower().lstrip().startswith('time, device, voltage, current, power'): continue
            vals = [v.strip() for v in line.split(',')]
            if len(vals) == 5 and re.fullmatch(r'\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d-\d+', vals[0]):
                rows += 1
                if first_numeric is None: first_numeric=vals
                last_numeric=vals
                if len(start)<MAX_PREVIEW_LINES: start.append(line[:MAX_DISPLAY])
                end.append(line[:MAX_DISPLAY]);end=end[-MAX_PREVIEW_LINES:]
                for i, v in enumerate(vals[2:]):
                    if i==0: # voltage
                        try: sample_shape.setdefault('voltage_prefix',[]).append(float(v))
                        except ValueError: pass
                    if len(sample_shape.get('voltage_prefix',[]))>2:sample_shape['voltage_prefix']=sample_shape['voltage_prefix'][:2]
        else:
            # SP numeric times may use comma-decimal, tab separation; never guess units.
            cols = [x.strip() for x in re.split(r'\t+', line.strip()) if x.strip()]
            numeric=(len(cols)==6 and bool(re.fullmatch(r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}',cols[0])))
            if numeric:
                rows += 1
                if first_numeric is None: first_numeric=cols
                last_numeric=cols
                if len(start)<MAX_PREVIEW_LINES:start.append(line[:MAX_DISPLAY])
                end.append(line[:MAX_DISPLAY]);end=end[-MAX_PREVIEW_LINES:]
                sample_shape['numeric_column_counts']=sorted(set(sample_shape.get('numeric_column_counts',[])+[len(cols)]))
    return {'member_basename':Path(member.filename).name,
        'original_bytes':member.file_size,'physical_source_label':original.explicit_cell_in_path(member.filename),
        'role':kind,'raw_lines':number_lines,'parsed_candidate_rows':rows,
        'head_lines':prefix[:15],
        'first_rows':start,'last_rows':end,
        'first_fields':first_numeric,'last_fields':last_numeric,
        'format_clues':sample_shape,
        'numeric_time_unit_verified':False,'signal_phase_join_verified':False}

def inspect_source(blob:bytes,expected_size:int)->dict:
    cert=original.inspect_archive(blob,expected_size)
    findings=[]
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for m in z.infolist():
            if m.is_dir() or original.explicit_cell_in_path(m.filename) not in ('02','03'):continue
            role=original.role_for_member(m.filename)
            if role not in ('thickness_sp_candidate','charge_discharge_log_candidate'):continue
            findings.append(summarise_member(z,m,'electrical' if role=='charge_discharge_log_candidate' else 'sp'))
    if len(findings)!=8:raise ValueError('Expected two electrical and six SP original source members')
    return {'source_doi':original.DOI,'full_archive_sha256':cert['original_zip_sha256'],
        'publisher_full_archive_md5_pass':True,'member_crc_pass':True,
        'source_layouts':findings,'tested_raw_source_file_count':len(findings),
        'individual_sensor_time_axis_verified':False,'source_stage_equality_verified':False,
        'measured_false_match_rate':None,'not_a_physical_impact_trial':True}

def main()->None:
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);args=p.parse_args()
    blob,size=original.get_original();out=inspect_source(blob,size)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    for q in out['source_layouts']:
        print('REAL_SOURCE_LAYOUT',q['physical_source_label'],q['role'],q['parsed_candidate_rows'],q['member_basename'])
    print('PHASE_AND_SYNC_STILL_NOT_CERTIFIED')

if __name__=='__main__':main()