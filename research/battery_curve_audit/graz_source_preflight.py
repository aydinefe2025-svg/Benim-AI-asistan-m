"""Read-only publisher-archive authentication and cell-02/03 phase inventory.

This does NOT quantify damage, cross-cell mismatch, or sensor calibration.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import re
import urllib.parse
import urllib.request
import zipfile
from pathlib import PurePosixPath, Path

DOI = '10.5281/zenodo.22079387'
RECORD = 22079387
OFFICIAL_MD5 = 'b9ed863766e30afbd0e309951c855d08'
MAX_COMPRESSED = 40_000_000
MAX_MEMBER_SIZE = 200_000_000
MAX_UNCOMPRESSED = 500_000_000
CELL_PRELOAD_KN = {'01': 0, '02': 1.5, '03': 3, '04': 5, '05': 15}

def safe_member(info: zipfile.ZipInfo) -> None:
    n = info.filename.replace('\\', '/')
    parts = PurePosixPath(n).parts
    if not n or n.startswith('/') or re.match(r'^[A-Za-z]:', n) or '..' in parts or info.file_size > MAX_MEMBER_SIZE:
        raise ValueError('unsafe ZIP member: ' + n[:100])
    if info.create_system == 3 and ((info.external_attr >> 16) & 0o170000) == 0o120000:
        raise ValueError('ZIP symlink not allowed')

def explicit_cell_in_path(path: str) -> str | None:
    # Avoid false-positive YYYY, timestamps, stages and arbitrary sequence digits.
    stem = path.lower().replace('\\', '/')
    hits = set(re.findall(r'(?<![a-z0-9])(?:cell|sample|specimen|battery)[ _-]*0?([1-5])(?![0-9])', stem))
    for p in stem.split('/'):
        if re.fullmatch(r'0[1-5]', p):
            hits.add(p[1:])
    return f'{int(next(iter(hits))):02d}' if len(hits) == 1 else None

def role_for_member(name: str) -> str:
    base = PurePosixPath(name).name.lower()
    if re.search(r'(^|[_ .-])sp([_ .-]|\d|$)', base):
        return 'thickness_sp_candidate'
    if 'log' in base:
        return 'charge_discharge_log_candidate'
    return 'unclassified'

def inspect_archive(data: bytes, expected_size: int, md5: str = OFFICIAL_MD5) -> dict:
    if not 0 < len(data) <= MAX_COMPRESSED or len(data) != expected_size:
        raise ValueError('official byte count not met')
    if hashlib.md5(data).hexdigest() != md5 or md5 != OFFICIAL_MD5:
        raise ValueError('official publisher MD5 not met')
    rows = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        members = z.infolist()
        if not members or len(members) > 4000:
            raise ValueError('ZIP member count invalid')
        total = 0
        for m in members:
            safe_member(m)
            total += m.file_size
            if total > MAX_UNCOMPRESSED:
                raise ValueError('ZIP expanded total unsafe')
        corrupt = z.testzip()
        if corrupt:
            raise ValueError('ZIP CRC invalid: ' + corrupt)
        for m in members:
            if m.is_dir():
                continue
            row = {'path': m.filename, 'bytes': m.file_size,
                   'cell_id_from_name_only': explicit_cell_in_path(m.filename),
                   'candidate_role_from_name_only': role_for_member(m.filename)}
            if m.file_size <= 30_000_000 and PurePosixPath(m.filename).suffix.lower() in ('.csv','.txt','.log','.tsv'):
                # Headers only; do not re-publish raw signal values.
                with z.open(m) as f:
                    first = f.read(8192).decode('utf-8-sig',errors='replace')
                row['first_nonempty_header_preview'] = next((x[:170] for x in first.splitlines() if x.strip()), '')
                if row['cell_id_from_name_only'] in ('02','03'):
                    # Targeted schema reconnaissance only: no numeric waveform dumps.
                    prefix = first.splitlines()[:70]
                    row['metadata_line_clues'] = [
                        {'line': i+1, 'text': line[:220]}
                        for i,line in enumerate(prefix)
                        if line.strip() and any(c.isalpha() for c in line)
                        and not (line.count(',') >= 3 and any(c.isdigit() for c in line))
                    ][:28]
                    if m.filename.lower().endswith('.log'):
                        with z.open(m) as f:
                            nonblank = (line.decode('utf-8-sig',errors='replace').strip()
                                        for line in f if line.strip())
                            header = next(nonblank, '')
                            first_sample = next(nonblank, '')
                            last_sample = first_sample
                            for val in nonblank:
                                last_sample = val
                        row['electrical_header_columns'] = [q.strip() for q in header.split(',')]
                        row['first_electrical_time_token'] = first_sample.split(',')[0].strip()
                        row['last_electrical_time_token'] = last_sample.split(',')[0].strip()
            rows.append(row)
    cells = {}
    for cell,preload in CELL_PRELOAD_KN.items():
        these = [r for r in rows if r['cell_id_from_name_only'] == cell]
        cells[cell] = {'publisher_preload_kN': preload,'source_members':len(these),
                       'log_candidates':sum(x['candidate_role_from_name_only']=='charge_discharge_log_candidate' for x in these),
                       'sp_candidates':sum(x['candidate_role_from_name_only']=='thickness_sp_candidate' for x in these),
                       'candidate_archive_paths':[r['path'] for r in these],
                       'same_cell_electromechanical_timestamps_verified':False,
                       'matching_experiment_stage_verified':False,
                       'cross_cell_wrong_match_rate':None}
    return {'source_doi':DOI,'original_archive_bytes':len(data),
            'original_zip_sha256':hashlib.sha256(data).hexdigest(),
            'publisher_zip_md5_verified':True, 'zip_crc_verified':True,
            'archive_member_count':len(rows),'archive_uncompressed_bytes':total,
            'cells': cells, 'members':rows,
            'scope':'source original authentication and candidate file inventory only',
            'raw_charge_capacity_quantified':False,'physical_impact_test':False,
            'hardware_calibration_verified':False,'experiment_phase_join_verified':False,
            'measured_cell_to_cell_mismatch_rate':None}

def get_original() -> tuple[bytes,int]:
    url = f'https://zenodo.org/api/records/{RECORD}'
    req = urllib.request.Request(url,headers={'User-Agent':'CANO-battery-source-audit/1.0'})
    with urllib.request.urlopen(req, timeout=50) as response:
        meta = json.load(response)
    fs = [f for f in meta.get('files',[]) if f.get('key','').lower().endswith('.zip')]
    if len(fs) != 1:
        raise ValueError('expected exactly one publisher ZIP on Zenodo record')
    f = fs[0]
    if f.get('checksum') != 'md5:' + OFFICIAL_MD5:
        raise ValueError('Zenodo API source checksum conflicts with pinned official record')
    size = f.get('size')
    if not isinstance(size,int) or not 0 < size <= MAX_COMPRESSED:
        raise ValueError('publisher source size invalid')
    url = (f.get('links') or {}).get('content') or (f.get('links') or {}).get('self')
    if not url or not url.startswith('https://zenodo.org/'):
        # Official immutable record URL still fails safely on source mismatch.
        url=f'https://zenodo.org/records/{RECORD}/files/{urllib.parse.quote(f["key"])}?download=1'
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'CANO-battery-source-audit/1.0'}),timeout=120) as response:
        data = response.read(size+1)
    return data,size

def main():
    p=argparse.ArgumentParser(); p.add_argument('output',type=Path); a=p.parse_args()
    blob,size=get_original(); r=inspect_archive(blob,size)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2,ensure_ascii=False,sort_keys=True)+'\n',encoding='utf-8')
    print('GRAZ_REAL_PUBLISHER_ORIGINAL_PASS',r['original_archive_bytes'],r['archive_member_count'],r['original_zip_sha256'])
    for c in ('02','03'):
        print('CELL_SOURCE_CANDIDATES',c,r['cells'][c]['source_members'],r['cells'][c]['log_candidates'],r['cells'][c]['sp_candidates'])
    print('PHASE_JOIN_VERIFIED_FALSE; NO_CROSS_CELL_RATE_CLAIM')

if __name__ == '__main__':
    main()