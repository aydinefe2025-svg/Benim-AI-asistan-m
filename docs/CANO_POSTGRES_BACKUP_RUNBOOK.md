# CANO PostgreSQL backup and isolated restore runbook

**Status:** An operator-only disaster-recovery utility; NOT an automatic production backup,
NOT a completed Render database backup and NOT proof of restored production data.

## Preconditions

- Install PostgreSQL client utilities `pg_dump`, `pg_restore` and `psql` at versions compatible with the PostgreSQL server.
- Execute on a trusted host that can connect to the database. Do not weaken the Render database firewall to run this tool.
- Keep secrets in the process environment, never in commands, repository, Notion or GitHub Actions logs.
- Keep backup archives in private encrypted storage. The archive and manifest are not safe to publish.
- Provide a destination inside a restricted directory. The tool refuses to overwrite an existing archive or manifest.

## Create and check a backup

Provide the connection string from a trusted local secret manager or already configured process environment:

```sh
python -m scripts.cano_pg_backup_manifest backup /secure/cano-2026-11-04.dump
python -m scripts.cano_pg_backup_manifest verify /secure/cano-2026-11-04.dump
```

The environment variable `CANO_BACKUP_DATABASE_URL` is required for the first command.
The utility parses the URL into libpq environment variables such as `PGHOST`,
`PGDATABASE`, and `PGPASSWORD`. `PGDATABASE` contains only the decoded database
name. Credentials stay out of command arguments and logs. Remote connections
require TLS. For a production export, configure `sslmode=verify-full` with the
appropriate CA on the trusted backup host.

The utility writes a custom-format PostgreSQL archive and a SHA-256 manifest.
An integrity and pg_restore catalog check succeeds before publication. No automatic
GitHub artifact upload, Notion upload, or third-party sync is performed.

## Isolated restore test

1. Provision a **separate empty database**, with a name ending in `_cano_restore_test`. Do not reuse a populated staging or application database even if it ends in that suffix.
2. Set `CANO_RESTORE_TEST_DATABASE_URL` to that test database's private connection URL.
3. Run:

```sh
python -m scripts.cano_pg_backup_manifest restore-test /secure/cano-2026-11-04.dump
```

Before running the write-capable `pg_restore`, the tool uses read-only `psql`
catalog queries against the chosen target to reject nonempty user schemas,
relations, routines and user-defined types. An unavailable `psql` client,
unreadable catalog or any nonzero/non-numeric result **aborts the restore**.
The target URL is parsed into sanitized libpq environment variables;
only a strictly validated, ordinary database name is passed as `pg_restore --dbname`.
PostgreSQL requires `--dbname` for a direct database restore; without it,
`PGDATABASE` alone does not select a restore destination. No passwords or
entire connection URL go into subprocess command arguments.
This check does not eliminate the time-of-check/time-of-use race if another
writer modifies the target after preflight: arrange exclusive access to the
isolated destination while testing recovery.

The tool refuses a production database URL or a target without the isolated suffix,
and never issues `--clean` or `--create`. A successful `pg_restore` process is
recorded as `restore_command_succeeded`, **not** as production recovery
or independently verified row-level readback. Inspect table contents and compare
source/restore counts before closing a recovery drill.

## Tested recovery scope

[PR #191](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/191)
adds PostgreSQL 18 synthetic backup and restore coverage alongside PostgreSQL 17.
Production acceptance still requires a trusted host with database access, a
private encrypted destination, and an isolated restore with record readback.
Keep only the sanitized acceptance result and checksum in the operations log.

## Scope and remaining work

This backs up the **single selected PostgreSQL database**, not browser localStorage,
ephemeral SQLite, a second database with another URL, or GitHub/Notion research data.
Real scheduled off-site encrypted backups, owner login, credentials/access validation,
independently inspected row readback, and the Render free PostgreSQL expiration risk
must be addressed separately. No credentials or actual user data are present in tests.
