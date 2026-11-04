"""Real PostgreSQL readback and process-restart drill for CANO missions.

Runs only against an isolated test database, never against production owner data.
A recovered source quote is explicitly unverified science.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from core.agent_colony import AgentColony
from core.claim_evidence import audit_claim_quotes
from core.collaborative_mission import CollaborativeMission
from core.colony_postgres import ColonySnapshotStore

DOI = "10.1038/nprot.2013.143"
QUOTE = "Targeted nucleases are powerful tools for genome engineering."


class DraftClient:
    def chat(self, model, system, prompt):
        return "Unverified draft: inspect retrieved source excerpt."


class QuoteClient:
    def chat(self, model, system, prompt):
        return json.dumps({"claims": [
            {"claim": "Targeted nucleases are powerful genome tools",
             "doi": DOI, "quote": QUOTE}
        ]})


def snapshot(colony):
    with colony._db() as db:
        return {key: [dict(row) for row in db.execute("SELECT * FROM " + table)]
                for key, table in (
                    ("agents", "colony_agents"),
                    ("feedback", "colony_feedback"),
                    ("reviews", "colony_reviews"),
                    ("missions", "colony_missions"),
                )}


# The runner deliberately starts a *new* Python interpreter and SQLite file
# to emulate a fresh Render process instead of reusing local in-memory state.
RESTORE_WORKER = r"""
import json
import os
import sys
from pathlib import Path
from core.agent_colony import AgentColony
from core.collaborative_mission import CollaborativeMission
from core.colony_postgres import ColonySnapshotStore
from core.colony_restore import restore_owner_backup

owner, mission_id, path = sys.argv[1:4]
store = ColonySnapshotStore(os.environ["CANO_TEST_POSTGRES_DSN"])
colony = AgentColony(Path(path))
if store.load(owner + "-other") is not None:
    raise AssertionError("Owner isolation failed")
count = restore_owner_backup(colony, store, owner, approved=True)
saved = CollaborativeMission(colony).get(mission_id)
audit = saved["stages"][0]["source_claim_audit"]
if not (count == 2 and saved["status"] == "review_pending"
        and len(saved["stages"]) == 4 and len(audit) == 1
        and audit[0]["status"] == "quote_found_unverified"
        and audit[0]["claim_verified"] is False
        and audit[0]["citation_url"].startswith("https://")):
    raise AssertionError("Restored source/claim audit differs")
print(json.dumps({"restored_agents": count,
                  "restored_missions": 1,
                  "restored_quote_status": audit[0]["status"],
                  "claimed_scientific_truth": audit[0]["claim_verified"]}))
"""


@unittest.skipUnless(os.environ.get("CANO_TEST_POSTGRES_DSN"),
                     "Real PostgreSQL CI database not configured")
class PostgresProcessRecoveryTests(unittest.TestCase):
    def test_verified_snapshot_restores_in_new_process_with_owner_isolation(self):
        dsn = os.environ["CANO_TEST_POSTGRES_DSN"]
        owner = "e2e-" + uuid.uuid4().hex
        store = ColonySnapshotStore(dsn)
        store.initialize()
        try:
            with tempfile.TemporaryDirectory() as temp:
                source = AgentColony(Path(temp) / "source.sqlite3")
                founder = source.create_founder("research", "Research")
                source.spawn(founder, "evidence-reviewer",
                             "Review sources", approved=True)
                manager = CollaborativeMission(source)
                mission = manager.execute(
                    "Read scientific DOI " + DOI,
                    client=DraftClient(), model="stub",
                    source_lookup=lambda query, limit=3: [
                        {"title": "Genome engineering",
                         "url": "https://doi.org/" + DOI}])
                manager.inspect_source_documents(
                    mission["id"], reader=lambda doi: {
                        "doi": doi, "title": "Synthetic fixture",
                        "url": "https://doi.org/" + doi,
                        "status": "abstract_excerpt",
                        "excerpt": QUOTE + " Other methods were evaluated.",
                        "claim_verified": False})
                audit = audit_claim_quotes(
                    manager, mission["id"], client=QuoteClient(), model="stub")
                self.assertEqual(audit[0]["status"], "quote_found_unverified")
                payload = snapshot(source)
                self.assertTrue(store.save_versioned_verified(owner, payload))
                self.assertEqual(store.load(owner), payload)
                self.assertIsNone(store.load(owner + "-other"))

                env = os.environ.copy()
                result = subprocess.run(
                    [sys.executable, "-c", RESTORE_WORKER, owner, mission["id"],
                     str(Path(temp) / "restored.sqlite3")],
                    cwd=str(Path(__file__).resolve().parents[1]),
                    env=env, capture_output=True, text=True, timeout=45,
                    check=True,
                )
                receipt = json.loads(result.stdout)
                self.assertEqual(receipt["restored_agents"], 2)
                self.assertEqual(receipt["restored_missions"], 1)
                self.assertFalse(receipt["claimed_scientific_truth"])
        finally:
            # This is an ephemeral CI database, but still clean up test owners.
            import psycopg
            with psycopg.connect(dsn, connect_timeout=8) as db:
                with db.cursor() as cur:
                    cur.execute(
                        "DELETE FROM private_colony_snapshot_revisions WHERE owner_key=%s",
                        (owner,))
                    cur.execute(
                        "DELETE FROM private_colony_snapshots WHERE owner_key=%s",
                        (owner,))


if __name__ == "__main__":
    unittest.main()
