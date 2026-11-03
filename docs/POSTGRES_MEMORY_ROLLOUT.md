# PostgreSQL persistence adapter: deployment checklist

The adapter in `core/postgres_memory.py` is **not yet wired into the Streamlit UI**.
It deliberately does not create a database or migrate existing session data.

1. Provision a database in the same region as Render web service.
2. Configure `DATABASE_URL` as a **secret** from the database's **internal**
   connection URL. Never commit it, paste it into Notion, or expose it in UI.
3. Install a compatible `psycopg[binary]` dependency in the deployment environment.
4. From inside the deployed service, call `PostgresMemoryStore().initialize()`
   and test save/list/delete with disposable entries scoped to a non-guessable
   authenticated owner key. A constant owner key is **not** safe for multi-user apps.
5. Check database data after a service restart; test a backup and restoration
   into a separate database before enabling production writes.
6. Migrate session JSON memories only after explicit backup and record-count
   reconciliation. Do not overwrite existing user data.
7. Render's free PostgreSQL instance has an expiry date. Move to a durable
   provider before expiry and schedule backups; do not treat it as permanent.

**Important:** GitHub CI tests mock the DB connection; they do not prove
the live Render database is reachable or that writes survive restarts.
