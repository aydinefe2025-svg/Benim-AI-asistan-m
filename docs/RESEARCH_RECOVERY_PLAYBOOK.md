# Research system operations and recovery playbook

This document distinguishes **verified automation** from **planned integration**. It is not proof that any production backup has run.

## Verified components

- Research safety gate: `.github/workflows/research-safety-gate.yml`; Python 3.11 and 3.12 tests.
- SQLite backup function: `core/verified_backup.py::verified_sqlite_backup`; checks integrity, computes SHA-256, refuses overwrite.
- Restore regression drill: `tests/test_verified_backup.py`; uses isolated synthetic databases.
- Daily drill definition: `.github/workflows/sqlite-recovery-drill.yml`; schedule at 04:17 UTC, manual dispatch. **GitHub schedules only run from the default branch.** Presence in a development branch alone does not activate it.

## Incident handling

1. Stop dependent writes if a database integrity check fails. Preserve original database and WAL/SHM files for investigation.
2. Identify the last known-good backup by timestamp and SHA-256; never overwrite it.
3. Copy backup to an isolated restore location. Verify the SHA-256 against the recorded digest.
4. Run SQLite `PRAGMA integrity_check` and application-specific record/relationship checks on the isolated copy.
5. Only promote a restored database after independent review, a recorded recovery decision, and a rollback plan.
6. Record the incident, evidence, actions, and unresolved questions in the main research activity log.

## Production integration checklist (not completed)

- [ ] Identify production SQLite file locations and data owners without copying secrets into GitHub.
- [ ] Configure protected, encrypted off-host backup storage and access control.
- [ ] Run a first production-data backup with an explicit retention and deletion policy.
- [ ] Conduct an isolated production-data restore drill and record evidence.
- [ ] Confirm default-branch workflow activation and branch protection.
- [ ] Add failure alerting and periodic audit of backup age, hash, and restore outcomes.

## Scope and limitations

A green CI result validates tests against synthetic data; it does **not** establish that live research records were backed up, recovered, or synchronized with Notion. A daily workflow is not a substitute for an off-site backup. Do not store API keys, private datasets, or production databases in the repository.
