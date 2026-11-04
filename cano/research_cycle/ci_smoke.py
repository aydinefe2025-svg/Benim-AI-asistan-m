"""Strict end-to-end smoke check for local / GitHub CI, with no network operations."""
import argparse
import json
import pathlib
import sys

import atomic_batch
import cano_real_cycle


def check(output: pathlib.Path) -> dict:
    first = cano_real_cycle.run_cycle(output)
    if first['total_samples'] != 1975 or first['finding_count'] != 1977:
        raise AssertionError('unexpected dataset count')
    proof = cano_real_cycle.verify_cycle(output)
    if not proof['ok'] or proof['checked_findings'] != 1977:
        raise AssertionError('first verification failed')
    replay = cano_real_cycle.run_cycle(output)
    if replay['ingestion']['inserted'] != 0 or replay['ingestion']['already_processed'] != 1977:
        raise AssertionError('replay/idempotence failed')
    verified = cano_real_cycle.verify_cycle(output)
    audit = atomic_batch.audit(output / 'findings.sqlite3')
    if not verified['ok'] or not audit['ok'] or audit['checked'] != 1977:
        raise AssertionError('final evidence audit failed')
    return {
        'ok': True, 'total_samples': 1975, 'findings': 1977,
        'first_inserted': first['ingestion']['inserted'],
        'replay_inserted': replay['ingestion']['inserted'],
        'replay_skipped': replay['ingestion']['already_processed'],
        'audit': audit, 'manifest': str(output / 'manifest.json'),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.output), indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())