"""Opt-in local CANO backup: roundtrip after hard refresh without user cross-talk."""
import json
import tempfile
import unittest
from pathlib import Path

from core.agent_colony import AgentColony
from core.cano_command_center import _snapshot
from core.colony_restore import restore_empty_colony
from core.browser_colony import (
    encode_browser_colony_backup, decode_browser_colony_backup,
    browser_write_confirmed,
)


class BrowserColonyTests(unittest.TestCase):
    def test_explicit_opt_in_backup_roundtrip_after_new_session(self):
        with tempfile.TemporaryDirectory() as d:
            source = AgentColony(Path(d) / "source.sqlite3")
            founder = source.create_founder("research", "Careful scientific research")
            source.grow_specialists(approved=True)
            source.feedback(founder, "Test", "Lesson", "Evidence1", accepted=True)
            original = _snapshot(source)
            write = encode_browser_colony_backup(original)
            self.assertEqual(write["token"], write["token"])  # stable deterministic token
            self.assertLess(len(write["payload"]), 1_000_001)
            self.assertTrue(browser_write_confirmed(
                {"status": "ok", "payload": write["payload"], "ack": write["token"]},
                write))
            decoded = decode_browser_colony_backup(
                {"status": "ok", "payload": write["payload"]})
            self.assertEqual(decoded, original)
            restored = AgentColony(Path(d) / "new_session.sqlite3")
            self.assertEqual(restore_empty_colony(restored, decoded), 4)
            self.assertEqual(_snapshot(restored)["agents"], original["agents"])
            self.assertEqual(_snapshot(restored)["feedback"], original["feedback"])

    def test_unavailable_or_corrupt_store_fails_closed(self):
        for report in (None, {}, {"status":"error"}, {"status":"ok","payload":""},
                       {"status":"ok","payload":"{}"},
                       {"status":"ok","payload":"{"}):
            with self.subTest(report=report):
                with self.assertRaises(ValueError):
                    decode_browser_colony_backup(report)

    def test_write_confirmation_requires_exact_payload_and_ack(self):
        write = encode_browser_colony_backup({"agents":[],"feedback":[],"reviews":[],"missions":[]})
        self.assertFalse(browser_write_confirmed(None, write))
        self.assertFalse(browser_write_confirmed(
            {"status":"ok","ack":"wrong","payload":write["payload"]}, write))
        self.assertFalse(browser_write_confirmed(
            {"status":"ok","ack":write["token"],"payload":"{}"}, write))
        self.assertTrue(browser_write_confirmed(
            {"status":"ok","ack":write["token"],"payload":write["payload"]}, write))

    def test_oversized_or_nonjson_backup_refused(self):
        oversized = {"agents":[],"feedback":[],
                     "reviews":[],"missions":[{"payload":"x"*1_050_000}]}
        with self.assertRaises(ValueError):
            encode_browser_colony_backup(oversized)
        with self.assertRaises(ValueError):
            decode_browser_colony_backup({"status":"ok", "payload":"x"*1_050_000})
        with self.assertRaises(ValueError):
            encode_browser_colony_backup({"agents":[]})

    def test_browser_backup_is_a_local_preview_not_authoritative_verification(self):
        saved = encode_browser_colony_backup(
            {"agents":[],"feedback":[],"reviews":[],"missions":[]})
        data = json.loads(saved["payload"])
        self.assertEqual(data["version"], 1)
        self.assertTrue(data["opted_in"])
        self.assertNotIn("owner_key", data)


if __name__ == "__main__":
    unittest.main()
