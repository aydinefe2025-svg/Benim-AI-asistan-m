# CANO P0 — encrypted pg_dump watchdog (7 November 2026)

## Defect and measured regression

Existing AES-256-GCM streaming backup used `process.stdout.read(CHUNK)` before its `process.wait(timeout=1800)`. If `pg_dump` emitted a partial archive then stopped responding, the timeout was never reached. The fail-closed unit test reproduced this missing API as RED before changes.

## Fix

- A bounded queue (four 256-KiB chunks) and a daemon pipe-reading thread allow the main backup worker to enforce a `time.monotonic()` deadline even if `pg_dump` blocks. `max_seconds=1800` by default, explicit optional argument for controlled tests.
- The same deadline governs streaming **and** child exit; an overrun terminates the child, removes temporary ciphertext and publishes neither archive nor receipt. No plaintext dump is written.
- Existing main-branch `MEMORY_DATABASE_URL` / `AGENT_TASK_DATABASE_URL` restore-target guard and its test are preserved. An earlier draft [PR #406](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/406) was superseded after detecting concurrent changes.
- Secrets, owner data and encryption key are never committed.

## Evidence and acceptance

- Local synthetic fail-first test (RED) and GREEN **10/10** on isolated source from original PR; CI branch includes the existing main-branch source-guard test as well and must pass independently.
- GitHub PR workflow `cano-encrypted-offsite-dr.yml` uses synthetic PostgreSQL 17 and 18 for encrypted dump → isolated empty DB restore → row comparison.
- This is **not** a real owner-data offsite backup. The independent, encrypted backup of live Neon data still requires user-controlled private storage and an independently retained encryption key. Never upload production dumps or key material to GitHub, Notion or ChatGPT Library.

## Operational boundary

No Render production deployment, no live Neon write, no firewall change, no automatic payment. Do not merge before CI passes.
