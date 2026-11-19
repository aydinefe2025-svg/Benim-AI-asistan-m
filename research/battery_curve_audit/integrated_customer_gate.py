#!/usr/bin/env python3
"""Offline single-entry battery data preflight; no raw customer-data transmission.

Unifies strict CSV units, byte-identical and Decimal-equivalent curve grouping,
near-curve *review candidates* (2 mV) and transitive cell-atomic holdout.
An approved split is never written on unresolved evidence or skipped screening.
A negative screen does NOT establish scientific/physical independence.
"""
import argparse
import json
import math
import os
import tempfile
from pathlib import Path
import sys

import customer_preflight as customer
import numeric_equivalence_guard as numeric_guard
import near_duplicate_guard as near_guard

SCHEMA = 'cano.battery.integrated-preflight.v1'
MAX_TRACES = 120
MAX_PAIRS = 1_000_000
TIME_TO_HOURS = {'h': 1.0, 's': 1 / 3600, 'ms': 1 / 3_600_000}
VOLTAGE_TO_VOLTS = {'v': 1.0, 'mv': .001}


def screen_numeric_report(numeric, manifest, root):
    """Check files were not altered after the numeric audit, then screen curves."""
    root = Path(root)
    sources = numeric.get('sources')
    derived = numeric.get('all_curve_identity')
    entries = manifest.get('files')
    if (not isinstance(sources, list) or not isinstance(derived, list)
            or not isinstance(entries, list) or len(sources) != len(entries)
            or len(derived) != numeric.get('trace_count')):
        raise ValueError('REVIEW_REQUIRED: incomplete numeric audit inputs')
    if len(derived) > MAX_TRACES or numeric.get('measured_time_voltage_pairs', MAX_PAIRS+1) > MAX_PAIRS:
        raise ValueError('REVIEW_REQUIRED: screening compute budget exceeded')
    units = numeric.get('unit_contract', {})
    time_factor = TIME_TO_HOURS.get(units.get('time_unit'))
    volt_factor = VOLTAGE_TO_VOLTS.get(units.get('voltage_unit'))
    if time_factor is None or volt_factor is None:
        raise ValueError('UNIT_REVIEW_REQUIRED: no explicit supported unit contract')
    traces = []
    source_i = 0
    trace_i = 0
    for entry, source in zip(entries, sources):
        path = customer.safe_path(root, entry['path'])
        if path.stat().st_size > customer.MAX_FILE_BYTES:
            raise ValueError('REVIEW_REQUIRED: file too large')
        raw = path.read_bytes()
        if (len(raw) > customer.MAX_FILE_BYTES or
                customer.sha256(raw) != source.get('raw_sha256')):
            raise ValueError('REVIEW_REQUIRED: source changed after numeric audit')
        parsed, _, _ = customer.parse_csv(raw, entry['path'])
        for pts in parsed:
            if trace_i >= len(derived):
                raise ValueError('REVIEW_REQUIRED: extra trace after audit')
            row = derived[trace_i]
            trace_i += 1
            if (row['cell'] != entry['cell'] or row['mode'] != entry['mode'] or
                    row['n'] != len(pts) or row.get('source_sha256') != source['raw_sha256'] or
                    numeric_guard.numeric_pair_hash(pts) != row['trace_sha256']):
                raise ValueError('REVIEW_REQUIRED: changed curve after numeric audit')
            traces.append({
                'cell': row['cell'], 'mode': row['mode'], 'run': row['run'],
                'n': row['n'], 'trace_sha256': row['trace_sha256'],
                'times': [float(t) * time_factor for t, _ in pts],
                'volts': [float(v) * volt_factor for _, v in pts],
            })
        source_i += 1
    if trace_i != len(derived):
        raise ValueError('REVIEW_REQUIRED: missing trace after numeric audit')
    insufficient = [
        {'cell': t['cell'], 'mode': t['mode'], 'run': t['run'],
         'reason': 'short_trace' if t['n'] < near_guard.DEFAULT_MIN_POINTS else 'flat_trace'}
        for t in traces if (t['n'] < near_guard.DEFAULT_MIN_POINTS or
                          max(t['volts']) - min(t['volts']) < near_guard.DEFAULT_MIN_VOLTAGE_RANGE_V)
    ]
    near = near_guard.candidates_for(traces)
    split = near_guard.propose_split(derived, near)
    if split is not None:
        near_guard.verify_split(derived, near, split)
    duplicated_cells = sum(1 for group in numeric['duplicate_groups']
                           if len({x['cell'] for x in group}) > 1)
    decision = ('BLOCK_INSUFFICIENT_GROUPS' if split is None else
                'REVIEW_REQUIRED' if duplicated_cells or near or insufficient else
                'PASS_SCREEN_ONLY')
    return {
        'schema': SCHEMA,
        'source_numeric_audit_sha256': numeric_guard.digest(numeric),
        'source_files': len(sources), 'trace_count': len(traces),
        'time_voltage_pairs': numeric['measured_time_voltage_pairs'],
        'unit_contract': units,
        'raw_unique': len({x['raw_trace_sha256'] for x in derived}),
        'numeric_unique': len({x['trace_sha256'] for x in derived}),
        'numeric_only_duplicate_groups': len(numeric['numeric_only_duplicate_groups']),
        'cross_cell_numeric_duplicate_groups': duplicated_cells,
        'near_candidate_count': len(near), 'near_candidates': near,
        'unscreened_trace_count': len(insufficient), 'unscreened_traces': insufficient,
        'split': split,
        'decision': decision,
        'limitations': [
            'Screen-only acceptance: not proof of physical/statistical independence.',
            'Near comparison: same-mode, 100+ points, 2mV and 0.5% endpoint threshold; flat curves unscreened.',
            'Cross-cell identical or near signals need independent technician review.',
            'Reports include sensitive aliases, filenames and hashes; no consent to publish.',
            'Not accredited battery health testing, SOH prediction or paid customer acceptance.',
        ],
    }


