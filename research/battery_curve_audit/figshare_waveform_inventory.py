"""Source-only bounded multi-cell waveform file inventory, never downloads waveform bytes.

Scientific Data 2024, DOI 10.1038/s41597-024-03859-z; Figshare article 25975315.
The inventory is advisory: file names and publisher checksums do not prove physical-cell identity.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ARTICLE_ID = 25975315
URL = f"https://api.figshare.com/v2/articles/{ARTICLE_ID}"
EXPECTED_DOI = "10.6084/m9.figshare.25975315"
MAX_META_BYTES = 2_000_000
MAX_FILES = 5000
MAX_SINGLE_BYTES = 30_000_000_000
MAX_TOTAL_BYTES = 100_000_000_000
MAX_TRIAL_BYTES = 80_000_000


def analyze_inventory(meta: dict, *, trial_cap: int = MAX_TRIAL_BYTES) -> dict:
    if not isinstance(meta, dict) or meta.get('id') != ARTICLE_ID:
        raise ValueError('SOURCE_REVIEW_REQUIRED: article id')
    doi = str(meta.get('doi') or '').lower().strip()
    if not re.fullmatch(r'10\.6084/m9\.figshare\.25975315(?:\.v\d+)?', doi):
        raise ValueError('SOURCE_REVIEW_REQUIRED: wrong DOI')
    license_info = meta.get('license')
    if not isinstance(license_info, dict):
        raise ValueError('SOURCE_REVIEW_REQUIRED: missing license')
    name = str(license_info.get('name') or '').strip().lower().replace('-', ' ')
    uri = urlparse(str(license_info.get('url') or ''))
    if name not in {'cc by 4.0', 'creative commons attribution 4.0 international',
                    'attribution 4.0 international', 'attribution 4.0'} or (
            uri.scheme != 'https' or uri.hostname != 'creativecommons.org'
            or uri.path.rstrip('/').lower() != '/licenses/by/4.0'):
        raise ValueError('SOURCE_REVIEW_REQUIRED: license not verified')
    files = meta.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError('SOURCE_REVIEW_REQUIRED: file list')
    if isinstance(trial_cap, bool) or not isinstance(trial_cap, int) or not 1 <= trial_cap <= MAX_TRIAL_BYTES:
        raise ValueError('SOURCE_REVIEW_REQUIRED: trial budget')
    seen, candidates, all_sizes, count_by_ext = set(), [], [], Counter()
    total = 0
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError('SOURCE_REVIEW_REQUIRED: invalid entry')
        fid, filename, size = entry.get('id'), entry.get('name'), entry.get('size')
        if isinstance(fid, bool) or not isinstance(fid, int) or fid <= 0 or fid in seen:
            raise ValueError('SOURCE_REVIEW_REQUIRED: duplicate/bad file id')
        if not isinstance(filename, str) or not 1 <= len(filename) <= 200 or (
                '/' in filename or '\\' in filename or '..' in filename or '\x00' in filename):
            raise ValueError('SOURCE_REVIEW_REQUIRED: unsafe source filename')
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_SINGLE_BYTES:
            raise ValueError('SOURCE_REVIEW_REQUIRED: invalid size')
        seen.add(fid)
        total += size
        if total > MAX_TOTAL_BYTES:
            raise ValueError('SOURCE_REVIEW_REQUIRED: aggregate byte budget')
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else '(none)'
        count_by_ext[ext] += 1
        if ext not in {'zip', '7z', 'tar', 'gz', 'csv'} or size == 0:
            continue
        all_sizes.append(size)
        digest = entry.get('computed_md5') or entry.get('supplied_md5')
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-fA-F]{32}', digest):
            continue
        if size > trial_cap:
            continue
        candidates.append({'file_id': fid, 'size_bytes': size, 'publisher_md5': digest.lower(),
                           'file_ext': ext, 'filename': filename})
    candidates.sort(key=lambda x:(x['size_bytes'],x['file_id']))
    all_sizes.sort()
    min_size=all_sizes[0] if all_sizes else None
    return {'schema':'cano.battery.figshare25975315.waveform-inventory.v1',
            'publisher_article_id': ARTICLE_ID, 'publisher_doi':doi,
            'license':'CC_BY_4_0_PUBLISHER_METADATA',
            'publisher_file_count':len(files),'publisher_listed_total_bytes':total,
            'types_count':dict(sorted(count_by_ext.items())),
            'potential_signal_archive_file_count':len(all_sizes),
            'smallest_potential_signal_file_bytes':min_size,
            'bounded_archive_candidates_count':len(candidates),
            'trial_file_byte_cap':trial_cap,
            'bounded_candidates_first_20':candidates[:20],
            'original_waveform_files_downloaded':0,
            'measurement_time_unit_verified':False,
            'waveform_cell_id_link_verified':False,
            'independent_physical_cells_verified':0,
            'field_false_match_rate_established':False,
            'production_release_allowed':False,
            'decision': ('CANDIDATES_FOUND_METADATA_ONLY' if candidates else
                         'NO_CANDIDATE_WITHIN_BUDGET_METADATA_ONLY')}


def fetch_inventory() -> dict:
    req=Request(URL,headers={'Accept':'application/json','User-Agent':'CANO-battery-bounded-inventory/1.0'})
    with urlopen(req,timeout=30) as resp:
        uri=urlparse(resp.geturl())
        if resp.status != 200 or uri.scheme != 'https' or uri.hostname != 'api.figshare.com':
            raise ValueError('SOURCE_REVIEW_REQUIRED: publisher host')
        raw=resp.read(MAX_META_BYTES+1)
    if not 2 <= len(raw) <= MAX_META_BYTES:
        raise ValueError('SOURCE_REVIEW_REQUIRED: metadata byte budget')
    meta=json.loads(raw)
    receipt=analyze_inventory(meta)
    receipt['publisher_metadata_sha256']=sha256(raw).hexdigest()
    return receipt


def main(argv=None) -> int:
    import sys
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print('usage: figshare_waveform_inventory.py output.json',file=sys.stderr)
        return 2
    try:
        dest=Path(args[0])
        if dest.exists() or not dest.parent.is_dir():
            raise ValueError('SOURCE_REVIEW_REQUIRED: output exists/missing directory')
        result=fetch_inventory()
        with dest.open('x',encoding='utf-8') as f:
            json.dump(result,f,indent=2,sort_keys=True)
            f.write('\n')
        print('INVENTORY_METADATA_ONLY',json.dumps({'count':result['bounded_archive_candidates_count'],
                  'smallest':result['smallest_potential_signal_file_bytes'],
                  'decision':result['decision']}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
        print('SOURCE_REVIEW_REQUIRED',str(e)[:180],file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())