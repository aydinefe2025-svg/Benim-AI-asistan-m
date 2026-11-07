"""Owner-scoped, fail-closed CAS checkpoint for CANO evidence page."""
import unittest
from pathlib import Path

from core.cano_owner_checkpoint import (
    bind_restored_owner_baseline, save_owner_checkpoint,
)

OLD = {"agents": [{"id": "a"}], "feedback": [], "reviews": []}
NEW = {"agents": [{"id": "a"}, {"id": "b"}], "feedback": [], "reviews": []}
OTHER = {"agents": [{"id": "a"}, {"id": "c"}], "feedback": [], "reviews": []}


class FakeStore:
    def __init__(self, live=OLD):
        self.live = live
        self.calls = []

    def load(self, owner):
        self.calls.append(("load", owner))
        return self.live

    def save_versioned_verified(self, owner, payload, *, expected_prior,
                              archive_prior=True):
        self.calls.append(("save", owner, expected_prior, archive_prior))
        if expected_prior != self.live:
            raise RuntimeError("Stale owner backup")
        self.live = payload


class EvidenceCheckpointTests(unittest.TestCase):
    def state(self, owner="owner-A", expected=OLD):
        return {"_cano_backup_owner_key": owner,
                "_cano_backup_expected": expected}

    def test_rejects_missing_or_other_owner_provenance_without_writing(self):
        store = FakeStore()
        for state in ({}, {"_cano_backup_owner_key": "owner-A"},
                      self.state(owner="owner-B")):
            with self.subTest(state=state), self.assertRaises(RuntimeError):
                save_owner_checkpoint(store, "owner-A", state, NEW)
        self.assertEqual(store.calls, [])

    def test_success_updates_baseline_only_after_verified_write(self):
        store = FakeStore()
        state = self.state()
        save_owner_checkpoint(store, "owner-A", state, NEW, archive_prior=False)
        self.assertEqual(store.calls, [("save", "owner-A", OLD, False)])
        self.assertEqual(store.live, NEW)
        self.assertEqual(state["_cano_backup_expected"], NEW)

    def test_stale_tab_cannot_overwrite_newer_server_snapshot(self):
        store = FakeStore(live=OTHER)
        state = self.state(expected=OLD)
        with self.assertRaises(RuntimeError):
            save_owner_checkpoint(store, "owner-A", state, NEW)
        self.assertEqual(store.live, OTHER)
        self.assertEqual(state["_cano_backup_expected"], OLD)

    def test_restore_binds_latest_owner_baseline_without_writing(self):
        store = FakeStore(live=NEW)
        state = {}
        got = bind_restored_owner_baseline(store, "owner-A", state)
        self.assertEqual(got, NEW)
        self.assertEqual(state, self.state(expected=NEW))
        self.assertEqual(store.calls, [("load", "owner-A")])

    def test_account_switch_prevents_baseline_rebinding(self):
        store = FakeStore()
        state = self.state(owner="owner-B")
        with self.assertRaises(PermissionError):
            bind_restored_owner_baseline(store, "owner-A", state)
        self.assertEqual(store.calls, [])
        self.assertEqual(state["_cano_backup_owner_key"], "owner-B")

    def test_missing_restore_backup_does_not_bind_owner(self):
        store = FakeStore(live=None)
        state = {}
        with self.assertRaises(RuntimeError):
            bind_restored_owner_baseline(store, "owner-A", state)
        self.assertEqual(state, {})

    def test_page_must_use_checkpoint_guard_in_both_saves(self):
        page = (Path(__file__).resolve().parents[1]
                / "pages" / "01_CANO_Kaynak_Denetimi.py").read_text(encoding="utf-8")
        self.assertIn("from core.cano_owner_checkpoint import", page)
        # Additional safe checkpoint call sites may be added as the page grows.
        self.assertGreaterEqual(page.count("save_owner_checkpoint("), 10)
        self.assertIn("bind_restored_owner_baseline(", page)
        self.assertNotIn("store.save_versioned_verified(owner,", page)


if __name__ == "__main__":
    unittest.main()
