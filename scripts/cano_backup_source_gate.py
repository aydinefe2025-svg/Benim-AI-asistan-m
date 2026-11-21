"""Read-only, explicit-source application backup preflight.

An AES-authenticated pg_dump of an empty *different* database is not an
application disaster-recovery backup. This optional operator profile refuses
an unpinned or unpopulated CANO source before any archive can be created.

This is inventory evidence only: it does NOT independently prove the deployed
app's environment mapping, a consistent transaction snapshot, or a restore.
"""
from __future__ import annotations

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

# Strict P0 source inventory: all current public tables plus nine historical
# recovery tables. Do not silently treat the earlier nine-table 'full' profile
# as proof of complete 19-table disaster recovery.
P0_HISTORY_SCHEMA = 'cano_p0_neon_recovery_20261115'
P0_TABLES = (
    tuple(('public', x) for x in APP_SOURCE_PROFILES['full'])
    + (('public', 'cano_code_jobs'),)
    + tuple((P0_HISTORY_SCHEMA, x) for x in APP_SOURCE_PROFILES['full'])
)
assert len(P0_TABLES) == 19

_IDENT = re.compile(r'[a-z_][a-z0-9_]{0,62}\Z')
_HOST = re.compile(r'[a-z0-9][a-z0-9.-]{0,253}\Z')


def require_application_source(libpq_env: dict, profile: str, *,
                               expected_host: str, expected_database: str,
                               psql_bin: str = 'psql',
                               runner=subprocess.run,
                               expected_total_rows: str | int | None = None) -> dict:
    """Refuse a source that lacks pinned host/db, schema or populated tables.

    All queries are constant catalog/EXISTS reads, never dynamic identifiers
    from the operator. No connection credentials or row contents are returned.
    """
    if profile not in APP_SOURCE_PROFILES and profile != 'p0_19':
        raise ValueError('Unknown application backup profile')
    if not isinstance(expected_host, str) or not _HOST.fullmatch(expected_host):
        raise ValueError('An explicit pinned source host is required')
    if not isinstance(expected_database, str) or not _IDENT.fullmatch(expected_database):
        raise ValueError('An explicit pinned source database is required')
    host = str(libpq_env.get('PGHOST', '')).casefold().rstrip('.')
    db = str(libpq_env.get('PGDATABASE', ''))
    if host != expected_host.casefold().rstrip('.') or db != expected_database:
        raise ValueError('Application backup source does not match pinned identity')

    if profile == 'p0_19':
        # Explicit inventory pinned by the operator; no implicit live count
        # can silently certify a truncated or wrong-source backup.
        if isinstance(expected_total_rows, bool):
            raise ValueError('A positive expected P0 row count is required')
        raw_count = str(expected_total_rows) if expected_total_rows is not None else ''
        if (not re.fullmatch(r'[1-9][0-9]{0,17}', raw_count)
                or int(raw_count) > 9223372036854775807):
            raise ValueError('A positive expected P0 row count is required')
        pinned_rows = int(raw_count)

    exe = shutil.which(psql_bin)
    if not exe:
        raise ValueError('PostgreSQL psql client is unavailable')

    if profile == 'p0_19':
        # All identifiers below come from fixed source code, never from a
        # user supplied SQL string. If any table is missing, SQL fails.
        unions = ' UNION ALL '.join(
            f'SELECT count(*)::bigint AS n FROM "{schema}"."{table}"'
            for schema, table in P0_TABLES
        )
        # Guard against an unexpected extra table in either schema.
        sql = (
            "SELECT current_database() || E'\\t' || "
            "(SELECT COUNT(*)::text FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace ns ON ns.oid = c.relnamespace "
            f"WHERE ns.nspname IN ('public','{P0_HISTORY_SCHEMA}') "
            "AND c.relkind IN ('r','p')) "
            "|| E'\\t' || "
            f"(SELECT SUM(n)::text FROM ({unions}) AS counts)"
        )
    else:
        required = APP_SOURCE_PROFILES[profile]
        # A missing table makes the query fail closed. Checking one row only
        # does not copy user data.
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
    if profile == 'p0_19':
        if (observed_db != expected_database or observed_tables != '19'
                or nonempty != str(pinned_rows)):
            raise ValueError('Cannot verify application source inventory')
        return {
            'profile': profile,
            'required_tables_matched': len(P0_TABLES),
            'expected_total_rows': pinned_rows,
            'row_count_verified': True,
            'source_host_pinned': True,
            'source_database_pinned': True,
            'scope': 'Read-only P0 preflight; live app binding, dump snapshot and restore not proven.',
        }
    tables = observed_tables.split(',') if observed_tables else []
    if (observed_db != expected_database or not set(required).issubset(tables)
            or nonempty != '1'):
        raise ValueError('Cannot verify application source inventory')
    return {
        'profile': profile,
        'required_tables_matched': len(required),
        'nonempty_table_verified': True,
        'source_host_pinned': True,
        'source_database_pinned': True,
        'scope': 'Read-only preflight only; live app binding and restored data not proven.',
    }
