#!/usr/bin/env python3
"""Offline numeric-equivalence guard for customer battery curves.

An **additional** conservative equality screen: numeric Decimal values match even
if exported as 3.4, 3.400 or 34e-1. This is distinct from calibrated near-curve
screening. No interpolation, tolerance, or proof of physical copied samples.

The original customer's raw-text identity and source SHA-256 remain in the
JSON evidence; existing independent_holdout.py accepts the derived numeric
trace hash for transitive cell grouping. No raw measurement pairs are exported.
"""
import argparse
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sys

import customer_preflight as original

SCHEMA = 'cano.battery.customer-numeric-audit.v1'


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def normalized_decimal(text):
    """Exact numeric identity with zero normalized; never round to float.

    Produces a compact coefficient/exponent pair, preserving every significant
    decimal digit without applying the global decimal arithmetic precision.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > 256:
        raise ValueError('REVIEW_REQUIRED: missing or oversized numeric field')
    try:
        number = Decimal(text.strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('REVIEW_REQUIRED: invalid decimal field') from exc
    if not number.is_finite():
        raise ValueError('REVIEW_REQUIRED: non-finite decimal field')
    if number.is_zero():
        return '0'
    sign, digits, exp = number.as_tuple()
    coefficient = ''.join(map(str, digits)).lstrip('0')
    # Remove insignificant trailing zeroes without Decimal.normalize rounding.
    trailing = len(coefficient) - len(coefficient.rstrip('0'))
    if trailing:
        coefficient = coefficient[:-trailing]
        exp += trailing
    return ('-' if sign else '') + coefficient + 'e' + str(exp)


def numeric_pair_hash(pairs):
    h = hashlib.sha256()
    for t, v in pairs:
        h.update((normalized_decimal(t) + '\t' + normalized_decimal(v) + '\n').encode('utf-8'))
    return h.hexdigest()


def build_numeric_audit(manifest, root):
    """Reverify customer SHA inputs and generate a *separate* numeric report."""
    root = Path(root)
    baseline = original.audit_customer(manifest, root)
    if len(baseline['sources']) != len(manifest['files']):
        raise ValueError('REVIEW_REQUIRED: source count mismatch')
    derived = []
    pos = 0
    for entry, source in zip(manifest['files'], baseline['sources']):
        filename = original.safe_path(root, entry['path'])
        raw = filename.read_bytes()
        if len(raw) > original.MAX_FILE_BYTES or original.sha256(raw) != source['raw_sha256']:
            raise ValueError('REVIEW_REQUIRED: source changed during audit')
        traces, _, _ = original.parse_csv(raw, entry['path'])
        for trace in traces:
            if pos >= len(baseline['all_curve_identity']):
                raise ValueError('REVIEW_REQUIRED: trace count changed')
            row = dict(baseline['all_curve_identity'][pos])
            pos += 1
            original_text_hash = original.sha256(''.join(t+'\t'+v+'\n' for t,v in trace).encode('utf-8'))
            if (row['trace_sha256'] != original_text_hash or
                    row['source_sha256'] != source['raw_sha256']):
                raise ValueError('REVIEW_REQUIRED: inconsistent original trace hashes')
            row['raw_trace_sha256'] = original_text_hash
            row['trace_sha256'] = numeric_pair_hash(trace)
            derived.append(row)
    if pos != len(baseline['all_curve_identity']):
        raise ValueError('REVIEW_REQUIRED: trace count changed')
    groups = defaultdict(list)
    for row in derived:
        groups[row['trace_sha256']].append(row)
    duplicates = sorted((v for v in groups.values() if len(v)>1),
                        key=lambda r:r[0]['trace_sha256'])
    only_numeric = [g for g in duplicates if len({r['raw_trace_sha256'] for r in g})>1]
    cross_cell = any(len({r['cell'] for r in g})>1 for g in duplicates)
    result = dict(baseline)
    result.update({
        'schema': SCHEMA,
        'original_text_audit_sha256': digest(baseline),
        'identity_method': 'exact Decimal coefficient/exponent; no numeric tolerance',
        'trace_count': len(derived),
        'all_curve_identity': derived,
        'unique_curve_count': len(groups),
        'duplicate_groups': duplicates,
        'numeric_only_duplicate_groups': only_numeric,
        'review_status': 'REVIEW_REQUIRED' if cross_cell else 'SCREEN_ONLY_NO_NUMERIC_CROSS_CELL_DUPLICATES',
        'limits': [
            'Numeric equality is not proof of fabricated data or independent measurements.',
            'No cross-time-grid, rounded-value, resampled or near-duplicate equivalence is inferred.',
            'Cell identifiers, filenames and content hashes in reports are customer-sensitive.',
            'No field/customer, battery SOH, lab calibration or commercial success claim.',
        ]
    })
    return result


def generate_holdout(numeric_report):
    from independent_holdout import create_manifest, verify_manifest
    split = create_manifest(numeric_report)
    verify_manifest(numeric_report, split)
    return split


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--holdout', type=Path)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    root = args.root if args.root else args.manifest.resolve().parent
    audit = build_numeric_audit(manifest, root)
    split = generate_holdout(audit) if args.holdout else None
    # Reject accidental replacement of customer source data.
    source_files = {original.safe_path(Path(root), x['path']) for x in manifest['files']}
    output_paths = [args.report] + ([args.holdout] if args.holdout else [])
    resolved = [p.resolve() for p in output_paths]
    if len(set(resolved)) != len(resolved) or any(p in source_files for p in resolved):
        raise ValueError('REVIEW_REQUIRED: output path collides with customer source or another output')
    for path, data in zip(output_paths, (audit, split)):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"{audit['review_status']}: numeric unique={audit['unique_curve_count']}/"
          f"{audit['trace_count']} numeric-only groups={len(audit['numeric_only_duplicate_groups'])}; "
          f"holdout={'verified' if split else 'NOT_RUN'}")
    return 0


if __name__=='__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, json.JSONDecodeError) as e:
        print('REVIEW_REQUIRED: ' + str(e), file=sys.stderr)
        sys.exit(2)
