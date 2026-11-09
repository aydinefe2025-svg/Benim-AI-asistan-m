# CANO Render PG18 owner-only preflight (no database access)

This read-only utility checks local prerequisites before the **existing**
`scripts/cano_render_rescue.py` encrypted backup operation. It does **not**
connect to Render, run pg_dump, open a firewall, upload data, or restore a DB.

On the owner's trusted machine, set the actual configured database URLs and
encryption key **privately**, outside shell history and without sending them
to GitHub, Notion, chat, CI, or logs. Keep both non-secret expected Render
identifiers set:

- `CANO_REQUIRED_RENDER_DATABASE=research_library_persistent_db`
- `CANO_REQUIRED_RENDER_HOST_PREFIX=dpg-dbkfp5bm8hqs73bba7u0-a`

Choose a **fresh** destination with an existing private parent directory and
at least approximately 2 GiB plus 64 MiB free for the configured backup cap.
Use PostgreSQL **18** clients (`pg_dump`, `pg_restore`, `psql`).

```powershell
python -m scripts.cano_render_operator_preflight "D:\CANO_PRIVATE\rescue_new"
```

A nonzero exit means one or more **local** checks failed. The output contains
only boolean checks, never a URL, hostname, account, password, or key.
The preflight checks the syntax of the expected Render URI but does **not**
prove that the URI connects to the actual remote server. On Windows it reads
the destination's access control list and passes only when the current user
owns the folder and the only allowed principals are that user, SYSTEM, and
local Administrators. If PowerShell cannot read the ACL or reports any other
allowed principal, the check fails closed. The output reports only whether the
ACL check passed; it never emits account names or ACL entries.
This does not test an authorized /32 external connection; use the existing
operator runbook and do not open access to 0.0.0.0/0.

Even with `local_preflight_passed=true`, all three fields
`network_verified`, `offsite_verified`, and
`isolated_restore_verified` remain false. The real data recovery gate stays
open until an authorized private Render encrypted export, independent durable
readback and isolated PostgreSQL 18 restore are individually proven.

Focus tests: `python -m unittest tests.test_cano_render_operator_preflight -v`.
No production deployment is needed or requested by this change.
