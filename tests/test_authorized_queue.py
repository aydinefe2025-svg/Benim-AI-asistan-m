import os
import sqlite3
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from core.authorized_queue import AuthorizedQueue


class AuthorizedQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / 'authorized.sqlite3')
        self.queue = AuthorizedQueue(self.db, owner_key='user-a', max_jobs=4)

    def test_enqueue_rejects_unapproved_and_idempotently_reuses_key(self):
        with self.assertRaises(PermissionError):
            self.queue.enqueue('task-1', 'Check source evidence')
        first = self.queue.enqueue('task-1', 'Check source evidence', approved=True, max_calls=2)
        same = self.queue.enqueue('task-1', 'Check source evidence', approved=True, max_calls=2)
        self.assertEqual(first['id'], same['id'])
        with self.assertRaises(ValueError):
            self.queue.enqueue('task-1', 'Different goal', approved=True, max_calls=2)
        self.assertEqual(len(self.queue.list()), 1)

    def test_authorized_one_task_executes_once_into_review_pending(self):
        job = self.queue.enqueue('source-1', 'Review bibliography', approved=True)
        called = []
        with self.assertRaises(PermissionError):
            self.queue.run_once('worker-1', lambda goal: called.append(goal) or 'Draft')
        result = self.queue.run_once('worker-1', lambda goal: called.append(goal) or 'Draft', approved=True, now=100)
        self.assertEqual(result['status'], 'review_pending')
        self.assertFalse(result['verified'])
        self.assertEqual(called, ['Review bibliography'])
        self.assertEqual(self.queue.get(job['id'])['state'], 'review_pending')
        self.assertIsNone(self.queue.run_once('worker-1', lambda goal: 'Again', approved=True, now=101))
        self.assertEqual([e['state'] for e in self.queue.events(job['id'])], ['queued', 'running', 'review_pending'])

    def test_failed_provider_is_sanitized_and_budget_bounded(self):
        job = self.queue.enqueue('retry', 'Review', approved=True, max_calls=2)
        def fail(_):
            raise RuntimeError('confidential token 1234')
        first = self.queue.run_once('worker-1', fail, approved=True, now=100)
        self.assertEqual(first['status'], 'retry_pending')
        self.assertEqual(self.queue.get(job['id'])['state'], 'queued')
        self.assertIsNone(self.queue.run_once('worker-2', fail, approved=True, now=100))
        second = self.queue.run_once('worker-2', fail, approved=True, now=103)
        self.assertEqual(second['status'], 'blocked')
        self.assertEqual(self.queue.get(job['id'])['attempts'], 2)
        self.assertEqual(self.queue.get(job['id'])['state'], 'blocked')
        self.assertNotIn('confidential', str(self.queue.events(job['id'])))

    def test_lease_expiry_blocks_rather_than_repeating_external_call(self):
        job = self.queue.enqueue('lost', 'Review', approved=True, max_calls=3)
        lease = self.queue.claim('worker-1', approved=True, now=10, lease_seconds=5)
        self.assertEqual(lease['id'], job['id'])
        self.assertEqual(self.queue.recover_expired(now=16), 1)
        self.assertEqual(self.queue.get(job['id'])['state'], 'blocked')
        with self.assertRaises(PermissionError):
            self.queue.complete(job['id'], lease['lease_token'], 'Late draft', now=17)
        self.assertIsNone(self.queue.claim('worker-2', approved=True, now=18))

    def test_second_owner_cannot_see_or_claim_first_owner_task(self):
        job = self.queue.enqueue('owned', 'Private task', approved=True)
        other = AuthorizedQueue(self.db, owner_key='user-b', max_jobs=4)
        self.assertEqual(other.list(), [])
        self.assertIsNone(other.claim('other-worker', approved=True, now=20))
        with self.assertRaises(KeyError):
            other.get(job['id'])
        self.assertEqual(len(self.queue.list()), 1)

    def test_concurrent_claim_does_not_duplicate_execution(self):
        self.queue.enqueue('race', 'One task', approved=True)
        barrier = threading.Barrier(2)
        acquired = []
        lock = threading.Lock()
        def get_one(worker):
            barrier.wait()
            lease = self.queue.claim(worker, approved=True, now=30)
            with lock:
                acquired.append(lease)
        threads = [threading.Thread(target=get_one, args=(f'worker-{i}',)) for i in range(2)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(sum(lease is not None for lease in acquired), 1)

    def test_state_survives_reopening_same_database(self):
        job = self.queue.enqueue('reopen', 'Saved goal', approved=True)
        reopened = AuthorizedQueue(self.db, owner_key='user-a', max_jobs=4)
        self.assertEqual(reopened.get(job['id'])['goal'], 'Saved goal')
        self.assertEqual(len(reopened.events(job['id'])), 1)

    @unittest.skipUnless(os.name == "posix", "POSIX permission contract")
    def test_existing_queue_database_and_rollback_journal_are_private(self):
        job = self.queue.enqueue(
            "private", "Keep this task private", approved=True)
        os.chmod(self.db, 0o644)  # Simulate older insecure queue file.
        reopened = AuthorizedQueue(self.db, owner_key="user-a", max_jobs=4)
        self.assertEqual(reopened.get(job["id"])["state"], "queued")
        self.assertEqual(stat.S_IMODE(os.stat(self.db).st_mode), 0o600)
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "UPDATE authorized_jobs SET goal=? WHERE id=?",
                ("Private draft text", job["id"]))
            journal = self.db + "-journal"
            self.assertTrue(os.path.isfile(journal))
            self.assertEqual(stat.S_IMODE(os.stat(journal).st_mode), 0o600)

    @unittest.skipUnless(os.name == "posix", "POSIX symlink contract")
    def test_queue_refuses_symlinked_sqlite_target_without_creating_database(self):
        root = Path(self.temp.name)
        victim = root / "unrelated.sqlite3"
        link = root / "queue-link.sqlite3"
        link.symlink_to(victim)
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            AuthorizedQueue(link, owner_key="user-a", max_jobs=4)
        self.assertFalse(victim.exists())

    def test_quota_rejects_unbounded_task_creation(self):
        for i in range(4):
            self.queue.enqueue(f'key-{i}', f'Goal {i}', approved=True)
        with self.assertRaises(RuntimeError):
            self.queue.enqueue('overflow', 'Extra', approved=True)


if __name__ == '__main__':
    unittest.main()
