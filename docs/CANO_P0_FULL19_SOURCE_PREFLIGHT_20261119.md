# CANO P0 full 19-table source preflight (2026-11-19)

This optional operator-enforced source gate is for **future** CANO P0 whole-database encrypted pg_dump snapshots. It cannot retrospectively authenticate the previously created `CANO_P0_PG18_19TABLE_113ROWS_20261119.canoenc`.

## Why the nine-table `full` guard is insufficient

The legacy `full` profile checks only nine CANO application tables in `public` and verifies that at least one contains data. A different source can satisfy that limited check while missing `public.cano_code_jobs` or the nine historical recovery tables. A successful AES-GCM backup of that partial source would not be a complete 19-table P0 archive.

The new `p0_19` profile instead checks *exactly* 19 ordinary/partitioned tables across `public` (10) and `cano_p0_neon_recovery_20261115` (9). The query counts rows in all 19 fixed tables with one read-only SQL statement and refuses to start `pg_dump` unless the total equals an **explicit operator-pinned expected count**. Missing/extra tables, mismatched counts, wrong host/database, invalid count, invalid SQL response, or connectivity failure fail closed.

## Operator invocation (secrets stay local)

Set the following **privately in the operator environment**, never in git, issue comments or logs:

- `DATABASE_URL` — owner's read-only backup connection URI for the intended Neon source.
- `CANO_BACKUP_KEY_HEX` — independently protected AES-256 backup key, never printed or committed.
- `CANO_BACKUP_EXPECTED_HOST` — explicit hostname of the intended Neon endpoint.
- `CANO_BACKUP_EXPECTED_DB` — expected database name (e.g. `assistant_pg`).
- `CANO_BACKUP_EXPECTED_TOTAL_ROWS` — current count from a separately authorized read-only inventory (e.g. `113` on the observed 19 Nov checkpoint). It is **not hardcoded** and must be re-verified when the live source changes.

Then run with a private destination and **explicit profile**:

```powershell
python -m scripts.cano_encrypted_backup backup D:\CANO_RECOVERY\02_Sifreli_Arsiv --require-application-profile p0_19
```

The default legacy `full` profile is unchanged for backward compatibility; P0 recovery acceptance must explicitly select `p0_19`.

## Evidence boundaries

- The 19-table count and row total are an independent *preflight SQL statement*, not the transaction snapshot used later by `pg_dump`. Changes between the preflight and dump can alter contents.
- Host/db are pinned to the provided backup connection, but **the deployed Render app's actual DB URL→this Neon branch mapping is not proved by the gate**.
- Encryption, receipt MAC, independent offsite copy, authenticated decryption, standalone `pg_restore`, and source-vs-restored row content comparison each require separate evidence.
- Historical V3 private-key/passphrase restoration is a different acceptance. Do not equate 19/113 logical SQL parity or Notion ciphertext SHA readback with decrypting the new archive.
- The new mode runs only on opt-in; it never creates branches, new database resources, alters live tables or exposes credentials.

## Tests

`python -m unittest tests.test_cano_p0_source_preflight -v`

Covers good 19/113 acceptance, missing/invalid expected rows, 18/20-table deviations, 112/114-row deviations, wrong db/host, provider failure, backwards-compatible `full`, the CLI option and actual propagation into encrypted-backup preflight. GitHub Actions on the PR is the independent integration gate.


## Receiptless archive authentication (new, independent operator step)

An orphan `.canoenc` without an authenticated companion receipt cannot use the old `verify RECEIPT.json` command. The new `verify-archive` command runs AES-256-GCM verification on the **actual pinned ciphertext** without fabricating a receipt or writing a plaintext dump.

Verified existing Windows resources: `cano-tools-pg18/bin/pg_restore.exe` is PostgreSQL **18.7**, and `cano-tools-pg18/pydeps` supplies `cryptography 50.0.2`. No new packages or paid resources are needed. The new command is on **draft PR #643** and must not be claimed installed on the Windows machine before that branch's code is present.

After providing the correct matching `CANO_BACKUP_KEY_HEX` **locally only** (not in chat or GitHub), run the updated script against the pinned archive:

~~~powershell
python scripts/cano_encrypted_backup.py verify-archive C:\Users\User\AppData\Local\SentinelX\workspace\CANO_P0_PG18_19TABLE_113ROWS_20261119.canoenc --expected-sha256 a22cdb7175ed3c006d95fdf76cd00ef37c8d0b22aaa89f274b69a7fa0b45ba07
~~~

The command rejects an invalid/missing expected SHA-256, symlink, truncation, wrong header or missing/wrong AES key before reporting success. It verifies GCM tag and `PGDMP` signature without writing plaintext, and checks disk bytes again before producing results. It returns a plaintext SHA-256/size plus explicit `receipt_authenticated=false`, `source_identity_verified=false` and `isolated_restore_verified=false` boundaries.

This is verification only: it never creates a DB or calls `pg_restore`. Actual isolation restore and source attribution still need separate evidence. The 19-Nov Windows `.cano-neon-backup.env` metadata check listed only `DATABASE_URL`; `CANO_BACKUP_KEY_HEX` was not present in that file, and no secret values were printed.
