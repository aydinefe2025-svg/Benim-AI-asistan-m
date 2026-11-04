"""Exercise the existing PostgreSQL adapter with synthetic data only.

Never log the connection URL. Existing rows are neither deleted nor updated;
each invocation creates random test owners. This does not migrate live data.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.postgres_memory import PostgresMemoryStore


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run_checks(database_url):
    run_id = uuid.uuid4().hex
    owner = 'synthetic-growth-' + run_id
    other_owner = 'synthetic-other-' + run_id
    recovery_owner = 'synthetic-recovery-' + run_id
    entry = {'id': 'sample-' + run_id, 'text': "Synthetic O'Reilly record — δοκιμή"}
    store = PostgresMemoryStore(database_url)
    store.initialize()
    store.save(owner, entry)
    store.save(other_owner, {'id': entry['id'], 'text': 'Other synthetic owner'})
    require(store.list(owner) == [entry], 'Owner isolation failed')
    require(store.list(other_owner)[0]['text'] == 'Other synthetic owner', 'Other owner mismatch')
    reopened = PostgresMemoryStore(database_url)
    require(reopened.list(owner) == [entry], 'Fresh connection lost committed data')
    # A real transaction rollback must not retain the uncommitted insert.
    try:
        with store._connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    'INSERT INTO private_memory_entries(owner_key,entry_id,payload) VALUES (%s,%s,%s::jsonb)',
                    (owner, 'rollback-' + run_id, json.dumps({'id': 'rollback'})),
                )
                raise RuntimeError('Synthetic transaction abort')
    except RuntimeError:
        pass
    require(reopened.list(owner) == [entry], 'Rollback retained an uncommitted row')
    # Recover from a real local JSON export into a distinct synthetic owner.
    with tempfile.TemporaryDirectory() as folder:
        backup = Path(folder) / 'synthetic-memory.json'
        backup.write_text(json.dumps(reopened.list(owner), ensure_ascii=False), encoding='utf-8')
        for restored_entry in json.loads(backup.read_text(encoding='utf-8')):
            reopened.save(recovery_owner, restored_entry)
    require(reopened.list(recovery_owner) == [entry], 'Recovery content mismatch')
    require(reopened.list(owner) == [entry], 'Recovery changed original rows')
    return {
        'status': 'verified', 'run_id': run_id, 'synthetic_owner': owner,
        'write_read': True, 'owner_isolation': True, 'fresh_connection_read': True,
        'transaction_rollback': True, 'synthetic_export_recovery': True,
        'existing_records_deleted': False, 'production_data_migrated': False,
        'synthetic_records_retained': 3,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--secure-prompt', action='store_true',
                        help='Read the URL through a non-echoing terminal prompt')
    parser.add_argument('--env-name', default='DATABASE_URL')
    args = parser.parse_args()
    try:
        url = getpass.getpass('DATABASE_CONNECTION_READY> ') if args.secure_prompt else os.environ.get(args.env_name)
        if not url:
            print(json.dumps({'status': 'not_configured'}))
            return 2
        print(json.dumps(run_checks(url), sort_keys=True))
        return 0
    except Exception as exc:
        # Do not print provider exceptions: they can contain the URL/password.
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
