# Google login and persistent personal memory

The live Render app now requires Google OIDC login. PostgreSQL-backed personal memory and persistent task storage remain separate, opt-in features; neither is configured by this login setup.

## Google OIDC setup

1. In Google Cloud Console, create an OAuth client of type **Web application**. Add this exact authorized redirect URI: `https://benim-ai-asistan-streamlit.onrender.com/oauth2callback`.
2. In Render, upload the contents of `.streamlit/secrets.toml.example` as a Secret File named `secrets.toml`. Render filenames cannot contain directory separators. The tracked `.streamlit/config.toml` tells Streamlit to read `/etc/secrets/secrets.toml` or a root-level `secrets.toml`; local development can continue to use `.streamlit/secrets.toml`.
3. Put the real client ID, client secret, and separate long random values for `cookie_secret` and `owner_key_secret` in Render's dashboard only. Never put credentials in Git, logs, or chat; keep `owner_key_secret` stable when rotating the cookie secret.
4. `APP_AUTH_REQUIRED=true` is enabled on the live Render service. The app fails closed if the OIDC secret file is missing or incomplete. Streamlit native OIDC needs Streamlit 1.42 or newer and Authlib 1.3.2 or newer; see [Streamlit authentication](https://docs.streamlit.io/develop/concepts/connections/authentication).

The app reads Google OIDC settings from the `[auth]` section in the configured secrets file; standalone `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` environment variables are not used by this implementation. Google login does not require `DATABASE_URL`. No Google Cloud free trial is required.

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

The app derives an opaque owner key from the verified OIDC issuer and subject using the separate stable `owner_key_secret`; email is never used as an ownership key. Imported notes are upserted in one transaction and scoped by that owner key. Existing session-only SQLite research tasks are not migrated by this feature. Export user-controlled task data before any future persistence or auth changes that could affect access to existing data. No live data was copied or altered by the OAuth setup.

For persistent task records, configure a separate `AGENT_TASK_DATABASE_URL`; do not reuse `DATABASE_URL`, which is reserved for personal memory. On first start the app creates owner-scoped `agent_research_*` tables, so the role must own the tables or have schema create privileges. Every task, draft, and event query is scoped to the authenticated owner key. Existing SQLite task data is not migrated. Set this URL only after `APP_AUTH_REQUIRED=true` and the OIDC Secret File are verified.
