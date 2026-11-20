#!/usr/bin/env python3
"""Authenticate and inspect ONE source-author-hosted Stroebl battery CSV.

Not proof of identical bytes to the Figshare zip nor of cell independence.
Research only, no customer uploads or waveform export. Stdlib only.
"""
from __future__ import annotations
import csv
from hashlib import sha1, sha256
import io
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen

AUTHOR_REPO = 'fst2112/Multi-Stage-Lithium-Ion-Battery-Aging-Dataset-Analysis'
AUTHOR_COMMIT = '145ced182329bb7c1ca00b6b541189721226557e'
AUTHOR_PATH = 'data/Multi-Stage_Aging_Study_uncompressed/Stage_1/TP_z08_01/TP_z08_01_01_ET_T23.csv'
AUTHOR_BLOB_SHA1 = '296c18a9bf7d90af1cae7e82f5f82c870bb9c77f'
AUTHOR_RAW_BYTES = 23079267
SOURCE_URL = f'https://raw.githubusercontent.com/{AUTHOR_REPO}/{AUTHOR_COMMIT}/{AUTHOR_PATH}'
MAX_BYTES = AUTHOR_RAW_BYTES
MAX_ROWS = 1_000_000
TIME_EXPR = re.compile(r'^(\d+):([0-5]?\d):([0-5]?\d(?:\.\d+)?)$')
REQUIRED = ('run_time', 'c_vol', 'c_cur', 'step_type')


def git_blob_sha1(raw: bytes) -> str:
    return sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()


def parse_seconds(value: str) -> float:
    value = value.strip()
    match = TIME_EXPR.fullmatch(value)
    if match:
        hours, minutes, seconds = match.groups()
        result = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    else:
        result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 100_000_000:
        raise ValueError('SOURCE_REVIEW_REQUIRED: time must be a bounded finite nonnegative second value')
    return result


