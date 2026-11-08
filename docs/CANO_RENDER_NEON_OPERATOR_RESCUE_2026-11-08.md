# CANO Render PostgreSQL → Neon PG18 operator-only rescue (2026-11-08)

## Why this exists

Render Free PostgreSQL `dpg-dbkfp5bm8hqs73bba7u0-a` expires at
**2026-12-02 21:11:49 UTC**. Free PostgreSQL has no Render-managed backups.
The hosted connector is blocked by the database's empty external IP allowlist.
**Do not treat CI synthetic data, the existing Neon archive, or this script as
proof that the separate Render source was exported.**

A prepared **empty** PostgreSQL 18 restore target is available in another
provider: Neon project `delicate-shape-38017562`, branch
`br-ancient-boat-baersipb`, database `cano_restore_render_20261108`
(created and independently queried: 0 user tables). This target contains no
restored Render data as of 8 Nov 2026.

## 1. The owner's machine is the export runner

Only on the owner's persistent private Windows/Linux host:

- Use PostgreSQL **18** client tools `pg_dump`, `pg_restore` and `psql`.
- Install the Python dependencies in `requirements-persistence.txt`.
- Retrieve the relevant **actual active** PostgreSQL connection URIs from the
  owner's credential manager/provider dashboards into process-local environment
  variables: `CANO_DATABASE_URL`, `DATABASE_URL`,
  `MEMORY_DATABASE_URL`, `AGENT_TASK_DATABASE_URL` (each only if configured).
  Check every active application source: missing variables cannot be backed up.
- Generate and retain an independent 32-byte random AES key offline. Provide
  its 64 hex digits as `CANO_BACKUP_KEY_HEX` **without entering it in command
  history or sharing it in chat, GitHub, Notion or logs**.
- For an external Render connection, use only the owner's fixed trusted public
  IP address (`/32`) in the Render database Networking allowlist for the
  minimum required period; remove that allowance afterward. Never open
  `0.0.0.0/0` or put production credentials into a GitHub workflow.
  Alternatively use an already-authorized private, same-region Render job
  with an independently secure *persistent* receiver; no such production
  execution is claimed here.

Run, from the repository root, choosing a **fresh, empty private directory**
on the owner's persistent disk (not a free Render web filesystem).
**Set both non-secret Render identity guards** before the export. This makes
the run refuse to publish a complete manifest if only the Neon URLs are
configured or the expired Render database's connection URI is missing.
The hostname check accepts the exact Render service hostname or its
`.render.com` subdomain, not a lookalike domain.

```powershell
$env:CANO_REQUIRED_RENDER_DATABASE = "research_library_persistent_db"
$env:CANO_REQUIRED_RENDER_HOST_PREFIX = "dpg-dbkfp5bm8hqs73bba7u0-a"
python -m scripts.cano_render_rescue "D:\CANO_PRIVATE\rescue_20261108"
```

If the command returns an error, **do not remove these guards to force a
success**. Confirm the owner-only actual Render source connection is present.
These identifiers are not connection credentials and do not grant access.
The entry `required_render_source_matched: true` merely records that at
least one *configured URI* had the expected host prefix and database name.
It does not prove the server's operator identity or the archive's actual
contents until encrypted dump and independent restore/readback complete.

This calls the existing direct-to-AES-256-GCM `pg_dump` path for each distinct
configured URI and verifies each receipt. Identical full URIs are deduplicated
while all associated environment aliases are kept in the manifest.
An error on any configured source prevents a **complete** manifest.
Manifest contains only safe alias names, hashes, relative encrypted file paths,
and explicit `offsite_verified=false` / `isolated_restore_verified=false`.
This operation does **not** restore, delete, migrate or deploy anything.
It refuses to run inside a Render web service.

## 2. Durable independent encrypted copy and readback

Copy the **entire** resulting private directory, including
`cano-rescue-manifest.json`, `source-*/*.canoenc` and
`source-*/*.receipt.json`, into a private different-provider store.
Confirm the upload is finished, re-fetch it to a private machine, and run
`python -m scripts.cano_encrypted_backup verify <receipt-path>` for **each**
copied receipt, using the original key, plus a byte-wise SHA-256 manifest
comparison. A local copy or sync queue is not an offsite receipt. Keep the AES
key out of the backup provider. Do not publish an archive in public GitHub.

## 3. Restore into the already-provisioned empty Neon PG18 database

After real Render export and independent encrypted readback, inspect
`cano-rescue-manifest.json`: `required_render_source_numbers` is an
explicit list such as `[2]` identifying the encrypted archive directory
created from the expected Render connection, **not necessarily source-01**.
Match that number with its entry `archive` relative path and authenticated
receipt. Never guess the source number, and fail if the required source list
is absent or empty. Supply the owner's separate Neon restore URI only through
`CANO_RESTORE_DATABASE_URL`; leave active source URLs in their own environment
variables so the restore guards can reject accidental source overwrite.
**Restore only one compatible source archive per empty database**:

```powershell
python -m scripts.cano_encrypted_backup restore-isolated "<exact archive path from verified Render manifest>" --confirm-empty-isolated-target
```

The database name must start with `cano_restore_` and be genuinely empty.
Do not merge divergent production/main branches or deploy this draft code
before the separate source-access and acceptance gates.

For CANO's nine known application tables, the repository already has a
read-only cross-DB checksum/schema auditor `scripts.cano_dr_compare`.
When isolated restore exists, use the owner's private
`CANO_AUDIT_SOURCE_DATABASE_URL` and
`CANO_RESTORE_DATABASE_URL` environments, then:

```powershell
python -m scripts.cano_dr_compare
```

That auditor covers the **nine CANO tables** and schema metadata, not every
PostgreSQL object or other databases. Additional actual Render tables,
permissions, owner identities, and application login/restart acceptance must
be checked separately. Only then decide on migration and production cutover.

## Acceptance / status as of 2026-11-08

- [x] Neon existing 9-table/30-record backup contents independently compared
  to its Neon source, 9/9 SHA-256 digests equal (NOT Render data).
- [x] Empty Neon PG18 restore database independently created and queried.
- [ ] Render source external/private authorized access.
- [ ] Actual Render source `pg_dump` encrypted export.
- [ ] Independent provider uploaded encrypted files, checksum download readback.
- [ ] Actual Render data restored into empty PG18 target.
- [ ] Complete source and target row/schema/owner verification.
- [ ] Safe app cutover and rollback acceptance.

Canonical task: https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/95
Existing Render OFFSITE script: `scripts/cano_encrypted_backup.py`
Rescue coverage script in this draft: `scripts/cano_render_rescue.py`.
