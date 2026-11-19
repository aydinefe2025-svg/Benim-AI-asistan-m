#!/usr/bin/env python3
"""Offline customer-battery CSV preflight: duplicate and schema audit.

Reads only explicitly mapped local files; never uploads raw customer measurements.
Supports 2, 4 or 6 columns (1-3 independent timestamp/voltage pairs) with
trailing omitted pairs on later rows. Numerical and time checks are strict.
Exact equality compares original time/voltage TEXT; it cannot detect rounded,
resampled or near-duplicate curves. Not a certified safety or SOH tool.

Example manifest:
{"schema":"cano.battery.customer-files.v1","files":[
 {"path":"cell_A.csv","cell":"A","mode":"dchg"},
 {"path":"cell_B.csv","cell":"B","mode":"chg"}]}
Usage:
 python customer_preflight.py --manifest manifest.json --report report.json
 python customer_preflight.py --manifest manifest.json --report report.json --split holdout.json
"""
import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

SCHEMA = 'cano.battery.customer-files.v1'
MAX_FILE_BYTES = 30_000_000


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def csv_unit_signature(raw, label):
    """Never compare raw numeric text across incompatible declared units.

    All columns and all files must use one unambiguous time/voltage unit pair.
    No unit conversion is attempted: mixed units fail before hashing/splitting.
    """
    try:
        header = next(csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True))
    except (UnicodeError, StopIteration, csv.Error) as exc:
        raise ValueError(f'UNIT_REVIEW_REQUIRED: invalid CSV header {label}') from exc
    if len(header) not in (2, 4, 6):
        raise ValueError(f'UNIT_REVIEW_REQUIRED: header width {label}')
    signatures = set()
    for i in range(0, len(header), 2):
        mt = re.fullmatch(r'Timestamp(?:[_ -]?[A-Za-z0-9]+)?\s*\[(h|s|ms)\]', header[i].strip(), re.I)
        mv = re.fullmatch(r'(?:DC\d+|Voltage(?:[_ -]?\d+)?|V\d+|BATT_\d+_(?:DC|CC)\d+)\s*\[(V|mV)\]', header[i+1].strip(), re.I)
        if not mt or not mv:
            raise ValueError(f'UNIT_REVIEW_REQUIRED: missing/unknown units {label}')
        signatures.add((mt.group(1).lower(), mv.group(1).lower()))
    if len(signatures) != 1:
        raise ValueError(f'UNIT_REVIEW_REQUIRED: mixed units in file {label}')
    return next(iter(signatures))


