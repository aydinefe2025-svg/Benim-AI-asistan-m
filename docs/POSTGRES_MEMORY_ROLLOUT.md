# PostgreSQL persistence: verified development foundation

Updated 2026-11-03. The existing adapter from
`feat/postgres-research-store-20261103` is preserved in `core/postgres_memory.py`.
It is not yet wired into the public Streamlit UI and does not migrate SQLite.

## Provisioned and tested

- Existing Neon organization remains on the Free plan; no upgrade or paid add-on.
- Project: `benim-ai-persistence` (`sweet-sound-73776160`).
- Branch: `development` (`br-flat-sky-b95bk71x`), PostgreSQL 17.
- Region: `aws-eu-central-1` (Frankfurt), matching the Render region.
- Compute: fixed 0.25 CU. After testing it was explicitly suspended; API state
  is `idle`, disabled=false. Storage and synthetic records were retained.
- Driver: psycopg 3.3.7, pinned in `requirements-persistence.txt`.
- Real driver checks passed: write/read with Unicode and quotes, owner filtering,
  fresh connection read, rollback, synthetic JSON export/recovery without
  changing original records. A separate connector read after the Python process
  exited and another read after a compute restart both found the committed row.
- Only three labeled synthetic records from the smoke run were retained.
  Existing application data was not uploaded, deleted or migrated.

This proves the development adapter and database path. It does not prove public
user authentication, a production migration, full-database recovery or an SLA.

## Safe local verification

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-persistence.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe scripts/check_postgres_persistence.py --secure-prompt
```

The last command reads a connection URL through a non-echoing prompt. Obtain it
privately from the provider console or approved secret storage; never paste it
into chat, a command argument, a PR, logs or a tracked file. An injected
`DATABASE_URL` is also supported. Use a direct connection for schema work; pooled
connections are appropriate for future application traffic.

The smoke run inserts synthetic owners with random IDs; it never invokes delete
or overwrites a pre-existing owner. Runtime checks remain active with Python -O.
Errors expose only an exception class, not provider text or credentials.

## Production rollout gates

1. Authenticate users and derive an owner key on the trusted server side.
   A caller-supplied, constant or guessable owner key is not authorization.
2. Provision a dedicated application role with only the required permissions.
   The owner connection used for development verification is not the proposed
   browser-facing credential. Never expose a database URL to the browser.
3. Obtain and verify the existing Render SQLite/session export before any
   deployment that may replace its ephemeral disk. Local backups do not cover
   the live Render filesystem.
4. Reconcile records and fingerprints in a separate migration target, test
   recovery there, and preserve the source. Do not migrate on application import.
5. Enable the durable store explicitly behind the application's storage factory
   only after these checks. Preserve the current export/import fallback.
6. Monitor storage/compute/transfer allowances. Stay on Free unless the user
   explicitly authorizes a paid plan; do not enable chargeable services or
   assume unlimited capacity. Retain independent private backups.

No Render environment variables or live deployment were changed by this work.
The free development database is a tested foundation for the next migration.

Official references: https://neon.com/docs/introduction/plans and
https://neon.com/docs/connect/connection-pooling
