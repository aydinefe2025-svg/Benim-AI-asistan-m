# PostgreSQL persistent memory: integrated, production rollout gated

Updated 2026-11-03 after PR #71. The adapter in `core/postgres_memory.py`
is wired into the Streamlit UI for explicit personal-memory notes. Google OIDC
creates an opaque, owner-scoped identity for those records. This feature remains
opt-in until private Render secrets and a least-privilege production database
role are configured. Existing SQLite research tasks are not migrated.

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

This proves the development adapter and database path. GitHub CI also passed the
OIDC/authentication, PostgreSQL adapter, core, and research checks on PR #71.
It does not prove a live Google login, a production database connection, full
database recovery, or an SLA. The public app is still on the prior deployment
because Render auto-deploy is disabled.

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

1. **Google OIDC:** the login gate is implemented but not activated. Configure
   `.streamlit/secrets.toml` as a Render Secret File with the Google Web OAuth
   client, a strong random cookie secret, the exact Render callback URL, and
   Google's metadata URL. Only then set `APP_AUTH_REQUIRED=true`. Never put
   these values in Git, chat, or logs.
2. **Production PostgreSQL:** use a dedicated role with only schema usage and
   SELECT/INSERT/UPDATE/DELETE on `private_memory_entries`. Create the table as
   the schema owner before configuring the app's `DATABASE_URL`; the app does
   not run DDL or migrations. The app deliberately stops if `DATABASE_URL` is
   present without required authenticated identity.
3. **Existing user data:** research tasks and history remain in per-session
   SQLite and are not moved by this feature. Export the live Render data through
   the app's supported export before a deployment that may replace ephemeral
   storage. Local snapshots do not back up Render's filesystem.
4. **Recovery and migration:** test restoration using a separate target and
   preserve the source. Do not import existing data automatically on app start.
   Personal-memory JSON export/import remains available as a user-controlled
   fallback.
5. **Cost and monitoring:** remain on Free unless the user explicitly approves a
   paid plan. Monitor storage, compute, and transfer allowances and keep an
   independent private backup.

As of this update, Render environment variables and the live deployment were
not changed. The development Neon branch remains suspended after testing.
The implementation is traceable in [PR #71](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/71).

Official references: https://neon.com/docs/introduction/plans and
https://neon.com/docs/connect/connection-pooling
