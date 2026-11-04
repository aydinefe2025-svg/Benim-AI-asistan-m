"""Strict offline intake of curated, provenance-bearing source records.

No network access, no execution of source content, no automatic acceptance.
"""
from contextlib import closing
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from feedback_loop import connect, ingest

MAX_SOURCE_BYTES = 256 * 1024
MAX_RECORDS = 100
ALLOWED_HOSTS = {'doi.org', 'zenodo.org', 'arxiv.org', 'www.nature.com', 'github.com'}
ALLOWED_FIELDS = {'title', 'url', 'summary', 'published', 'source_sha256'}

def normalize_url(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 33 for c in url):
        raise ValueError('invalid URL')
    u = urlsplit(url)
    if (u.scheme != 'https' or u.hostname not in ALLOWED_HOSTS or u.username or u.password
            or u.port not in (None, 443) or not u.path or u.fragment):
        raise ValueError('URL not on HTTPS source allowlist')
    return url

def validate_record(record):
    if not isinstance(record, dict) or set(record) != ALLOWED_FIELDS:
        raise ValueError('unexpected or missing record fields')
    url = normalize_url(record['url'])
    for key, limit in (('title', 160), ('summary', 3000), ('published', 32)):
        value = record[key]
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError('invalid ' + key)
    if not isinstance(record['source_sha256'], str) or len(record['source_sha256']) != 64 or any(c not in '0123456789abcdef' for c in record['source_sha256']):
        raise ValueError('source_sha256 must be a lowercase SHA-256 digest')
    return {'kind': 'observation', 'title': record['title'], 'source': url,
            'evidence': json.dumps({'summary':record['summary'], 'published':record['published'],
                                    'source_sha256':record['source_sha256']}, ensure_ascii=False, sort_keys=True)}

def import_records(db, records):
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_RECORDS:
        raise ValueError('expected 1-100 records')
    # Validate all records before writing anything.
    items = [validate_record(r) for r in records]
    results = [ingest(db, item) for item in items]
    return {'received':len(items), 'inserted':sum(x['inserted'] for x in results),
            'duplicates':sum(not x['inserted'] for x in results), 'status':'pending_review',
            'warning':'Source metadata and digest are supplied claims, not independently verified'}

def import_file(db, path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError('safe input JSON file <=256KiB required')
    return import_records(db, json.loads(path.read_text(encoding='utf-8')))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('file', type=Path)
    a=p.parse_args()
    with closing(connect()) as db:
        print(json.dumps(import_file(db,a.file),indent=2))

if __name__ == '__main__':
    main()