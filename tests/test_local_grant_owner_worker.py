import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from core.authorized_queue import AuthorizedQueue
from core.local_task_handoff import claim_ticket, accept_result

class OwnerBridgeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("core.local_grant_owner"),"owner grant gate absent")
        self.assertIsNotNone(importlib.util.find_spec("core.local_grant_worker"),"network worker absent")
        from core import local_grant_owner, local_grant_worker
        self.owner,self.worker=local_grant_owner,local_grant_worker
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.q=AuthorizedQueue(Path(self.tmp.name)/"queue.db",owner_key="owner-a")
        self.q.enqueue("one","12 x 7?",approved=True)
    def test_disabled_wrong_owner_unapproved_do_not_issue(self):
        with patch.object(self.owner.PostgresLocalGrant,"issue") as issue:
            for env,owner,approved in [({}, "owner-a",True),({"CANO_LOCAL_GRANT_ENABLED":"1"},"other",True),({"CANO_LOCAL_GRANT_ENABLED":"1"},"owner-a",False)]:
                with self.assertRaises(PermissionError):
                    self.owner.issue_for_owner(self.q,owner_key=owner,environment=env,approved=approved)
            issue.assert_not_called()
            self.assertEqual(self.q.list()[0]["state"],"queued")
    def test_authorized_owner_delegates_explicitly(self):
        env={"CANO_LOCAL_GRANT_ENABLED":"1"}
        with patch.object(self.owner.PostgresLocalGrant,"issue",return_value={"id":"sample"}) as issue:
            self.assertEqual(self.owner.issue_for_owner(self.q,owner_key="owner-a",environment=env,approved=True),{"id":"sample"})
            issue.assert_called_once_with(self.q,approved=True)
        with patch.object(self.owner.PostgresLocalGrant,"revoke") as revoke:
            with self.assertRaises(PermissionError):
                self.owner.revoke_for_owner(self.q,"sample",owner_key="other",approved=True)
            revoke.assert_not_called()
    def test_worker_single_model_call_and_verified_readback(self):
        private=claim_ticket(self.q,approved=True)
        client=Mock()
        client.take.return_value=private["ticket"]
        client.finish.side_effect=lambda token,result: accept_result(self.q,private,result,approved=True)
        calls=[]
        callback=lambda goal: calls.append(goal) or "12 x 7 = 84."
        receipt=self.worker.run_once(client,"test-grant",Path(self.tmp.name)/"ledger.db",callback,approved=True)
        self.assertTrue(receipt["readback"])
        self.assertFalse(receipt["verified"])
        self.assertEqual(calls,["12 x 7?"])
        client.take.assert_called_once()
        client.finish.assert_called_once()
    def test_no_approval_and_uncertain_submission_do_not_retry(self):
        client=Mock()
        with self.assertRaises(PermissionError):
            self.worker.run_once(client,"test-grant",Path(self.tmp.name)/"ledger.db",lambda _:"draft")
        client.take.assert_not_called()
        private=claim_ticket(self.q,approved=True)
        client.take.return_value=private["ticket"]
        client.finish.side_effect=RuntimeError("network uncertain")
        calls=[]
        with self.assertRaises(RuntimeError):
            self.worker.run_once(client,"test-grant",Path(self.tmp.name)/"ledger.db",lambda g:calls.append(g) or "draft",approved=True)
        self.assertEqual(len(calls),1)
        client.finish.assert_called_once()

if __name__=="__main__":unittest.main()
