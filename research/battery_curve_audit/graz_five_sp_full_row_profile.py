"""Graz five-cell original SP numeric row profiling; source-guarded no causal claims.

This is a raw-field inspection, not a physical calibration, capacity or impact test.
DOI 10.5281/zenodo.22079387. Never merge with four-cell Graz archive.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import io
import json
import math
import pathlib
import re
import zipfile

from research.battery_curve_audit import graz_five_cell_original_preflight as core
from research.battery_curve_audit import graz_five_cell_numeric_probe as prior

GOAL = 'graz-20261123-original-15-SP-measurement-row-profiling'
DATA_HEADER = re.compile(r'^\s*Time\s+Position\s*X\s*\[mm\]\s+Position\s*Z\s*\[mm\]', re.I)
START_EPOCH = re.compile(r'^\s*Start\s+time\s*:\s*([0-9]+(?:\.[0-9]+)?)', re.I)
MAX_SENSOR_ABS = 1_000_000_000


def isnum(x: str):
    try:
        v=float(x)
    except (ValueError, TypeError):
        return None
    return v if math.isfinite(v) and abs(v) < MAX_SENSOR_ABS else None


def profile_sp(z, member):
    counts=collections.Counter()
    start_epoch=None
    found_header=False
    examples=[]
    header_line=None
    valid_time_first=None
    valid_time_last=None
    time_lo=time_hi=None
    time_reversal=0
    previous_time=None
    dimension_counts=collections.Counter()
    minmax={str(i): [None,None] for i in range(6)}
    with z.open(member) as f:
        for lineno, raw in enumerate(f, 1):
            if lineno > 3_000_000:
                raise ValueError('source SP file unexpectedly long')
            # Preserve source bytes for parsing; no raw signal values saved beyond 3 representative lines.
            line=raw.decode('utf-8-sig',errors='replace').strip()
            if not found_header:
                m=START_EPOCH.match(line)
                if m:
                    if start_epoch is not None:
                        raise ValueError('duplicate Start time for one SP file')
                    start_epoch=float(m.group(1))
                if DATA_HEADER.search(line):
                    found_header=True
                    header_line=line[:280]
                    counts['header_line_no']=lineno
                continue
            if not line:
                continue
            counts['post_header_lines'] += 1
            if len(examples)<3:
                examples.append(line[:220])
            parts=line.split()
            dimension_counts[len(parts)]+=1
            if len(parts)!=6:
                counts['rows_wrong_token_count']+=1
                continue
            v=[isnum(x) for x in parts]
            if any(x is None for x in v):
                counts['rows_invalid_numeric']+=1
                continue
            counts['valid_six_numeric_rows']+=1
            for j,x in enumerate(v):
                mm=minmax[str(j)]
                mm[0]=x if mm[0] is None else min(mm[0],x)
                mm[1]=x if mm[1] is None else max(mm[1],x)
            time_value=v[0]
            if valid_time_first is None:
                valid_time_first=time_value
            valid_time_last=time_value
            time_lo=time_value if time_lo is None else min(time_lo,time_value)
            time_hi=time_value if time_hi is None else max(time_hi,time_value)
            if previous_time is not None and time_value<=previous_time:
                time_reversal+=1
            previous_time=time_value
    if start_epoch is None or not found_header:
        raise ValueError('original SP missing epoch start or 6-field sensor header')
    return {'source_member':member,'original_schema_header':header_line,
            'source_start_epoch':start_epoch,'row_count_checks':dict(counts),
            'first_three_rows_preview':examples,
            'original_token_width_histogram':{str(k):v for k,v in sorted(dimension_counts.items())},
            'valid_first_original_time_numeric':valid_time_first,
            'valid_last_original_time_numeric':valid_time_last,
            'time_value_minmax':[time_lo,time_hi], 'numeric_column_minmax':minmax,
            'time_nonincreasing_step_count':time_reversal,
            'original_time_column_unit_unverified':True,
            'instrument_sensor_calibration_unverified':True}


def inspect():
    meta=core.get_bytes(core.API,2_000_000)
    spec=core.validate_manifest(json.loads(meta))
    blob=core.get_bytes(spec['download_url'],core.MAX_ZIP_BYTES)
    if len(blob)!=spec['size'] or hashlib.md5(blob).hexdigest()!=core.PUBLISHER_MD5:
        raise ValueError('publisher original ZIP hash/size mismatch')
    structural=core.audit_archive(blob)
    if not structural['zip_crc_all_members_pass']:
        raise ValueError('ZIP CRC failure')
    result={}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        groups=prior.filename_groups(z.infolist())
        for cell,files in groups.items():
            result[cell]={'source_publisher_preload_kN':core.PUBLISHER_CELLS[cell],
                          'SP': [profile_sp(z, n) for n in sorted(files['sp_txt'])]}
    return {'goal_key':GOAL,'source_doi':core.DOI,
            'source_md5':core.PUBLISHER_MD5, 'source_sha256':hashlib.sha256(blob).hexdigest(),
            'source_zip_crc_all_members_pass':True,
            'num_physical_source_folders':len(result),
            'sp_file_count':sum(len(x['SP']) for x in result.values()),
            'sp_valid_numeric_rows':sum(f['row_count_checks'].get('valid_six_numeric_rows',0)
                                         for c in result.values() for f in c['SP']),
            'cells':result,
            'real_electrical_sp_signal_overlap_unverified':True,
            'source_time_unit_not_independently_proven':True,
            'individual_force_calibration_not_proven':True,
            'absolute_capacity_not_calculated':True,
            'impact_not_applied':True,
            'physical_causal_preload_inference_not_supported':True}


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=pathlib.Path)
    a=p.parse_args();result=inspect()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    print('GRAZ_REAL_SP_PROFILE_VALID_ROWS',result['sp_valid_numeric_rows'])
    for c, data in result['cells'].items():
        for x in data['SP']:
            print('GRAZ_ORIGINAL_SP',c,x['source_member'].rsplit('/',1)[-1],
                  x['row_count_checks'],x['time_value_minmax'],
                  x['first_three_rows_preview'][:1], flush=True)

if __name__=='__main__':main()