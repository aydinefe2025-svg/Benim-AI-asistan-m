"""Read-only, explicit-source application backup preflight.

An AES-authenticated pg_dump of an empty *different* database is not an
application disaster-recovery backup. This optional operator profile refuses
an unpinned or unpopulated CANO source before any archive can be created.

This is inventory evidence only: it does NOT independently prove the deployed
app's environment mapping, a consistent transaction snapshot, or a restore.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess

COLONY_TABLES = (
    'private_colony_snapshots',
    'private_colony_snapshot_revisions',
    'organism_lab_records',
)
TASK_TABLES = (
    'agent_research_tasks',
    'agent_research_task_events',
    'agent_research_drafts',
    'cano_authorized_jobs',
    'cano_authorized_job_events',
)
MEMORY_TABLES = ('private_memory_entries',)
APP_SOURCE_PROFILES = {
    'colony': COLONY_TABLES,
    'tasks': TASK_TABLES,
    'memory': MEMORY_TABLES,
    'full': COLONY_TABLES + TASK_TABLES + MEMORY_TABLES,
}
_IDENT = re.compile(r'[a-z_][a-z0-9_]{0,62}\Z')
_HOST = re.compile(r'[a-z0-9][a-z0-9.-]{0,253}\Z')


def require_application_source(libpq_env: dict, profile: str, *,
                               expected_host: str, expected_database: str,
                               psql_bin: str = 'psql',
                               runner=subprocess.run,
                               attest_counts: bool = False) -> dict:
    """Refuse a source that lacks pinned host/db, schema or populated tables.

    All queries are constant catalog/EXISTS reads, never dynamic identifiers
    from the operator. No connection credentials or row contents are returned.
    """
    if profile not in APP_SOURCE_PROFILES:
        raise ValueError('Unknown application backup profile')
    if not isinstance(expected_host, str) or not _HOST.fullmatch(expected_host):
        raise ValueError('An explicit pinned source host is required')
    if not isinstance(expected_database, str) or not _IDENT.fullmatch(expected_database):
        raise ValueError('An explicit pinned source database is required')
    host = str(libpq_env.get('PGHOST', '')).casefold().rstrip('.')
    db = str(libpq_env.get('PGDATABASE', ''))
    if host != expected_host.casefold().rstrip('.') or db != expected_database:
        raise ValueError('Application backup source does not match pinned identity')

    exe = shutil.which(psql_bin)
    if not exe:
        raise ValueError('PostgreSQL psql client is unavailable')
    required = APP_SOURCE_PROFILES[profile]
    # Names below are fixed constants (not user-provided SQL). A missing table
    # makes the query fail closed. Checking one row only does not copy user data.
    populated = ' OR '.join(
        f'EXISTS (SELECT 1 FROM public."{table}" LIMIT 1)' for table in required
    )
    sql = (
        "SELECT current_database() || E'\\t' || "
        "(SELECT COALESCE(string_agg(c.relname, ',' ORDER BY c.relname), '') "
        "FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')) "
        "|| E'\\t' || "
        f"(CASE WHEN ({populated}) THEN '1' ELSE '0' END)"
    )
    # A service/credential file, app backup key, and unrelated secrets are not
    # inherited. Sensitive libpq credentials stay in the child environment.
    safe_env = {k: str(v) for k, v in libpq_env.items()
                if k.startswith('PG') or k in ('PATH','HOME','SystemRoot','SYSTEMROOT',
                                               'WINDIR','PATHEXT','COMSPEC', 'LANG')}
    try:
        process = runner(
            [exe, '-X', '--no-password', '-At', '-v', 'ON_ERROR_STOP=1', '-c', sql],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=safe_env, check=False, timeout=30,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        raise ValueError('Cannot verify application source inventory') from None
    if process.returncode != 0 or not isinstance(process.stdout, bytes) or len(process.stdout)>16384:
        raise ValueError('Cannot verify application source inventory')
    lines = process.stdout.decode('utf-8', errors='replace').strip().splitlines()
    if len(lines) != 1 or len(lines[0].split('\t')) != 3:
        raise ValueError('Cannot verify application source inventory')
    observed_db, observed_tables, nonempty = lines[0].split('\t')
    tables = observed_tables.split(',') if observed_tables else []
    if (observed_db != expected_database or not set(required).issubset(tables)
            or nonempty != '1'):
        raise ValueError('Cannot verify application source inventory')
    result = {
        'profile': profile,
        'required_tables_matched': len(required),
        'nonempty_table_verified': True,
        'source_host_pinned': True,
        'source_database_pinned': True,
        'scope': 'Read-only preflight only; live app binding and restored data not proven.',
    }
    if not attest_counts:
        return result
    # Fixed-profile names only. No user text or credentials enter SQL.
    expected_role = libpq_env.get('PGUSER', '')
    if not isinstance(expected_role, str) or not expected_role:
        raise ValueError('Pinned PostgreSQL source role is required')
    counts_sql = " || ',' || ".join(
        f'(SELECT COUNT(*)::text FROM public."{table}")' for table in required
    )
    inventory_sql = (
        "SELECT current_database() || E'\\t' || session_user || E'\\t' || "
        + counts_sql
    )
    try:
        inventory = runner(
            [exe, '-X', '--no-password', '-At', '-v', 'ON_ERROR_STOP=1',
             '-c', inventory_sql],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=safe_env, check=False, timeout=45,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        raise ValueError('Cannot verify source row-count inventory') from None
    raw = getattr(inventory, 'stdout', None)
    if (getattr(inventory, 'returncode', None) != 0 or
            not isinstance(raw, bytes) or len(raw) > 4096):
        raise ValueError('Cannot verify source row-count inventory')
    parts = raw.decode('utf-8', 'replace').strip().split('\\t')
    if (len(parts) != 3 or parts[0] != expected_database or
            parts[1] != expected_role):
        raise ValueError('Source database or role changed during preflight')
    numbers = parts[2].split(',')
    if (len(numbers) != len(required) or
            any(not re.fullmatch(r'[0-9]{1,18}', n) for n in numbers)):
        raise ValueError('Invalid source row-count inventory')
    table_counts = dict(zip(required, (int(n) for n in numbers)))
    if sum(table_counts.values()) < 1:
        raise ValueError('Application source has no data')
    source_key = '\\x00'.join((host, db, expected_role))
    result['source_preflight'] = {
        'source_id_sha256': hashlib.sha256(source_key.encode('utf-8')).hexdigest(),
        'application_profile': profile,
        'table_counts': table_counts,
        'expected_table_count': len(required),
        'read_only_catalog_and_count': True,
        'same_snapshot_as_dump_verified': False,
        'live_app_env_binding_verified': False,
        'isolated_restore_verified': False,
    }
    return result
