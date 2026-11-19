#!/usr/bin/env python3
"""Offline, privacy-minimizing customer-battery audit in one command.

Runs the existing strict CSV/unit parser, Decimal numeric equivalence, and
conservative same-mode near-curve review, then validates a connected-cell
holdout. Raw readings remain local. A public summary contains only counts;
requesting a private split is explicit and remains NOT_CERTIFIED.

No battery-health prediction, accredited measurement, or physical independence
claim. Dependencies: Python 3 standard library and sibling audit modules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys

import customer_preflight as customer
import numeric_equivalence_guard as numeric
import near_duplicate_guard as near

SCHEMA = 'cano.battery.customer-local-pipeline.v1'
MAX_TRACES = 120
MAX_PAIRS = 1_000_000


def audit_offline(manifest, root, *, max_traces=MAX_TRACES, max_pairs=MAX_PAIRS):
    """In-memory only. The returned private manifest contains customer IDs."""
    if not isinstance(max_traces, int) or isinstance(max_traces, bool) or not 3 <= max_traces <= MAX_TRACES:
        raise ValueError('REVIEW_REQUIRED: invalid trace budget')
    if not isinstance(max_pairs, int) or isinstance(max_pairs, bool) or not 3 <= max_pairs <= MAX_PAIRS:
        raise ValueError('REVIEW_REQUIRED: invalid pair budget')
    root = Path(root)
    audited = numeric.build_numeric_audit(manifest, root)
    traces = audited['all_curve_identity']
    if len(traces) > max_traces:
        raise ValueError('REVIEW_REQUIRED: trace budget exceeded; batch must be reviewed')
    if audited['measured_time_voltage_pairs'] > max_pairs:
        raise ValueError('REVIEW_REQUIRED: pair budget exceeded; batch must be reviewed')
    units = audited['unit_contract']
    if units['voltage_unit'] not in ('v', 'mv') or units['time_unit'] not in ('h', 's', 'ms'):
        raise ValueError('UNIT_REVIEW_REQUIRED: unsupported physical units')
    scale_v = 0.001 if units['voltage_unit'] == 'mv' else 1.0
    seen = {}
    for row in traces:
        key = (row['cell'], row['mode'], row['run'])
        if key in seen:
            raise ValueError('REVIEW_REQUIRED: duplicate trace identity')
        seen[key] = row
    next_run = {}
    physical_traces = []
    for entry, source in zip(manifest['files'], audited['sources']):
        filename = customer.safe_path(root, entry['path'])
        raw = filename.read_bytes()
        if (len(raw) > customer.MAX_FILE_BYTES or
                hashlib.sha256(raw).hexdigest() != source['raw_sha256']):
            raise ValueError('REVIEW_REQUIRED: source CSV changed during analysis')
        if customer.csv_unit_signature(raw, entry['path']) != (
                units['time_unit'], units['voltage_unit']):
            raise ValueError('UNIT_REVIEW_REQUIRED: source units changed during analysis')
        parsed, _, _ = customer.parse_csv(raw, entry['path'])
        key = (entry['cell'], entry['mode'])
        for points in parsed:
            next_run[key] = next_run.get(key, 0) + 1
            run = next_run[key]
            row = seen.get((entry['cell'], entry['mode'], run))
            if (row is None or row['trace_sha256'] != numeric.numeric_pair_hash(points)
                    or row['source_sha256'] != source['raw_sha256']):
                raise ValueError('REVIEW_REQUIRED: numeric trace/source identity changed')
            times = [float(t) for t, _ in points]
            volts = [float(v) * scale_v for _, v in points]
            if any(not math.isfinite(v) for v in volts + times):
                raise ValueError('REVIEW_REQUIRED: invalid physical reading')
            physical_traces.append({
                'cell': entry['cell'], 'mode': entry['mode'], 'run': run,
                'n': len(points), 'times': times, 'volts': volts,
                'trace_sha256': row['trace_sha256'],
            })
    if len(physical_traces) != len(traces):
        raise ValueError('REVIEW_REQUIRED: trace count changed during analysis')
    # compare_near skips flat or short traces by design. Do not silently
    # reinterpret a skipped screen as evidence of no near-duplicate leakage.
    unscreened = [t for t in physical_traces
                  if (t['n'] < near.DEFAULT_MIN_POINTS or
                      max(t['volts'])-min(t['volts']) < near.DEFAULT_MIN_VOLTAGE_RANGE_V)]
    absolute_candidates = near.candidates_for(physical_traces)
    origin_candidates = near.relative_time_origin_candidates(physical_traces, absolute_candidates)
    candidates = absolute_candidates + origin_candidates
    split = near.propose_split(traces, candidates)
    if split is not None:
        near.verify_split(traces, candidates, split)
    cross_numeric_groups = sum(
        len({item['cell'] for item in group}) > 1
        for group in audited['duplicate_groups']
    )
    groups = near.components(traces, candidates)
    if split is None:
        decision = 'BLOCK_INSUFFICIENT_GROUPS'
    elif cross_numeric_groups or candidates or unscreened:
        decision = 'REVIEW_REQUIRED'
    else:
        decision = 'SCREEN_ONLY_NO_CROSS_CELL_CANDIDATES'
    summary = {
        'schema': SCHEMA,
        'decision': decision,
        'source_files': audited['source_files'],
        'trace_count': audited['trace_count'],
        'sample_pairs': audited['measured_time_voltage_pairs'],
        'unit_contract': units,
        'numeric_unique_traces': audited['unique_curve_count'],
        'numeric_only_duplicate_groups': len(audited['numeric_only_duplicate_groups']),
        'cross_cell_numeric_duplicate_groups': cross_numeric_groups,
        'near_candidates': len(candidates),
        'time_origin_near_candidates': len(origin_candidates),
        'unscreened_traces': len(unscreened),
        'independent_groups': len(groups),
        'holdout_possible': split is not None,
        'near_screen_threshold_mv': near.DEFAULT_TOLERANCE_MV,
        'near_screen_endpoint_fraction': near.DEFAULT_ENDPOINT_FRACTION,
        'near_screen_min_points': near.DEFAULT_MIN_POINTS,
        'private_identifiers_in_public_summary': False,
        'limitations': [
            'SCREEN_ONLY is not certification of statistical or physical independence.',
            'Near matches are review candidates, not proof of copying or fraud.',
            'Traces with fewer than 100 samples or voltage span below 0.05 V were not near-screened; human review required.',
            'Thresholds are not calibrated on real independent customer labels.',
            'Only constant time-origin shifts are screened additionally; time warping, >2 mV bias and noisy clones may be missed.',
            'Shared batches, changed time grids, derived feature leakage, SOH and field performance not validated.',
            'Private split contains cell aliases and hashes; disclose only with customer permission.',
        ],
    }
    private = None if split is None else {
        'status': 'NOT_CERTIFIED',
        'sensitivity': 'CUSTOMER_IDENTIFIERS_AND_HASHES',
        'split': split,
        'by_cell': {row['cell']: row['partition'] for row in split['assignments']},
        'review_required': decision != 'SCREEN_ONLY_NO_CROSS_CELL_CANDIDATES',
    }
    return summary, private


def save_reports(summary, private, report, private_output=None, *, source_paths=()):
    """Exclusive, restrictive creation; refuse to replace customer inputs.

    Any failure rolls back files created in this call. No files are modified.
    """
    report = Path(report)
    destinations = [report]
    payloads = [summary]
    if private_output is not None:
        if private is None:
            raise ValueError('REVIEW_REQUIRED: private split unavailable')
        destinations.append(Path(private_output))
        payloads.append(private)
    resolved = [p.resolve(strict=False) for p in destinations]
    forbidden = {Path(p).resolve(strict=False) for p in source_paths}
    if len(set(resolved)) != len(resolved) or any(p in forbidden for p in resolved):
        raise ValueError('REVIEW_REQUIRED: report destination collides with customer source/output')
    for p in destinations:
        if p.exists() or p.is_symlink():
            raise ValueError('REVIEW_REQUIRED: existing output would be overwritten')
        if not p.parent.is_dir():
            raise ValueError('REVIEW_REQUIRED: output parent directory does not exist')
    created = []
    try:
        for path, obj in zip(destinations, payloads):
            raw = (json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(fd, 'wb') as out:
                out.write(raw)
                out.flush()
                os.fsync(out.fileno())
    except Exception:
        for p in created:
            p.unlink(missing_ok=True)
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', type=Path, required=True,
                    help='Explicit mapping of local customer CSVs to cell IDs and mode')
    ap.add_argument('--root', type=Path, help='Root directory containing local authorized CSVs')
    ap.add_argument('--summary', type=Path, required=True, help='Aggregates only, no identifiers')
    ap.add_argument('--private-split', type=Path, help='Explicit opt-in; customer-sensitive split')
    ap.add_argument('--report-only', action='store_true',
                    help='Exit 0 on REVIEW_REQUIRED, only to view the report; no model acceptance')
    args = ap.parse_args(argv)
    try:
        if args.report_only and args.private_split is not None:
            raise ValueError('REVIEW_REQUIRED: --report-only cannot create private split')
        manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
        root = args.root if args.root else args.manifest.parent
        summary, private = audit_offline(manifest, root)
        inputs = [customer.safe_path(Path(root), item['path']) for item in manifest['files']]
        inputs.append(args.manifest.resolve())
        save_reports(summary, private, args.summary, args.private_split, source_paths=inputs)
        print(f"{summary['decision']}: traces={summary['trace_count']}; "
              f"numeric duplicate groups={summary['cross_cell_numeric_duplicate_groups']}; "
              f"near candidates={summary['near_candidates']}; independent groups={summary['independent_groups']}")
        return 0 if summary['decision'] == 'SCREEN_ONLY_NO_CROSS_CELL_CANDIDATES' or args.report_only else 2
    except (ValueError, TypeError, KeyError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print('REVIEW_REQUIRED: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
