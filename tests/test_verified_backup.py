import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.verified_backup import verified_sqlite_backup, sha256_file


class VerifiedBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "research.sqlite3"
        with sqlite3.connect(self.source) as db:
            db.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, claim TEXT)")
            db.execute("INSERT INTO evidence (claim) VALUES ('verified sample')")

    def test_backup_is_readable_and_hash_matches(self):
        destination = self.root / "archive" / "snapshot.sqlite3"
        report = verified_sqlite_backup(self.source, destination)
        self.assertEqual(report["integrity"], "ok")
        self.assertEqual(report["sha256"], sha256_file(destination))
        self.assertGreater(report["bytes"], 0)
        with sqlite3.connect(destination) as db:
            self.assertEqual(db.execute("SELECT claim FROM evidence").fetchone()[0], "verified sample")
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_restore_drill_preserves_records_and_schema(self):
        """Exercise a full restore into an isolated database, not the live one."""
        backup = self.root / "snapshot.sqlite3"
        report = verified_sqlite_backup(self.source, backup)
        restored = self.root / "restored.sqlite3"
        with sqlite3.connect(backup) as source_db:
            with sqlite3.connect(restored) as restored_db:
                source_db.backup(restored_db)
                self.assertEqual(
                    restored_db.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                )
                self.assertEqual(
                    restored_db.execute("SELECT claim FROM evidence").fetchall(),
                    [("verified sample",)],
                )
                self.assertIsNotNone(
                    restored_db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='evidence'"
                    ).fetchone()
                )
        self.assertEqual(report["sha256"], sha256_file(backup))

    def test_backup_does_not_modify_source(self):
        before = self.source.stat().st_size
        verified_sqlite_backup(self.source, self.root / "snapshot.sqlite3")
        with sqlite3.connect(self.source) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 1
            )
        self.assertEqual(self.source.stat().st_size, before)

    def test_existing_backup_is_never_overwritten(self):
        destination = self.root / "snapshot.sqlite3"
        destination.write_bytes(b"existing archive")
        with self.assertRaises(FileExistsError):
            verified_sqlite_backup(self.source, destination)
        self.assertEqual(destination.read_bytes(), b"existing archive")

    def test_missing_source_does_not_create_backup(self):
        destination = self.root / "missing-backup.sqlite3"
        with self.assertRaises(FileNotFoundError):
            verified_sqlite_backup(self.root / "missing.sqlite3", destination)
        self.assertFalse(destination.exists())

    def test_source_cannot_be_destination(self):
        with self.assertRaises(ValueError):
            verified_sqlite_backup(self.source, self.source)

    def test_wal_mode_committed_records_included(self):
        with sqlite3.connect(self.source) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("INSERT INTO evidence (claim) VALUES ('wal committed')")
        destination = self.root / "wal-backup.sqlite3"
        verified_sqlite_backup(self.source, destination)
        with sqlite3.connect(destination) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
