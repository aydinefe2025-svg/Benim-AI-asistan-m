#!/usr/bin/env python3
"""One-command, offline laboratory CSV/source-receipt cross-check.

Never certifies field independence. Joins EXISTING strict CSV intake to the
EXISTING raw-source + exact audit receipt binder, without invented validators.
All identifying data stay local; default output is counts only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import customer_preflight as customer
import field_pilot_csv_intake as intake
import field_receipt_binding as binding


def run_bound(manifest_path, root, audit_path, cells_path, reviews_path, frame_path,
              summary_path, private_ledger_path=None):
    """Refuse missing/changed inputs; create only NEW private-safe outputs."""
    manifest_path = Path(manifest_path)
    root = Path(root)
    audit_path = Path(audit_path)
    cells_path = Path(cells_path)
    reviews_path = Path(reviews_path)
    frame_path = Path(frame_path)
    summary_path = Path(summary_path)
    if (manifest_path.stat().st_size > binding.MAX_MANIFEST_BYTES or
            audit_path.stat().st_size > binding.MAX_REPORT_BYTES):
        raise ValueError('REVIEW_REQUIRED: manifest or audit report exceeds safety budget')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), list):
        raise ValueError('REVIEW_REQUIRED: malformed customer source manifest')
    # Compute the entire protect-from-overwrite set before processing. This
    # includes all raw source CSVs; no accidentally reusing a source pathname.
    protected = [manifest_path, audit_path, cells_path, reviews_path, frame_path]
    for item in manifest['files']:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str):
            raise ValueError('REVIEW_REQUIRED: malformed source path mapping')
        protected.append(customer.safe_path(root, item['path']))
    # The one canonical CSV converter performs exact header/width checks, and
    # its existing adjudication rejects unknown and contradictory reviewers.
    _field_aggregate, ledger = intake.evaluate(cells_path, reviews_path, frame_path)
    # The existing binding engine independently verifies SHA of the *exact*
    # audit JSON bytes, re-reads every raw time/voltage CSV, and checks every
    # declared cell partition against the audited transitive grouped split.
    result = binding.bind_pilot(manifest, root, audit_path.read_bytes(), ledger)
    intake.save(result, summary_path,
                private=ledger if private_ledger_path is not None else None,
                private_path=private_ledger_path,
                inputs=protected)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--root', type=Path, help='Root with authorized raw CSV inputs')
    p.add_argument('--audit-report', type=Path, required=True,
                   help='Original strict integrated audit report, exact bytes')
    p.add_argument('--cells', type=Path, required=True)
    p.add_argument('--reviews', type=Path, required=True)
    p.add_argument('--frame', type=Path, required=True)
    p.add_argument('--summary', type=Path, required=True)
    p.add_argument('--private-ledger', type=Path,
                   help='Opt-in: save identifiers, reviewer IDs and site references locally')
    args = p.parse_args(argv)
    try:
        root = args.root if args.root is not None else args.manifest.resolve().parent
        r = run_bound(args.manifest, root, args.audit_report, args.cells,
                      args.reviews, args.frame, args.summary, args.private_ledger)
        print(f"{r['decision']}: source reverified, partitions bound; "
              "field acceptance NOT_ESTABLISHED")
        return 0 if r['decision'] == 'PILOT_ONLY_NOT_CERTIFIED' else 2
    except (ValueError, KeyError, TypeError, RuntimeError, OSError, UnicodeError,
            json.JSONDecodeError) as exc:
        print('REVIEW_REQUIRED: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
