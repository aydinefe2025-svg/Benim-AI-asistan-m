import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.persistent_storage import (
    PersistentStorageError,
    validate_production_sqlite_path,
)


class ProductionStoragePreflightTests(unittest.TestCase):
    def test_valid_absolute_path_inside_configured_root(self):
        self.assertEqual(
            validate_production_sqlite_path(
                "/var/data/research/store.sqlite3",
                persistent_root="/var/data",
            ),
            Path("/var/data/research/store.sqlite3"),
        )

    def test_rejects_missing_configuration(self):
        for path, root in [(None, "/var/data"), ("/var/data/db.sqlite3", None)]:
            with self.subTest(path=path, root=root):
                with self.assertRaises(PersistentStorageError):
                    validate_production_sqlite_path(path, persistent_root=root)

    def test_rejects_relative_and_temporary_paths(self):
        for path, root in [
            ("data/research.db", "/var/data"),
            ("/tmp/research.db", "/tmp"),
            ("/var/data/research.db", "/"),
            ("/var/data/research.db", "var/data"),
            ("/opt/render/project/src/research.db", "/var/data"),
            ("/var/data/../tmp/research.db", "/var/data"),
        ]:
            with self.subTest(path=path, root=root):
                with self.assertRaises(PersistentStorageError):
                    validate_production_sqlite_path(path, persistent_root=root)

    def test_symlink_escape_is_rejected(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "mounted"
            root.mkdir()
            (root / "escape").symlink_to(base, target_is_directory=True)
            with self.assertRaises(PersistentStorageError):
                validate_production_sqlite_path(
                    root / "escape" / "db.sqlite3",
                    persistent_root=root,
                )


if __name__ == "__main__":
    unittest.main()
