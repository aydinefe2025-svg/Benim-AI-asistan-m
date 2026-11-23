import json
from pathlib import Path
import tempfile
import unittest
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from core.cano_backup_bundle import (
    create_portable_bundle, export_authorized_queue, verify_portable_bundle,
)
from core.backup_encryption import encrypt_backup
from scripts.cano_secure_backup import restore_to_new_directory


class FakeQueue:
    def list(self):
        return [{"id": "job-1", "goal": "task", "state": "review_pending",
                 "draft": "unverified", "owner_key": "private-owner",
                 "lease_token": "secret-token"}]

    def events(self, job_id):
        self.event_job = job_id
        return [{"state": "review_pending", "code": "unverified_draft_saved"}]


class CanoBackupBundleTests(unittest.TestCase):
    def test_owner_queue_backup_excludes_owner_and_lease_secrets(self):
        queue = FakeQueue()
        jobs = export_authorized_queue(queue)
        self.assertEqual(queue.event_job, "job-1")
        self.assertNotIn("owner_key", jobs[0])
        self.assertNotIn("lease_token", jobs[0])
        self.assertEqual(jobs[0]["events"][0]["state"], "review_pending")

    def test_bundle_contains_owner_scoped_json_and_verified_manifest(self):
        colony = {key: [] for key in ("agents", "feedback", "reviews", "missions")}
        colony["agents"] = [{"id": "agent-1", "role": "research"}]
        memories = [{"id": "memory-1", "text": "Türkçe tercih", "tags": [],
                     "created_at": "2026-11-06T00:00:00+00:00"}]
        queue = FakeQueue()
        bundle = create_portable_bundle(
            colony=colony, memories=memories,
            research_tasks=b'{"schema":"research-task-export-v1","tasks":[]}',
            authorized_queue=export_authorized_queue(queue),
        )
        files = verify_portable_bundle(bundle)
        self.assertEqual(set(files), {
            "cano-colony.json", "memory-library.json", "research-tasks.json",
            "authorized-queue.json", "manifest.json",
        })
        self.assertEqual(json.loads(files["cano-colony.json"])["agents"][0]["id"], "agent-1")
        self.assertEqual(json.loads(files["memory-library.json"])["items"], memories)
        queue_payload = json.loads(files["authorized-queue.json"])
        self.assertTrue(queue_payload["available"])
        self.assertNotIn("owner_key", queue_payload["jobs"][0])
        self.assertNotIn("lease_token", queue_payload["jobs"][0])
        self.assertTrue(json.loads(files["manifest.json"])["sources_available"]["authorized_queue"])

    def test_v2_portable_backup_preserves_lab_experiments_through_offline_restore(self):
        import base64
        import hashlib
        raw = b'{"robots":2,"checked":true}'
        digest = hashlib.sha256(raw).hexdigest()
        records = [{
            "record_id": "cano-organism-lab-v1-world-" + digest,
            "kind": "world", "sha256": digest,
            "data_b64": base64.b64encode(raw).decode("ascii")
        }]
        colony = {key: [] for key in ("agents", "feedback", "reviews", "missions")}
        bundle = create_portable_bundle(
            colony=colony, memories=[], research_tasks=b"{}",
            authorized_queue=[], organism_records=records)
        contents = verify_portable_bundle(bundle)
        self.assertIn("organism-lab-records.json", contents)
        self.assertEqual(json.loads(contents["organism-lab-records.json"])["records"],
                         records)
        manifest = json.loads(contents["manifest.json"])
        self.assertEqual(manifest["schema"], "cano-portable-backup-v2")
        self.assertTrue(manifest["sources_available"]["organism_lab"])
        password = "correct-horse-staple-cano-backup"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "account.canoenc"
            source.write_bytes(encrypt_backup(bundle, password))
            files = restore_to_new_directory(source, root / "restored", password)
            self.assertIn("organism-lab-records.json", files)
            restored = json.loads((root / "restored" / "organism-lab-records.json").read_text())
            self.assertEqual(restored["records"], records)

    def test_v2_export_rejects_lab_record_larger_than_store_limit(self):
        import base64
        import hashlib
        from core.organism_lab_persistence import OrganismLabStore

        limit = OrganismLabStore.MAX_RECORD_BYTES
        raw = b'{"payload":"' + b"x" * limit + b'"}'
        self.assertGreater(len(raw), limit)
        digest = hashlib.sha256(raw).hexdigest()
        oversized = [{
            "record_id": "cano-organism-lab-v1-world-" + digest,
            "kind": "world",
            "sha256": digest,
            "data_b64": base64.b64encode(raw).decode("ascii"),
        }]
        colony = {key: [] for key in ("agents", "feedback", "reviews", "missions")}
        with self.assertRaisesRegex(ValueError, "size limit"):
            create_portable_bundle(
                colony=colony, memories=[], research_tasks=b"{}",
                authorized_queue=[], organism_records=oversized,
            )

    def test_v2_verified_archive_rejects_oversized_lab_record_even_with_valid_manifest(self):
        import base64
        import hashlib
        from core.organism_lab_persistence import OrganismLabStore

        raw = b'{"payload":"' + b"x" * OrganismLabStore.MAX_RECORD_BYTES + b'"}'
        digest = hashlib.sha256(raw).hexdigest()
        oversized = {
            "record_id": "cano-organism-lab-v1-world-" + digest,
            "kind": "world",
            "sha256": digest,
            "data_b64": base64.b64encode(raw).decode("ascii"),
        }
        colony = {key: [] for key in ("agents", "feedback", "reviews", "missions")}
        good = create_portable_bundle(
            colony=colony, memories=[], research_tasks=b"{}",
            authorized_queue=[], organism_records=[],
        )
        with ZipFile(BytesIO(good), "r") as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        lab = json.dumps({
            "schema": "cano-organism-lab-export-v1", "records": [oversized],
        }, separators=(",", ":")).encode("utf-8")
        files["organism-lab-records.json"] = lab
        manifest = json.loads(files["manifest.json"])
        manifest["components"]["organism-lab-records.json"] = {
            "sha256": hashlib.sha256(lab).hexdigest(),
            "size_bytes": len(lab),
        }
        files["manifest.json"] = json.dumps(manifest, separators=(",", ":")).encode()
        forged = BytesIO()
        with ZipFile(forged, "w", compression=ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        with self.assertRaisesRegex(ValueError, "size limit"):
            verify_portable_bundle(forged.getvalue())

    def test_strict_owner_restore_rejects_checksum_valid_incomplete_account(self):
        """File hashes alone must not certify recovery of the full owner's account."""
        colony = {key: [] for key in ("agents", "feedback", "reviews", "missions")}
        bundle = create_portable_bundle(
            colony=colony, memories=None, research_tasks=None,
            authorized_queue=None, organism_records=[],
        )
        self.assertEqual(len(verify_portable_bundle(bundle)), 6)
        password = "correct-horse-staple-cano-backup"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, destination = root / "incomplete.canoenc", root / "restored"
            source.write_bytes(encrypt_backup(bundle, password))
            with self.assertRaisesRegex(ValueError, "complete|unavailable"):
                restore_to_new_directory(
                    source, destination, password, require_complete=True)
            self.assertFalse(destination.exists(),
                             "Do not extract a partial archive as a full account")

    def test_strict_owner_restore_rejects_malformed_research_with_valid_hash(self):
        """A fully available but unusable section cannot pass full recovery."""
        colony = {key: [] for key in ("agents", "feedback", "reviews", "missions")}
        bundle = create_portable_bundle(
            colony=colony, memories=[], research_tasks=b"{}",
            authorized_queue=[], organism_records=[],
        )
        self.assertEqual(len(verify_portable_bundle(bundle)), 6)
        password = "correct-horse-staple-cano-backup"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, destination = root / "malformed.canoenc", root / "restored"
            source.write_bytes(encrypt_backup(bundle, password))
            with self.assertRaisesRegex(ValueError, "research"):
                restore_to_new_directory(
                    source, destination, password, require_complete=True)
            self.assertFalse(destination.exists())

    def test_complete_preflight_rejects_invalid_research_receipt_with_valid_outer_hash(self):
        """A rebuilt outer ZIP manifest must not mask corrupt research provenance."""
        from core.archive_integrity import archive_digest
        from core.cano_backup_bundle import verify_complete_portable_bundle

        colony = {key: [] for key in ("agents", "feedback", "reviews", "missions")}
        research = {
            "schema": "research-task-export-v1",
            "exported_at": "2026-11-23T20:00:00+00:00",
            "warning": "unverified draft",
            "tasks": [{"id": "original-task"}],
        }
        research["integrity"] = {"algorithm": "sha256", "digest": archive_digest(research)}
        common = dict(
            colony=colony, memories=[], authorized_queue=[], organism_records=[],
        )
        good = create_portable_bundle(
            research_tasks=json.dumps(research).encode("utf-8"), **common,
        )
        self.assertEqual(len(verify_complete_portable_bundle(good)), 6)

        # The current archive writer authenticates these bytes in its outer
        # manifest, but the research payload's own signed-off digest is stale.
        research["tasks"][0]["id"] = "changed-after-receipt"
        tampered = create_portable_bundle(
            research_tasks=json.dumps(research).encode("utf-8"), **common,
        )
        self.assertEqual(len(verify_portable_bundle(tampered)), 6)
        with self.assertRaisesRegex(ValueError, "research|integrity"):
            verify_complete_portable_bundle(tampered)

    def test_strict_owner_restore_accepts_verified_complete_account(self):
        """A valid v2 archive remains recoverable in the complete-owner mode."""
        colony = {key: [] for key in ("agents", "feedback", "reviews", "missions")}
        bundle = create_portable_bundle(
            colony=colony, memories=[],
            research_tasks=b'{"schema":"research-task-export-v1","tasks":[]}',
            authorized_queue=[], organism_records=[],
        )
        password = "correct-horse-staple-cano-backup"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, destination = root / "complete.canoenc", root / "restored"
            source.write_bytes(encrypt_backup(bundle, password))
            files = restore_to_new_directory(
                source, destination, password, require_complete=True)
            self.assertEqual(len(files), 5)
            self.assertEqual(set(files), {
                "cano-colony.json", "memory-library.json",
                "research-tasks.json", "authorized-queue.json",
                "organism-lab-records.json",
            })


    def test_bundle_rejects_tampered_component_and_unexpected_files(self):
        colony = {key: [] for key in ("agents", "feedback", "reviews", "missions")}
        bundle = create_portable_bundle(
            colony=colony, memories=[], research_tasks=b"{}", authorized_queue=[])
        files = verify_portable_bundle(bundle)
        files["cano-colony.json"] += b"x"
        forged = BytesIO()
        with ZipFile(forged, "w", compression=ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        with self.assertRaisesRegex(ValueError, "checksum"):
            verify_portable_bundle(forged.getvalue())

        unexpected = BytesIO()
        with ZipFile(unexpected, "w") as archive:
            archive.writestr("../secret.json", b"x")
        with self.assertRaisesRegex(ValueError, "file list"):
            verify_portable_bundle(unexpected.getvalue())

    def test_bundle_rejects_invalid_colony_and_missing_queue(self):
        with self.assertRaises(ValueError):
            create_portable_bundle(colony={}, memories=[], research_tasks=b"{}",
                                   authorized_queue=[])
        colony = {key: [] for key in ("agents", "feedback", "reviews", "missions")}
        bundle = create_portable_bundle(colony=colony, memories=[], research_tasks=None,
                                        authorized_queue=None)
        files = verify_portable_bundle(bundle)
        manifest = json.loads(files["manifest.json"])
        self.assertFalse(manifest["sources_available"]["research_tasks"])
        self.assertFalse(manifest["sources_available"]["authorized_queue"])

    def test_offline_restore_authenticates_and_writes_only_validated_files(self):
        colony = {key: [] for key in ("agents", "feedback", "reviews", "missions")}
        bundle = create_portable_bundle(
            colony=colony, memories=[], research_tasks=b"{}", authorized_queue=[])
        password = "correct-horse-staple-cano-backup"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "cano.canoenc"
            source.write_bytes(encrypt_backup(bundle, password))
            destination = root / "restored"
            files = restore_to_new_directory(source, destination, password)
            self.assertEqual(files, sorted([
                "cano-colony.json", "memory-library.json", "research-tasks.json",
                "authorized-queue.json",
            ]))
            self.assertEqual(set(path.name for path in destination.iterdir()), set(files))
            with self.assertRaises(ValueError):
                restore_to_new_directory(source, root / "wrong", "incorrect-password-long")



if __name__ == "__main__":
    unittest.main()

