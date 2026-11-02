from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from core.sqlite_snapshot import snapshot_directory, restore_directory
from core.task_store import TaskStore
from core.research_drafts import save_draft, load_draft


class DirectorySnapshotTests(unittest.TestCase):
    def test_real_session_history_and_draft_survive_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source'
            source.mkdir()
            first = TaskStore(source / 'tasks.first.sqlite3')
            task = first.create('Preserve existing work', 'Full history')
            first.transition(task['id'], 'running', note='Started')
            save_draft(first.db_path, task['id'], 'Original private draft')
            second = TaskStore(source / 'tasks.second.sqlite3')
            second.create('Isolated session')
            backup, restored = root / 'backup', root / 'restored'
            self.assertEqual(snapshot_directory(source, backup)['database_count'], 2)
            self.assertEqual(restore_directory(backup, restored)['database_count'], 2)
            recovered = TaskStore(restored / 'tasks.first.sqlite3')
            self.assertEqual(recovered.list(), first.list())
            self.assertEqual(recovered.history(task['id']), first.history(task['id']))
            self.assertEqual(load_draft(recovered.db_path, task['id']), 'Original private draft')
            self.assertEqual(TaskStore(restored / 'tasks.second.sqlite3').list(), second.list())

    def test_wal_committed_data_included_without_closing_writer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with closing(sqlite3.connect(root / 'wal.db')) as conn:
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('CREATE TABLE records(value TEXT)')
                conn.execute("INSERT INTO records VALUES('committed')")
                conn.commit()
                snapshot_directory(root, root / 'snapshot')
                with closing(sqlite3.connect(root / 'snapshot' / 'wal.db')) as restored:
                    self.assertEqual(restored.execute('SELECT * FROM records').fetchall(), [('committed',)])

    def test_preexisting_destination_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            TaskStore(root / 'tasks.sqlite3').create('Retain')
            snapshot_directory(root, root / 'snapshot')
            with self.assertRaises(FileExistsError):
                snapshot_directory(root, root / 'snapshot')
            with self.assertRaises(FileExistsError):
                restore_directory(root / 'snapshot', root)

    def test_tampering_and_unsafe_paths_rejected_before_target_created(self):
        for name in ['../outside.db', 'C:\\outside.db', 'tasks.sqlite3']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                TaskStore(root / 'tasks.sqlite3')
                backup, target = root / 'backup', root / 'target'
                snapshot_directory(root, backup)
                manifest = json.loads((backup / 'manifest.json').read_text())
                manifest['databases'][0]['name'] = name
                manifest['databases'][0]['sha256'] = '0' * 64
                (backup / 'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    restore_directory(backup, target)
                self.assertFalse(target.exists())
