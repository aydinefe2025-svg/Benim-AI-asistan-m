"""Bounded offline atomic findings/receipts with cross-process idempotence."""
import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path

import feedback_loop

MAX_BYTES = 2 * 1024 * 1024
MAX_LINES = 10000


def run(source, database, limit=1000, fault_after_finding=False):
    source = Path(source)
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_BYTES:
        raise ValueError('unsafe input')
    if not isinstance(limit, int) or not 1 <= limit <= MAX_LINES:
        raise ValueError('invalid limit')
    lines = source.read_bytes().splitlines()
    if len(lines) > MAX_LINES or any(len(line) > 65536 for line in lines):
        raise ValueError('input limits exceeded')
    db = Path(database)
    if db.is_symlink():
        raise ValueError('symlink database forbidden')
    conn = feedback_loop.connect(db)
    result = {'inserted': 0, 'duplicate': 0, 'rejected': 0,
              'already_processed': 0, 'deferred': 0}
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS receipts '
                     '(digest TEXT PRIMARY KEY, status TEXT NOT NULL, detail TEXT NOT NULL)')
        conn.execute('CREATE INDEX IF NOT EXISTS ix_receipts_detail_status ON receipts(detail,status)')
        conn.commit()
        for line in lines:
            if not line.strip():
                continue
            digest = hashlib.sha256(line).hexdigest()
            # Parse outside the lock: lock is held only for one bounded transaction.
            normalized, error = None, None
            try:
                normalized = feedback_loop.validate(json.loads(line))
            except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                error = str(exc)[:200]
            # BEGIN IMMEDIATE serializes the read-then-write receipt check across
            # independent worker processes; the previous SELECT-before-BEGIN raced.
            conn.execute('BEGIN IMMEDIATE')
            try:
                if conn.execute('SELECT 1 FROM receipts WHERE digest=?', (digest,)).fetchone():
                    status = 'already_processed'
                elif sum(result[k] for k in ('inserted', 'duplicate', 'rejected')) >= limit:
                    status = 'deferred'
                elif error is not None:
                    conn.execute('INSERT INTO receipts VALUES (?,?,?)', (digest, 'rejected', error))
                    status = 'rejected'
                else:
                    canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                    finding_hash = hashlib.sha256(canonical.encode()).hexdigest()
                    cur = conn.execute('INSERT OR IGNORE INTO findings VALUES(?,?,?,?,?,?,?)',
                                       (finding_hash, normalized['kind'], normalized['title'],
                                        normalized['source'], normalized['evidence'],
                                        'pending_review', int(time.time())))
                    if fault_after_finding:
                        raise RuntimeError('injected crash')
                    status = 'inserted' if cur.rowcount else 'duplicate'
                    conn.execute('INSERT INTO receipts VALUES (?,?,?)', (digest, status, finding_hash))
                conn.commit()
                result[status] += 1
            except BaseException:
                conn.rollback()
                raise
        result['all_processed'] = result['deferred'] == 0
        return result
    finally:
        conn.close()


def audit(database):
    db = Path(database)
    if not db.is_file() or db.is_symlink():
        return {'ok': False, 'checked': 0, 'errors': ['missing or unsafe database']}
    conn = sqlite3.connect('file:' + str(db.resolve()) + '?mode=ro', uri=True)
    try:
        errors, checked = [], 0
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            errors.append('database integrity')
        for status, detail in conn.execute('SELECT status,detail FROM receipts'):
            checked += 1
            if status not in ('inserted', 'duplicate', 'rejected'):
                errors.append('invalid receipt status')
            if status in ('inserted', 'duplicate'):
                row = conn.execute('SELECT kind,title,source,evidence FROM findings WHERE digest=?', (detail,)).fetchone()
                if row is None:
                    errors.append('orphan receipt')
                else:
                    canonical = json.dumps(dict(zip(('kind','title','source','evidence'), row)),
                                           ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                    if hashlib.sha256(canonical.encode()).hexdigest() != detail:
                        errors.append('tampered finding content')
        # Audit both directions: a finding without any matching successful receipt
        # used to go unnoticed and could inflate claimed research findings.
        for (digest,) in conn.execute('SELECT digest FROM findings'):
            if conn.execute("SELECT 1 FROM receipts WHERE detail=? AND status IN ('inserted','duplicate') LIMIT 1",
                            (digest,)).fetchone() is None:
                errors.append('orphan finding')
        if not checked:
            errors.append('empty receipts')
        return {'ok': not errors, 'checked': checked, 'errors': errors}
    except sqlite3.DatabaseError as exc:
        return {'ok': False, 'checked': 0, 'errors': [str(exc)[:120]]}
    finally:
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input')
    parser.add_argument('--db', default='atomic_findings.sqlite3')
    parser.add_argument('--limit', type=int, default=1000)
    args = parser.parse_args()
    result = run(args.input, args.db, args.limit)
    print(json.dumps(result))
    raise SystemExit(2 if result['rejected'] or result['deferred'] else 0)
