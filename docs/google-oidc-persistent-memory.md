# Google login and persistent personal memory

The application supports optional Streamlit Google OIDC login and PostgreSQL-backed personal memory. Login and the database are deliberately opt-in: until both are provisioned, current deployment behavior remains unchanged. Do not enable these settings on the live service until the secret file, database role, backup, and CI checks are ready.

## Google OIDC setup

1. In Google Cloud Console, create an OAuth client of type **Web application**. Add the exact Render origin callback `https://YOUR-RENDER-SERVICE.onrender.com/oauth2callback` as an authorized redirect URI.
2. In Render, add a Secret File at `.streamlit/secrets.toml` using `.streamlit/secrets.toml.example` as a template. Enter the real client ID, client secret, and a generated random cookie secret in the Render dashboard only. Never put credentials in Git, logs, or chat.
3. Add `APP_AUTH_REQUIRED=true` to Render environment variables only after the secret file is installed and verified. Streamlit's native OIDC requires Streamlit 1.42 or newer; see [Streamlit authentication](https://docs.streamlit.io/develop/concepts/connections/authentication).

## PostgreSQL setup

Use a dedicated least-privilege database role and an existing managed PostgreSQL database. First, as the schema owner, create the table once:

```sql
CREATE TABLE IF NOT EXISTS private_memory_entries (
  owner_key TEXT NOT NULL,
  entry_id TEXT NOT NULL,
  payload JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_key, entry_id)
);
```

Grant that application role only `SELECT, INSERT, UPDATE, DELETE` on this table (and required schema usage). Configure its connection string as Render's `DATABASE_URL` secret. The web process does not run schema migrations or DDL. Enable persistent memory only alongside `APP_AUTH_REQUIRED=true`; the app intentionally fails closed if a database URL exists without authenticated identity.

## Data and rollout

The app derives an opaque owner key from the verified OIDC issuer and subject using the cookie secret; email is never used as an ownership key. Imported notes are upserted in one transaction and scoped by that owner key. Existing session-only SQLite research tasks are not migrated by this feature. Export user-controlled task data before any deployment that might replace ephemeral disk. No live data is copied or altered by this code change.

Roll out through a reviewed GitHub PR and a planned Render deploy after credentials and backups are ready. No paid action or deployment is performed by this change.