def inspect_csv(raw: bytes, *, expected_bytes: int = AUTHOR_RAW_BYTES,
                expected_blob: str = AUTHOR_BLOB_SHA1) -> dict:
    if not isinstance(raw, bytes) or len(raw) != expected_bytes or len(raw) > MAX_BYTES:
        raise ValueError('SOURCE_REVIEW_REQUIRED: source byte budget or exact size mismatch')
    if git_blob_sha1(raw) != expected_blob:
        raise ValueError('SOURCE_REVIEW_REQUIRED: source author git blob mismatch')
    try:
        decoded = raw.decode('iso-8859-1')
    except (UnicodeError, LookupError):
        raise ValueError('SOURCE_REVIEW_REQUIRED: unsupported author source encoding') from None
    if '\x00' in decoded:
        raise ValueError('SOURCE_REVIEW_REQUIRED: binary NUL in original CSV')
    reader = csv.DictReader(io.StringIO(decoded, newline=''), strict=True)
    header = reader.fieldnames
    if (not isinstance(header, list) or len(header) > 80 or
            any(not isinstance(x, str) or not x or len(x) > 100 for x in header) or
            len({x.strip().lower() for x in header}) != len(header)):
        raise ValueError('SOURCE_REVIEW_REQUIRED: invalid CSV columns')
    if any(k not in header for k in REQUIRED):
        raise ValueError('SOURCE_REVIEW_REQUIRED: missing measurement timestamp, voltage, current or step-type column')
    count = 0
    distinct_step = set()
    first_time = last_time = None
    n_time_decreases = 0
    n_time_equal = 0
    time_min = float('inf')
    time_max = float('-inf')
    v_min = float('inf')
    v_max = float('-inf')
    i_min = float('inf')
    i_max = float('-inf')
    continuous_segment = longest = 0
    prev_step = None
    for row in reader:
        count += 1
        if count > MAX_ROWS or None in row or any(k not in row or row[k] is None for k in REQUIRED):
            raise ValueError('SOURCE_REVIEW_REQUIRED: malformed or excessive sample rows')
        try:
            t = parse_seconds(row['run_time'])
            v = float(row['c_vol'])
            cur = float(row['c_cur'])
        except (ValueError, TypeError) as exc:
            raise ValueError('SOURCE_REVIEW_REQUIRED: unparseable time/voltage/current') from exc
        if not (math.isfinite(v) and math.isfinite(cur) and 0 <= v <= 6.0 and -30 <= cur <= 30):
            raise ValueError('SOURCE_REVIEW_REQUIRED: invalid numeric voltage/current units or values')
        step = row['step_type'].strip()
        if not step or len(step) > 40:
            raise ValueError('SOURCE_REVIEW_REQUIRED: missing/invalid step type')
        if last_time is not None:
            if t < last_time:
                n_time_decreases += 1
            elif t == last_time:
                n_time_equal += 1
        if last_time is not None and t > last_time and step == prev_step:
            continuous_segment += 1
        else:
            longest = max(longest, continuous_segment)
            continuous_segment = 1
        last_time, prev_step = t, step
        first_time = t if first_time is None else first_time
        distinct_step.add(step)
        time_min = min(time_min, t)
        time_max = max(time_max, t)
        v_min, v_max = min(v_min, v), max(v_max, v)
        i_min, i_max = min(i_min, cur), max(i_max, cur)
    longest = max(longest, continuous_segment)
    if count < 100:
        raise ValueError('SOURCE_REVIEW_REQUIRED: source too short for any screening')
    return {
        'schema':'cano.battery.stroebl.author-onecell-authenticated.v1',
        'source_status':'AUTHORS_GITHUB_ORIGINAL_GIT_BLOB_VERIFIED',
        'source_repo':AUTHOR_REPO,
        'author_commit':AUTHOR_COMMIT,
        'git_blob_sha1':expected_blob,
        'original_bytes':len(raw),
        'file_sha256':sha256(raw).hexdigest(),
        'source_stage_from_path':'Stage_1',
        'measurements_file_count':1,
        'full_time_voltage_sample_rows':count,
        'time_axis_name':'run_time',
        'time_axis_seconds_parser':'numeric_seconds_or_hh_mm_ss_to_seconds',
        'voltage_axis_name':'c_vol',
        'current_axis_name':'c_cur',
        'step_axis_name':'step_type',
        'time_min_s':round(time_min,6),
        'time_max_s':round(time_max,6),
        'time_decreasing_steps':n_time_decreases,
        'time_equal_steps':n_time_equal,
        'longest_consecutive_same_step_monotone_segment':longest,
        'distinct_step_types_count':len(distinct_step),
        'voltage_min_V':round(v_min,6),
        'voltage_max_V':round(v_max,6),
        'voltage_span_V':round(v_max-v_min,6),
        'current_min_A':round(i_min,6),
        'current_max_A':round(i_max,6),
        'source_publisher_figshare_byte_identity_verified':False,
        'physical_cell_independence_verified':False,
        'field_false_match_rate_measured':False,
        'reference_cell_id_link_to_279_row_original_metadata_verified':False,
        'commercial_product_certification':False,
        'decision':'ONE_SOURCE_AUTHOR_TIME_VOLTAGE_TRACE_CHECKED_ONLY',
        'limits':[
            'Author Git blob validates exact author-repository CSV bytes, not identical contents in publisher Figshare ZIP.',
            'File and path represent one laboratory trace; no independent cell-pair confusion rate can be computed.',
            'The published 279-row stage+serial metadata has not been joined to this author repository CSV.',
            'No calibration, instrument serial trust, independently verified technician, customer site or field acceptance.'
        ]
    }


def fetch_original_author_csv() -> bytes:
    with urlopen(Request(SOURCE_URL, headers={'User-Agent':'CANO-source-science/1.0','Accept':'text/csv'}), timeout=60) as resp:
        target = urlparse(resp.geturl())
        if resp.status != 200 or target.scheme != 'https' or target.hostname not in ('raw.githubusercontent.com', 'github.com'):
            raise ValueError('SOURCE_REVIEW_REQUIRED: unexpected source redirect or response')
        return resp.read(MAX_BYTES+1)


def main(argv=None) -> int:
    if argv is None: argv=sys.argv[1:]
    if len(argv) != 1:
        print('usage: author_onecell_original.py new-redacted-result.json',file=sys.stderr)
        return 2
    try:
        out=Path(argv[0])
        if out.exists() or out.is_symlink() or not out.parent.is_dir():
            raise ValueError('SOURCE_REVIEW_REQUIRED: refuse existing result or missing directory')
        result=inspect_csv(fetch_original_author_csv())
        with out.open('x',encoding='utf-8') as f:
            json.dump(result,f,ensure_ascii=False,indent=2,sort_keys=True)
            f.write('\n')
        print('VERIFIED_AUTHOR_SOURCE',json.dumps({'rows':result['full_time_voltage_sample_rows'],
             'voltage_span_V':result['voltage_span_V'],'decision':result['decision']}))
        return 0
    except (OSError,ValueError,csv.Error) as exc:
        print('SOURCE_REVIEW_REQUIRED: '+str(exc)[:180],file=sys.stderr)
        return 2

if __name__=='__main__': raise SystemExit(main())
