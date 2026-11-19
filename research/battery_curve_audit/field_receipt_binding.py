#!/usr/bin/env python3
"""Bind an offline laboratory field ledger to re-verified time/voltage sources.

This is a linkage/provenance check, NOT scientific or customer-site acceptance.
The field ledger's self-asserted human approvals remain unverified. All readings
and private IDs stay on the user's local disk; only aggregates are released.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys

import customer_preflight as customer
import field_pilot_evidence as field
import integrated_customer_gate as gate

SCHEMA = 'cano.battery.bound-field-pilot.v1'
MAX_REPORT_BYTES = 2_000_000
MAX_MANIFEST_BYTES = 1_000_000


def bind_pilot(manifest, root, report_bytes, ledger):
    """Re-run the complete source gate; require ledger==source split for each cell."""
    if not isinstance(report_bytes, bytes) or not (1 <= len(report_bytes) <= MAX_REPORT_BYTES):
        raise ValueError('REVIEW_REQUIRED: audit report size/format invalid')
    if not isinstance(ledger, dict):
        raise ValueError('REVIEW_REQUIRED: field ledger missing')
    receipt = ledger.get('audit_receipt_sha256')
    if not isinstance(receipt, str) or len(receipt) != 64 or any(c not in '0123456789abcdef' for c in receipt):
        raise ValueError('REVIEW_REQUIRED: audit receipt invalid')
    if not hmac.compare_digest(hashlib.sha256(report_bytes).hexdigest(), receipt):
        raise ValueError('REVIEW_REQUIRED: ledger audit receipt mismatch')
    try:
        report = json.loads(report_bytes.decode('utf-8'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('REVIEW_REQUIRED: malformed audit report') from exc
    if not gate.verify_report(manifest, root, report):
        raise ValueError('REVIEW_REQUIRED: audit source mismatch')
    split = report.get('split')
    if not isinstance(split, dict) or not isinstance(split.get('assignments'), list):
        raise ValueError('REVIEW_REQUIRED: no candidate split to bind')
    source_assignment = {}
    for item in split['assignments']:
        if not isinstance(item, dict) or not isinstance(item.get('cell'), str):
            raise ValueError('REVIEW_REQUIRED: invalid split assignment')
        cell, partition = item['cell'], item.get('partition')
        if cell in source_assignment and source_assignment[cell] != partition:
            raise ValueError('REVIEW_REQUIRED: split not atomic by cell')
        source_assignment[cell] = partition
    if not source_assignment:
        raise ValueError('REVIEW_REQUIRED: no split assignments')
    ledger_cells = ledger.get('cells')
    ledger_assignments = ledger.get('assignments')
    if not isinstance(ledger_cells, list) or not isinstance(ledger_assignments, list):
        raise ValueError('REVIEW_REQUIRED: field cell/split metadata unavailable')
    cell_names = [x.get('cell') if isinstance(x, dict) else None for x in ledger_cells]
    if len(cell_names) != len(set(cell_names)) or set(cell_names) != set(source_assignment):
        raise ValueError('REVIEW_REQUIRED: field cell roster differs from verified source')
    seen = set()
    for item in ledger_assignments:
        if not isinstance(item, dict) or set(item) != {'cell', 'partition'}:
            raise ValueError('REVIEW_REQUIRED: invalid field partition row')
        cell = item['cell']
        if cell in seen or source_assignment.get(cell) != item['partition']:
            raise ValueError('REVIEW_REQUIRED: field partition differs from source audit')
        seen.add(cell)
    if seen != set(source_assignment):
        raise ValueError('REVIEW_REQUIRED: missing field partition assignment')
    field_report = field.assess(ledger)
    if report.get('decision') != 'PASS_SCREEN_ONLY':
        decision = 'BLOCK_AUDIT_REVIEW'
    elif field_report['decision'].startswith('BLOCK_'):
        decision = field_report['decision']
    else:
        decision = 'PILOT_ONLY_NOT_CERTIFIED'
    # Field aggregate is already designed to exclude identifying strings. Do not
    # transmit receipt hashes, source CSV paths, cell names, reviewer IDs or data.
    return {
        'schema': SCHEMA,
        'decision': decision,
        'field_acceptance': 'NOT_ESTABLISHED',
        'source_screen_decision': report['decision'],
        'source_recalculated_and_matched': True,
        'receipt_and_partitions_bound': True,
        'source_trace_count': report['trace_count'],
        'source_time_voltage_pairs': report['time_voltage_pairs'],
        'source_unscreened_count': report['unscreened_trace_count'],
        'source_cross_cell_numeric_groups': report['cross_cell_numeric_duplicate_groups'],
        'source_near_candidates': report['near_candidate_count'],
        'field_counts': {
            k: v for k, v in field_report.items()
            if k not in {'schema', 'decision', 'field_acceptance', 'limitations'}
        },
        'limits': [
            'This verifies SHA binding, exact declared cell partitions and present source data, not a human signature.',
            'The field ledger device, batch, campaign and technician annotations are self-asserted.',
            'A screen-only result does not prove physical independence; source REVIEW_REQUIRED never passes.',
            'Rates are observed adjudicated-pair summaries, not calibrated population errors or SOH accuracy.',
            'No customer-site acceptance, accreditation or commercial outcome is established.',
        ],
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--root',type=Path)
    p.add_argument('--audit-report',type=Path,required=True)
    p.add_argument('--ledger',type=Path,required=True)
    p.add_argument('--summary',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        root=args.root if args.root else args.manifest.resolve().parent
        if args.manifest.stat().st_size>MAX_MANIFEST_BYTES:
            raise ValueError('REVIEW_REQUIRED: manifest too large')
        if args.ledger.stat().st_size>field.MAX_BYTES:
            raise ValueError('REVIEW_REQUIRED: field ledger too large')
        if args.audit_report.stat().st_size>MAX_REPORT_BYTES:
            raise ValueError('REVIEW_REQUIRED: audit report too large')
        manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
        if not isinstance(manifest,dict) or not isinstance(manifest.get('files'),list):
            raise ValueError('REVIEW_REQUIRED: invalid customer manifest')
        sources={customer.safe_path(Path(root),item['path']) for item in manifest['files']}
        sources.update({args.manifest.resolve(strict=True),args.ledger.resolve(strict=True),
                        args.audit_report.resolve(strict=True)})
        out=args.summary
        if out.exists() or out.is_symlink() or out.resolve(strict=False) in sources:
            raise ValueError('REVIEW_REQUIRED: refuse to overwrite existing input/output')
        if not out.parent.is_dir():
            raise ValueError('REVIEW_REQUIRED: output parent directory unavailable')
        ledger=json.loads(args.ledger.read_text(encoding='utf-8'))
        summary=bind_pilot(manifest,root,args.audit_report.read_bytes(),ledger)
        payload=(json.dumps(summary,indent=2,ensure_ascii=False,sort_keys=True)+'\n').encode('utf-8')
        fd=os.open(out,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        try:
            with os.fdopen(fd,'wb') as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            out.unlink(missing_ok=True)
            raise
        print(summary['decision']+': source/ledger partitions bound; field acceptance NOT_ESTABLISHED')
        return 0 if summary['decision']=='PILOT_ONLY_NOT_CERTIFIED' else 2
    except (OSError,UnicodeError,ValueError,RuntimeError,KeyError,TypeError,json.JSONDecodeError) as exc:
        print('REVIEW_REQUIRED: '+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())