def integrated_check(manifest, root):
    numeric = numeric_guard.build_numeric_audit(manifest, root)
    return screen_numeric_report(numeric, manifest, root)


def verify_report(manifest, root, report):
    """Re-execute with original source bytes; no trust in self-asserted JSON flags."""
    if not isinstance(report, dict) or report.get('schema') != SCHEMA:
        raise ValueError('REVIEW_REQUIRED: report schema mismatch')
    expected = integrated_check(manifest, root)
    if report != expected:
        raise ValueError('REVIEW_REQUIRED: report/split evidence altered or source mismatch')
    return True


def validate_output_paths(manifest, root, manifest_path, report_path, split_path):
    """Never overwrite/delete input CSVs or the manifest, including symlink aliases."""
    if not isinstance(manifest, dict):
        raise ValueError('REVIEW_REQUIRED: manifest must be an object')
    entries = manifest.get('files')
    if not isinstance(entries, list) or any(not isinstance(item, dict) or
                                           not isinstance(item.get('path'), str) for item in entries):
        raise ValueError('REVIEW_REQUIRED: invalid file mapping')
    protected = {customer.safe_path(Path(root), item['path']) for item in entries}
    protected.add(Path(manifest_path).resolve())
    outputs = [Path(report_path).resolve()]
    if split_path is not None:
        outputs.append(Path(split_path).resolve())
    if len(set(outputs)) != len(outputs) or any(path in protected for path in outputs):
        raise ValueError('OUTPUT_REVIEW_REQUIRED: output path collides with customer source or another output')


def write_json(path, data):
    """Atomic write via exclusive unpredictable temporary name; do not clobber data."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.cano-battery-', suffix='.tmp',
                                         delete=False) as temp:
            tmp_name = Path(temp.name)
            temp.write(json.dumps(data, indent=2, ensure_ascii=False)+'\n')
        os.replace(tmp_name, path)
    finally:
        if tmp_name is not None:
            tmp_name.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--accepted-split', type=Path,
                        help='Only emit accepted train/validation/test split when NO review/block flags')
    parser.add_argument('--verify-report', type=Path, help='re-read local sources and compare prior report')
    args = parser.parse_args(argv)
    output_paths_validated = False
    try:
        manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
        root = args.root if args.root else args.manifest.resolve().parent
        validate_output_paths(manifest, root, args.manifest, args.report, args.accepted_split)
        output_paths_validated = True
        result = integrated_check(manifest, root)
        if args.verify_report:
            old = json.loads(args.verify_report.read_text(encoding='utf-8'))
            verify_report(manifest, root, old)
        write_json(args.report, result)
        if args.accepted_split:
            if result['decision'] != 'PASS_SCREEN_ONLY' or result['split'] is None:
                # Fail closed and avoid leaving an old accepted manifest on disk.
                args.accepted_split.unlink(missing_ok=True)
                print('REVIEW_REQUIRED: no accepted split; technician/source review required',file=sys.stderr)
                return 2
            write_json(args.accepted_split, result['split'])
        print(result['decision']+': numeric '+str(result['numeric_unique'])+
              '/'+str(result['trace_count'])+'; near candidates '+str(result['near_candidate_count'])+
              '; unscreened '+str(result['unscreened_trace_count']))
        return 0 if result['decision'] == 'PASS_SCREEN_ONLY' else 2
    except (OSError, UnicodeError, ValueError, RuntimeError, KeyError, TypeError, json.JSONDecodeError) as exc:
        if output_paths_validated and args.accepted_split:
            args.accepted_split.unlink(missing_ok=True)
        print('REVIEW_REQUIRED: '+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())
