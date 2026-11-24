import importlib.util
import tempfile
import unittest
from pathlib import Path
from core.authorized_queue import AuthorizedQueue
from core.local_task_handoff import claim_ticket, run_ticket

class GrantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.q=AuthorizedQueue(self.root/"queue.db",owner_key="test-owner")
        self.job=self.q.enqueue("one","One approved goal",approved=True)
        self.private=claim_ticket(self.q,approved=True)
        self.assertIsNotNone(importlib.util.find_spec("core.local_single_grant"),
                             "Single-task grant does not exist")
        from core.local_single_grant import SingleTaskGrant
        self.g,self.token=SingleTaskGrant.issue(self.q,self.private,approved=True)
    def test_wrong_token_and_one_take_only(self):
        with self.assertRaises(PermissionError):self.g.take("bad")
        ticket=self.g.take(self.token)
        self.assertEqual(ticket,self.private["ticket"])
        with self.assertRaises(PermissionError):self.g.take(self.token)
        result=run_ticket(ticket,self.root/"ledger.db",lambda _:"Draft.",approved=True)
        with self.assertRaises(PermissionError):self.g.finish("bad",result)
        receipt=self.g.finish(self.token,result)
        self.assertTrue(receipt["readback"])
        self.assertFalse(receipt["verified"])
        self.assertEqual(self.g.finish(self.token,result),receipt)
        self.assertEqual(self.q.get(self.job["id"])["attempts"],1)
        self.assertEqual(len(self.q.events(self.job["id"])),3)
    def test_reject_result_before_take_and_wrong_job(self):
        ticket=self.private["ticket"]
        result=run_ticket(ticket,self.root/"ledger.db",lambda _:"Draft.",approved=True)
        with self.assertRaises(PermissionError):self.g.finish(self.token,result)
        self.g.take(self.token)
        result["job_id"]="0"*32
        with self.assertRaises(ValueError):self.g.finish(self.token,result)
        self.assertEqual(self.q.get(self.job["id"])["state"],"running")
    def test_revocation_blocks_delivery(self):
        self.g.revoke()
        with self.assertRaises(PermissionError):self.g.take(self.token)
    def test_expiry_blocks_delivery(self):
        from unittest.mock import patch
        with patch("core.local_single_grant.time.time",return_value=self.private["ticket"]["expires_at"]):
            with self.assertRaises(PermissionError):self.g.take(self.token)

if __name__=="__main__":unittest.main()
