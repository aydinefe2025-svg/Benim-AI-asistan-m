"""No PostgreSQL server, external accounts, network, or real credentials used."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cano_pg_backup import BackupError, _libpq_env_from_url, make_backup, verify_backup


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        fake_dump = self.path / "fake_dump.py"
        fake_dump.write_text(
            "#!" + sys.executable + "\n"
            "import os,sys,pathlib\n"
            "assert os.environ['PGDATABASE'] == 'test'\n"
            "assert os.environ['PGHOST'] == 'example.invalid'\n"
            "assert os.environ['PGPORT'] == '5432'\n"
            "assert os.environ['PGUSER'] == 'private'\n"
            "assert os.environ['PGPASSWORD'] == 'secret'\n"
            "assert os.environ['PGSSLMODE'] == 'require'\n"
            "pathlib.Path(sys.argv[sys.argv.index('--file')+1]).write_bytes(b'PGDMP synthetic bytes')\n",
            encoding="utf-8")
        fake_restore = self.path / "fake_restore.py"
        fake_restore.write_text(
            "#!" + sys.executable + "\n"
            "import sys,pathlib\n"
            "data=pathlib.Path(sys.argv[-1]).read_bytes()\n"
            "if data.startswith(b'PGDMP'): print('synthetic archive list')\n"
            "else: sys.exit(1)\n",
            encoding="utf-8")
        for p in (fake_dump, fake_restore):
            p.chmod(p.stat().st_mode | stat.S_IXUSR)
        if os.name == "nt":
            for path in (fake_dump, fake_restore):
                wrapper = path.with_suffix(".cmd")
                wrapper.write_text(
                    f'@echo off\r\n"{sys.executable}" "{path}" %*\r\n',
                    encoding="utf-8",
                )
            fake_dump = fake_dump.with_suffix(".cmd")
            fake_restore = fake_restore.with_suffix(".cmd")
        self.dump = str(fake_dump)
        self.restore = str(fake_restore)
        self.dest = self.path / "backups"
        self.patch = patch.dict(os.environ, {"DATABASE_URL": "postgresql://private:secret@example.invalid/test"})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_successful_private_backup_and_readback(self):
        result = make_backup(self.dest, dump_bin=self.dump, restore_bin=self.restore)
        self.assertTrue(Path(result["archive"]).is_file())
        self.assertEqual(verify_backup(Path(result["receipt"]), restore_bin=self.restore)["sha256"], result["sha256"])
        self.assertFalse(result["restored_to_new_database"])
        self.assertNotIn("secret", json.dumps(result))
        if os.name == "posix":
            self.assertEqual(Path(result["archive"]).stat().st_mode & 0o777, 0o600)
            self.assertEqual(Path(result["receipt"]).stat().st_mode & 0o777, 0o600)

    def test_tamper_detected(self):
        result = make_backup(self.dest, dump_bin=self.dump, restore_bin=self.restore)
        Path(result["archive"]).write_bytes(b"PGDMP malicious tamper")
        with self.assertRaises(BackupError):
            verify_backup(Path(result["receipt"]), restore_bin=self.restore)

    def test_dump_failure_leaves_no_public_archive(self):
        bad = self.path / "bad_dump.py"
        bad.write_text("#!" + sys.executable + "\nimport sys\nsys.exit(2)\n")
        bad.chmod(bad.stat().st_mode | stat.S_IXUSR)
        if os.name == "nt":
            wrapper = bad.with_suffix(".cmd")
            wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{bad}" %*\r\n')
            bad = wrapper
        with self.assertRaises(BackupError):
            make_backup(self.dest, dump_bin=str(bad), restore_bin=self.restore)
        self.assertEqual(list(self.dest.glob('*')), [])

    def test_rejects_null_byte_database_name(self):
        with self.assertRaises(BackupError):
            _libpq_env_from_url("postgresql://ci:synthetic@localhost/ci%00db")

    def test_rejects_remote_tls_downgrade(self):
        with self.assertRaises(BackupError):
            _libpq_env_from_url(
                "postgresql://ci:synthetic@remote.example.invalid/db?sslmode=disable")

    def test_rejects_missing_url(self):
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            with self.assertRaises(BackupError):
                make_backup(self.dest, dump_bin=self.dump, restore_bin=self.restore)
        self.assertFalse(self.dest.exists())

    def test_rejects_symlinked_archive_readback(self):
        self.dest.mkdir()
        outside = self.path / "private-outside.dump"
        outside.write_bytes(b"PGDMP external archive bytes")
        link = self.dest / "redirect.dump"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this runner")
        receipt = self.dest / "redirect.receipt.json"
        import hashlib
        receipt.write_text(json.dumps({
            "archive": link.name, "size_bytes": outside.stat().st_size,
            "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
        }))
        with self.assertRaises(BackupError):
            verify_backup(receipt, restore_bin=self.restore)

    def test_rejects_receipt_path_traversal(self):
        self.dest.mkdir()
        receipt = self.dest / "bad.receipt.json"
        receipt.write_text(json.dumps({"archive": "../outside.dump", "size_bytes": 6, "sha256": "x"}))
        with self.assertRaises(BackupError):
            verify_backup(receipt, restore_bin=self.restore)


if __name__ == '__main__':
    unittest.main()
