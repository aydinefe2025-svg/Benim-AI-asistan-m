import tempfile
import json
import unittest
from pathlib import Path
from core.agent_colony import AgentColony
from core.colony_restore import restore_empty_colony, restore_colony_json_bytes
from core import colony_restore
from core.collaborative_mission import CollaborativeMission


class RestoreTests(unittest.TestCase):
    def test_restore_readback_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            colony = AgentColony(Path(directory) / "colony.sqlite3")
            data = {"agents": [
                {"id":"parent","parent_id":None,"generation":0,"role":"research",
                 "instructions":"Research","state":"active","created_at":"2026-01-01"},
                {"id":"child","parent_id":"parent","generation":1,"role":"review",
                 "instructions":"Review","state":"active","created_at":"2026-01-02"}],
                "feedback": [], "reviews": []}
            self.assertEqual(restore_empty_colony(colony, data), 2)
            self.assertEqual(colony.get("child")["parent_id"], "parent")
            with self.assertRaises(RuntimeError):
                restore_empty_colony(colony, data)
            self.assertEqual(colony.get("parent")["role"], "research")

    def test_mission_snapshot_restores_and_reads_back(self):
        with tempfile.TemporaryDirectory() as directory:
            first = AgentColony(Path(directory) / "source.sqlite3")
            founder = first.create_founder("research", "Research")
            reviewer = first.spawn(founder, "evidence-reviewer", "Review", approved=True)
            first_missions = CollaborativeMission(first)
            class FakeClient:
                def __init__(self): self.calls = 0
                def chat(self, model, system, prompt):
                    self.calls += 1
                    return "stage-" + str(self.calls)
            record = first_missions.execute("Safe factual test",
                                            client=FakeClient(), model="fake")
            first_missions.mark_reviewed(record["id"], approved=True)
            with first._db() as db:
                snapshot = {
                    "agents": [dict(x) for x in db.execute("SELECT * FROM colony_agents")],
                    "feedback": [dict(x) for x in db.execute("SELECT * FROM colony_feedback")],
                    "reviews": [],
                    "missions": [dict(x) for x in db.execute("SELECT * FROM colony_missions")],
                }
            target = AgentColony(Path(directory) / "restored.sqlite3")
            self.assertEqual(restore_empty_colony(target, snapshot), 2)
            restored = CollaborativeMission(target).get(record["id"])
            self.assertEqual(restored["task"], record["task"])
            self.assertEqual(restored["stages"], record["stages"])
            self.assertEqual(restored["status"], "reviewed")
            with self.assertRaises(RuntimeError):
                restore_empty_colony(target, snapshot)

    def test_invalid_mission_prevents_partial_restoration(self):
        with tempfile.TemporaryDirectory() as directory:
            target = AgentColony(Path(directory) / "target.sqlite3")
            snapshot = {
                "agents": [{
                    "id": "founder", "parent_id": None, "generation": 0,
                    "role": "research", "instructions": "Research",
                    "state": "active", "created_at": "2026-01-01"}],
                "feedback": [], "reviews": [],
                "missions": [{
                    "id": "mission1", "task": "Check", "stages":
                    json.dumps([{"role": "planner", "agent_id": "missing", "output": "x"}]),
                    "status": "review_pending", "created_at": "2026-01-01"}],
            }
            with self.assertRaises(ValueError):
                restore_empty_colony(target, snapshot)
            with target._db() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM colony_agents").fetchone()[0], 0)

    def test_partial_mission_restores_blocked_and_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = AgentColony(Path(directory) / "source.db")
            founder = source.create_founder("research", "Research")
            source.spawn(founder, "evidence-reviewer", "Review", approved=True)
            missions = CollaborativeMission(source)
            class FailSecond:
                def __init__(self): self.calls = 0
                def chat(self, model, system, prompt):
                    self.calls += 1
                    if self.calls == 2:
                        raise RuntimeError("Provider interrupted")
                    return "stage-" + str(self.calls)
            with self.assertRaises(RuntimeError):
                missions.execute("Safe test", client=FailSecond(), model="fake")
            with source._db() as db:
                snapshot = {
                    "agents": [dict(r) for r in db.execute("SELECT * FROM colony_agents")],
                    "feedback": [], "reviews": [],
                    "missions": [dict(r) for r in db.execute("SELECT * FROM colony_missions")],
                }
            self.assertEqual(snapshot["missions"][0]["status"], "blocked")
            target = AgentColony(Path(directory) / "restored.db")
            self.assertEqual(restore_empty_colony(target, snapshot), 2)
            saved = CollaborativeMission(target).get(snapshot["missions"][0]["id"])
            self.assertEqual(len(saved["stages"]), 1)
            class Fake:
                def __init__(self): self.calls = 0
                def chat(self, model, system, prompt):
                    self.calls += 1
                    return "continued-" + str(self.calls)
            client = Fake()
            resumed = CollaborativeMission(target).resume(saved["id"], client=client,
                                                           model="fake")
            self.assertEqual(resumed["model_calls"], 3)
            self.assertEqual(client.calls, 3)
            self.assertEqual(resumed["stages"][0]["output"], "stage-1")

    def test_imported_running_mission_becomes_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            target = AgentColony(Path(directory) / "restored.db")
            snapshot = {
                "agents": [{
                    "id": "founder", "parent_id": None, "generation": 0,
                    "role": "research", "instructions": "Research",
                    "state": "active", "created_at": "2026-01-01"}],
                "feedback": [], "reviews": [],
                "missions": [{"id": "run1", "task": "Research", "stages": "[]",
                              "status": "running", "created_at": "2026-01-01"}]
            }
            self.assertEqual(restore_empty_colony(target, snapshot), 1)
            self.assertEqual(CollaborativeMission(target).get("run1")["status"],
                             "blocked")

    def test_json_upload_round_trip_preserves_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            colony = AgentColony(Path(directory) / "restored.db")
            record = {
                "agents": [{
                    "id": "founder", "parent_id": None, "generation": 0,
                    "role": "research", "instructions": "Research",
                    "state": "active", "created_at": "2026-01-01"}],
                "feedback": [], "reviews": [], "missions": []
            }
            payload = json.dumps(record, ensure_ascii=False).encode("utf-8")
            self.assertEqual(restore_colony_json_bytes(colony, payload), 1)
            self.assertEqual(colony.get("founder")["role"], "research")
            with self.assertRaises(RuntimeError):
                restore_colony_json_bytes(colony, payload)
            self.assertEqual(colony.get("founder")["role"], "research")

    def test_json_import_rejects_invalid_utf8_invalid_json_and_oversize(self):
        with tempfile.TemporaryDirectory() as directory:
            colony = AgentColony(Path(directory) / "restored.db")
            for payload in (b"not json", bytes([255]), b"[]",
                            b"x" * (2_000_000 + 1), "not bytes"):
                with self.subTest(payload=str(payload)[:20]):
                    with self.assertRaises(ValueError):
                        restore_colony_json_bytes(colony, payload)
            with colony._db() as db:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM colony_agents").fetchone()[0], 0)

    def test_reject_missing_parent_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            colony = AgentColony(Path(directory) / "colony.sqlite3")
            bad = {"agents":[{"id":"a","parent_id":"missing","generation":1,
                   "role":"research","instructions":"Research","state":"active",
                   "created_at":"2026-01-01"}],"feedback":[],"reviews":[]}
            with self.assertRaises(ValueError):
                restore_empty_colony(colony, bad)
            with colony._db() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM colony_agents").fetchone()[0],0)


    def test_db_mutation_during_import_causes_rollback(self):
        """A trigger-induced mismatch must not leave a partially restored colony."""
        with tempfile.TemporaryDirectory() as directory:
            colony = AgentColony(Path(directory) / "colony.db")
            with colony._db() as db:
                db.execute("""CREATE TRIGGER corrupt_restore AFTER INSERT ON colony_agents
                    BEGIN UPDATE colony_agents SET role='corrupted' WHERE id=NEW.id; END""")
            snapshot = {"agents": [{
                "id": "founder", "parent_id": None, "generation": 0,
                "role": "research", "instructions": "Safe", "state": "active",
                "created_at": "2026-01-01"}],
                "feedback": [], "reviews": [], "missions": []}
            with self.assertRaisesRegex(RuntimeError, "readback mismatch"):
                restore_empty_colony(colony, snapshot)
            with colony._db() as db:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM colony_agents").fetchone()[0], 0)

    def test_owner_backup_requires_explicit_confirmation_before_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            colony = AgentColony(Path(directory) / "colony.db")
            class FakeStore:
                def __init__(self): self.lookups = []
                def load(self, owner):
                    self.lookups.append(owner)
                    return {"agents": [{
                        "id": "owner-agent", "parent_id": None, "generation": 0,
                        "role": "research", "instructions": "Safe",
                        "state": "active", "created_at": "2026-01-01"}],
                        "feedback": [], "reviews": [], "missions": []}
            store = FakeStore()
            with self.assertRaises(PermissionError):
                colony_restore.restore_owner_backup(colony, store, "owner-123", approved=False)
            self.assertEqual(store.lookups, [])
            with self.assertRaises(ValueError):
                colony_restore.restore_owner_backup(colony, store, " ", approved=True)
            self.assertEqual(store.lookups, [])
            self.assertEqual(colony_restore.restore_owner_backup(
                colony, store, "owner-123", approved=True), 1)
            self.assertEqual(store.lookups, ["owner-123"])
            self.assertEqual(colony.get("owner-agent")["role"], "research")
            with self.assertRaises(RuntimeError):
                colony_restore.restore_owner_backup(colony, store, "owner-123", approved=True)

    def test_incomplete_legacy_mission_is_archived_before_safe_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            colony = AgentColony(Path(directory) / "colony.db")
            original = {
                "agents": [{
                    "id": "owner-agent", "parent_id": None, "generation": 0,
                    "role": "research", "instructions": "Safe",
                    "state": "active", "created_at": "2026-01-01"}],
                "feedback": [], "reviews": [],
                "missions": [{"id": "old-mission", "status": "review_pending"}],
            }
            class VersionedStore:
                def __init__(self):
                    self.current = original
                    self.revisions = []
                def load(self, owner):
                    return self.current
                def save_versioned_verified(self, owner, payload, *,
                                             expected_prior, archive_prior):
                    self.assert_owner = owner
                    self.assert_prior = expected_prior
                    self.assert_archived = archive_prior
                    self.revisions.append(self.current)
                    self.current = payload
            store = VersionedStore()
            result = colony_restore.restore_owner_backup(
                colony, store, "owner-123", approved=True,
                archive_incomplete_missions=True)
            self.assertEqual(result, {
                "agent_count": 1, "archived_incomplete_missions": 1})
            self.assertEqual(store.revisions, [original])
            self.assertEqual(store.assert_prior, original)
            self.assertTrue(store.assert_archived)
            self.assertEqual(store.current["missions"], [])
            self.assertEqual(colony.get("owner-agent")["role"], "research")
            with colony._db() as db:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM colony_missions").fetchone()[0], 0)

    def test_incomplete_legacy_agent_fails_before_archiving_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            colony = AgentColony(Path(directory) / "colony.db")
            original = {
                "agents": [{"id": "old-agent", "role": "research"}],
                "feedback": [], "reviews": [],
                "missions": [{"id": "old-mission", "status": "review_pending"}],
            }
            class ReadOnlyStore:
                archive_calls = 0
                def load(self, owner):
                    return original
                def save_versioned_verified(self, *args, **kwargs):
                    self.archive_calls += 1
            store = ReadOnlyStore()
            with self.assertRaisesRegex(ValueError, "Invalid agent"):
                colony_restore.restore_owner_backup(
                    colony, store, "owner-123", approved=True,
                    archive_incomplete_missions=True)
            self.assertEqual(store.archive_calls, 0)
            with colony._db() as db:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM colony_agents").fetchone()[0], 0)

    def test_missing_owner_backup_refuses_write(self):
        with tempfile.TemporaryDirectory() as directory:
            colony = AgentColony(Path(directory) / "colony.db")
            class MissingStore:
                def load(self, owner): return None
            with self.assertRaises(LookupError):
                colony_restore.restore_owner_backup(colony, MissingStore(), "owner-123",
                                     approved=True)
            with colony._db() as db:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM colony_agents").fetchone()[0], 0)

    def test_archived_revision_becomes_current_checkpoint_and_preserves_newer_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            colony = AgentColony(Path(directory) / "colony.db")
            def snapshot(agent_id, role):
                return {"agents": [{
                    "id": agent_id, "parent_id": None, "generation": 0,
                    "role": role, "instructions": "Safe",
                    "state": "active", "created_at": "2026-01-01"}],
                    "feedback": [], "reviews": [], "missions": []}
            historical = snapshot("historic-agent", "research")
            current = snapshot("new-agent", "evidence-reviewer")
            class VersionedStore:
                def __init__(self):
                    self.current = current
                    self.archived = {7: historical}
                    self.revisions = []
                def load(self, owner):
                    return self.current
                def load_archived(self, owner, revision):
                    return self.archived.get(revision)
                def save_versioned_verified(self, owner, payload, *,
                                             expected_prior, archive_prior):
                    self.assert_owner = owner
                    self.assert_prior = expected_prior
                    self.assert_archive = archive_prior
                    self.revisions.append(self.current)
                    self.current = payload
            store = VersionedStore()
            self.assertEqual(colony_restore.restore_owner_backup(
                colony, store, "owner-123", approved=True, revision=7), 1)
            self.assertEqual(colony.get("historic-agent")["role"], "research")
            self.assertEqual(store.current, historical)
            self.assertEqual(store.revisions, [current])
            self.assertEqual(store.assert_prior, current)
            self.assertTrue(store.assert_archive)


if __name__ == "__main__":
    unittest.main()
