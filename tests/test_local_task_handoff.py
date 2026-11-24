import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

from core.authorized_queue import AuthorizedQueue

class LocalHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"queue.sqlite3"
        self.ledger=Path(self.tmp.name)/"worker.sqlite3"
        self.queue=AuthorizedQueue(self.db,owner_key="owner-a")
        self.job=self.queue.enqueue("single","12 x 7?",approved=True)
        self.assertIsNotNone(importlib.util.find_spec("core.local_task_handoff"),
                             "Local handoff feature is not available")
        from core import local_task_handoff
        self.bridge=local_task_handoff

    def test_approved_one_call_and_replay_without_second_call(self):
        with self.assertRaises(PermissionError):
            self.bridge.claim_ticket(self.queue)
        self.assertEqual(self.queue.get(self.job["id"])["state"],"queued")
        private=self.bridge.claim_ticket(self.queue,approved=True)
        ticket=private["ticket"]
        self.assertNotIn("lease_token",ticket)
        self.assertNotIn("owner_key",ticket)
        calls=[]
        answer=lambda goal:calls.append(goal) or "12 x 7 = 84."
        with self.assertRaises(PermissionError):
            self.bridge.run_ticket(ticket,self.ledger,answer)
        result=self.bridge.run_ticket(ticket,self.ledger,answer,approved=True)
        self.assertEqual(self.bridge.run_ticket(ticket,self.ledger,answer,approved=True),result)
        self.assertEqual(calls,["12 x 7?"])
        with self.assertRaises(PermissionError):
            self.bridge.accept_result(self.queue,private,result)
        receipt=self.bridge.accept_result(self.queue,private,result,approved=True)
        self.assertEqual(receipt["status"],"review_pending")
        self.assertFalse(receipt["verified"])
        self.assertEqual(self.queue.get(self.job["id"])["draft"],"12 x 7 = 84.")
        self.assertEqual(self.queue.get(self.job["id"])["attempts"],1)
        self.assertEqual(self.bridge.accept_result(self.queue,private,result,approved=True),receipt)
        self.assertEqual(len(self.queue.events(self.job["id"])),3)

    def test_wrong_owner_and_tamper_rejected_before_commit(self):
        private=self.bridge.claim_ticket(self.queue,approved=True)
        result=self.bridge.run_ticket(private["ticket"],self.ledger,lambda _:"Valid draft.",approved=True)
        other=AuthorizedQueue(self.db,owner_key="owner-b")
        with self.assertRaises(PermissionError):
            self.bridge.accept_result(other,private,result,approved=True)
        broken=copy.deepcopy(result)
        broken["draft"]="Changed"
        with self.assertRaises(ValueError):
            self.bridge.accept_result(self.queue,private,broken,approved=True)
        broken=copy.deepcopy(private["ticket"])
        broken["goal"]="Different task"
        with self.assertRaises(ValueError):
            self.bridge.run_ticket(broken,self.ledger,lambda _:"Not called",approved=True)
        self.assertEqual(self.queue.get(self.job["id"])["state"],"running")

    def test_failed_call_is_not_replayed(self):
        private=self.bridge.claim_ticket(self.queue,approved=True)
        calls=[]
        def fail(goal):
            calls.append(goal)
            raise RuntimeError("provider failed")
        with self.assertRaises(RuntimeError):
            self.bridge.run_ticket(private["ticket"],self.ledger,fail,approved=True)
        with self.assertRaises(RuntimeError):
            self.bridge.run_ticket(private["ticket"],self.ledger,fail,approved=True)
        self.assertEqual(len(calls),1)

    def test_expired_server_lease_does_not_accept_draft(self):
        private=self.bridge.claim_ticket(self.queue,approved=True)
        result=self.bridge.run_ticket(private["ticket"],self.ledger,lambda _:"Valid draft.",approved=True)
        self.queue.recover_expired(now=private["ticket"]["expires_at"]+1)
        with self.assertRaises(PermissionError):
            self.bridge.accept_result(self.queue,private,result,approved=True)
        self.assertEqual(self.queue.get(self.job["id"])["state"],"blocked")

if __name__=="__main__":unittest.main()
