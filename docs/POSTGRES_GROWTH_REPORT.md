# Growth foundation verification — 2026-11-03

## Result

A free Neon PostgreSQL development project was provisioned and exercised with the existing PostgreSQL memory adapter. This is a development foundation; it is not wired into the live app and no production data was migrated.

Project: `benim-ai-persistence` (PostgreSQL 17, Frankfurt, free plan, 0.25 CU). Its endpoint is currently idle after the real integration checks. The adapter dependency is pinned to psycopg 3.3.7.

## Evidence

- Local suite: 221 passed.
- Dependency consistency: `pip check` passed.
- Real PostgreSQL flow: write/read, owner-scope separation, fresh-connection read, transaction rollback, synthetic export/recovery all passed.
- A committed synthetic row remained readable after the client process exited and after the Neon compute restarted.
- Three synthetic rows were retained; no existing rows were deleted.
- No Render deployment or live data migration was performed.
- Detailed machine-readable evidence: [results.json](neon-growth-2026-11-03/results.json).

## Remaining production gates

1. Establish and verify an application-authenticated user identity; derive the owner key on the server.
2. Create a least-privilege runtime database role and store its connection secret in Render.
3. Produce and independently verify a fresh backup of the current Render data.
4. Reconcile a separate migration target and compare row counts/checksums before any cutover.
5. Enable the PostgreSQL store only after those checks, with a tested rollback path.

The current adapter's owner key is a data partition key, not an authentication boundary. Do not claim production authorization or a completed migration until these gates have evidence. Monitor free-tier usage; no paid operation was started.