def parse_csv(raw, label):
    try:
        stream = io.StringIO(raw.decode('utf-8-sig'), newline='')
    except UnicodeError as exc:
        raise ValueError(f'REVIEW_REQUIRED: UTF-8 encoding at {label}') from exc
    reader = csv.reader(stream, strict=True)
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError(f'REVIEW_REQUIRED: empty CSV {label}') from exc
    if len(header) not in (2, 4, 6):
        raise ValueError(f'REVIEW_REQUIRED: expected unique 2/4/6-column header at {label}')
    for i in range(0, len(header), 2):
        if 'timestamp' not in header[i].lower() or not ('voltage' in header[i+1].lower() or '[v]' in header[i+1].lower() or '[mv]' in header[i+1].lower()):
            raise ValueError(f'REVIEW_REQUIRED: timestamp/voltage schema {label}')
    traces = [[] for _ in range(len(header)//2)]
    last = [None] * len(traces)
    width_counts = defaultdict(int)
    rows = 0
    for rownum, row in enumerate(reader, 2):
        if not row:
            continue
        if len(row) > len(header) or len(row) % 2 or not len(row):
            raise ValueError(f'REVIEW_REQUIRED: invalid field count {label}:{rownum}')
        width_counts[len(row)] += 1
        rows += 1
        row += [''] * (len(header) - len(row))
        for ci in range(len(traces)):
            t, v = row[ci*2:ci*2+2]
            if not t and not v:
                continue
            if not t or not v:
                raise ValueError(f'REVIEW_REQUIRED: incomplete time-voltage pair {label}:{rownum}')
            try:
                tf, vf = float(t), float(v)
            except ValueError as exc:
                raise ValueError(f'REVIEW_REQUIRED: nonnumeric pair {label}:{rownum}') from exc
            if not math.isfinite(tf) or not math.isfinite(vf) or tf < 0 or vf < 0:
                raise ValueError(f'REVIEW_REQUIRED: non-finite or negative time/voltage {label}:{rownum}')
            if last[ci] is not None and tf <= last[ci]:
                raise ValueError(f'REVIEW_REQUIRED: nonincreasing time {label}:{rownum}')
            last[ci] = tf
            traces[ci].append((t, v))
    if not rows or any(len(t) < 2 for t in traces):
        raise ValueError(f'REVIEW_REQUIRED: each trace must contain at least two pairs at {label}')
    return traces, dict(width_counts), rows


def safe_path(root, value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('REVIEW_REQUIRED: invalid relative path')
    p = Path(value)
    if p.is_absolute() or any(x in ('..', '.') for x in p.parts):
        raise ValueError('REVIEW_REQUIRED: invalid relative path')
    root = root.resolve()
    dest = (root / p).resolve(strict=True)
    if not dest.is_relative_to(root) or not dest.is_file():
        raise ValueError('REVIEW_REQUIRED: path escapes root or is not a regular file')
    return dest


def audit_customer(manifest, root):
    root = Path(root)
    if not isinstance(manifest, dict) or manifest.get('schema') != SCHEMA:
        raise ValueError('REVIEW_REQUIRED: unsupported manifest schema')
    entries = manifest.get('files')
    if not isinstance(entries, list) or not entries or len(entries) > 1000:
        raise ValueError('REVIEW_REQUIRED: expected 1-1000 mapped CSV files')
    seen = set()
    curves = []
    widths = defaultdict(int)
    rows = 0
    pair_count = 0
    source_records = []
    next_run = defaultdict(int)
    batch_units = None
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'path', 'cell', 'mode'}:
            raise ValueError('REVIEW_REQUIRED: invalid file mapping fields')
        relative, cell, mode = entry['path'], entry['cell'], entry['mode']
        if not isinstance(cell, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', cell):
            raise ValueError('REVIEW_REQUIRED: invalid cell alias')
        if mode not in ('chg', 'dchg'):
            raise ValueError('REVIEW_REQUIRED: mode must be chg/dchg')
        path = safe_path(root, relative)
        if path in seen:
            raise ValueError('REVIEW_REQUIRED: duplicate path')
        seen.add(path)
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError('REVIEW_REQUIRED: file too large')
        raw = path.read_bytes()
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError('REVIEW_REQUIRED: file too large after read')
        units = csv_unit_signature(raw, relative)
        if batch_units is not None and units != batch_units:
            raise ValueError('UNIT_REVIEW_REQUIRED: mixed time/voltage units across files')
        batch_units = units
        parsed, row_widths, file_rows = parse_csv(raw, relative)
        rows += file_rows
        for width, amount in row_widths.items():
            widths[str(width)] += amount
        source_sha = sha256(raw)
        source_records.append({'file': relative, 'cell': cell, 'mode': mode,
                               'raw_sha256': source_sha, 'bytes': len(raw)})
        for pairs in parsed:
            next_run[(cell, mode)] += 1
            pair_count += len(pairs)
            digest = sha256(''.join(t+'\t'+v+'\n' for t, v in pairs).encode('utf-8'))
            curves.append({'cell': cell, 'mode': mode, 'run': next_run[(cell, mode)],
                           'n': len(pairs), 'trace_sha256': digest,
                           'source_sha256': source_sha})
    digest_map = defaultdict(list)
    for curve in curves:
        digest_map[curve['trace_sha256']].append(curve)
    duplicates = sorted((d for d in digest_map.values() if len(d) > 1),
                        key=lambda d: d[0]['trace_sha256'])
    cross_cell = any(len({c['cell'] for c in group}) > 1 for group in duplicates)
    return {
        'schema': 'cano.battery.customer-audit.v1',
        'source_files': len(entries), 'csv_data_rows': rows,
        'measured_time_voltage_pairs': pair_count,
        'trace_count': len(curves), 'unique_curve_count': len(digest_map),
        'width_counts': dict(sorted(widths.items())),
        'duplicate_groups': duplicates, 'all_curve_identity': curves,
        'sources': source_records,
        'unit_contract': {'time_unit': batch_units[0], 'voltage_unit': batch_units[1],
                          'policy': 'strict_uniform_units_no_implicit_conversion'},
        'review_status': 'REVIEW_REQUIRED' if cross_cell else 'NO_EXACT_CROSS_CELL_DUPLICATES',
        'limits': ['Exact text equality only; other duplicate and shared-batch dependence may remain.',
                   'Sensitive cell aliases and file names remain in local report; do not publish without consent.',
                   'Not an accredited test, battery-SOH estimate or commercial field validation.'],
    }


def generate_holdout(report):
    try:
        from independent_holdout import create_manifest, verify_manifest
    except ImportError as exc:
        raise RuntimeError('Place independent_holdout.py alongside customer_preflight.py') from exc
    manifest = create_manifest(report)
    verify_manifest(report, manifest)
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', type=Path, required=True)
    ap.add_argument('--root', type=Path)
    ap.add_argument('--report', type=Path, required=True)
    ap.add_argument('--split', type=Path)
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    root = args.root if args.root else args.manifest.resolve().parent
    result = audit_customer(manifest, root)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if args.split:
        split = generate_holdout(result)
        args.split.write_text(json.dumps(split, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print('PASS: no exact-curve or same-cell cross-split leakage')
    else:
        print(result['review_status'] + ': report only; no train/test split accepted')


if __name__ == '__main__':
    try:
        main()
    except (OSError, UnicodeError, ValueError, RuntimeError, csv.Error) as e:
        print('REVIEW_REQUIRED: ' + str(e), file=sys.stderr)
        sys.exit(2)
