# Google login and persistent personal memory

The application supports optional Streamlit Google OIDC login and PostgreSQL-backed personal memory. Both features are opt-in. Do not enable the login gate on the live service until the Google client is configured, the Secret File is installed, and existing user-controlled task data has been backed up and verified.

## Google OIDC setup

1. In Google Cloud Console, create an OAuth client of type **Web application**. Add this exact authorized redirect URI: `https://benim-ai-asistan-streamlit.onrender.com/oauth2callback`.
2. In Render, create a Secret File at `.streamlit/secrets.toml` using `.streamlit/secrets.toml.example` as the template. Put the real client ID, client secret, a long random cookie secret, and a separate generated `owner_key_secret` in Render's dashboard only. Never put credentials in Git, logs, or chat. Back up `owner_key_secret` securely and keep it stable: changing it makes existing personal memory inaccessible until owner keys are migrated.
3. Verify the Secret File is installed before setting `APP_AUTH_REQUIRED=true` in Render. That setting activates a login gate for the whole app. Streamlit's native OIDC requires Streamlit 1.42 or newer; see [Streamlit authentication](https://docs.streamlit.io/develop/concepts/connections/authentication).

The app reads Google OIDC settings from the `[auth]` section in `.streamlit/secrets.toml`; standalone `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` environment variables are not used by this implementation. Google login does not require `DATABASE_URL`. Do not start a Google Cloud free trial for this setup.

## PostgreSQL setup

PostgreSQL is a separate, optional feature for persistent personal-memory notes. Use a dedicated least-privilege database role and an existing managed PostgreSQL database. First, as the schema owner, create the table once:

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

The app derives an opaque owner key from the verified OIDC issuer and subject using the separate, stable `owner_key_secret`; rotating the login cookie secret does not orphan stored memories. Email is never used as an ownership key. Imported notes are upserted in one transaction and scoped by that owner key. Existing session-only SQLite research tasks are not migrated by this feature. Export user-controlled task data before any deployment or auth rollout that could affect access to existing data. No live data is copied or altered by this code change.

Roll out through a reviewed GitHub change and a planned Render deploy after credentials and backups are ready. No paid action or deployment is performed by this change.
