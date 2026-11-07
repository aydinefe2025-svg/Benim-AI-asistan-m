"""Freshness and tamper regression tests for the read-only calendar watchdog."""
import json
import tempfile
import unittest
from pathlib import Path

from organism_lab.calendar_cycle import run_day
from organism_lab.calendar_health import inspect_day


class CalendarHealthTests(unittest.TestCase):
    def test_seed_and_subsequent_day_checked_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_day(root, day="2026-11-07")
            state = root / "genome-state.json"
            report = root / "daily" / "2026-11-07.json"
            before = (state.read_bytes(), report.read_bytes())
            checked = inspect_day(root, day="2026-11-07")
            self.assertEqual(checked["status"], "verified")
            self.assertEqual((checked["tick"], checked["births"], checked["population"]), (8, 3, 4))
            self.assertEqual(checked["control_births"], 0)
            self.assertEqual((state.read_bytes(), report.read_bytes()), before)
            run_day(root, day="2026-11-08")
            after = inspect_day(root, day="2026-11-08")
            self.assertEqual((after["tick"], after["births"]), (16, 13))

    def test_next_day_missing_fails_even_when_old_archive_is_valid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_day(root, day="2026-11-07")
            with self.assertRaisesRegex(ValueError, "Stale or future"):
                inspect_day(root, day="2026-11-08")

    def test_changed_report_rejected_even_if_hash_recomputed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_day(root, day="2026-11-07")
            path = root / "daily" / "2026-11-07.json"
            obj = json.loads(path.read_text(encoding="utf-8"))
            obj["observed"]["births"] = 99
            path.write_text(json.dumps(obj), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "deterministic replay"):
                inspect_day(root, day="2026-11-07")

    def test_changed_checkpoint_and_invalid_day_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_day(root, day="2026-11-07")
            with self.assertRaises(ValueError):
                inspect_day(root, day="2026-11-06")
            path = root / "genome-state.json"
            obj = json.loads(path.read_text(encoding="utf-8"))
            obj["state"]["metrics"]["births"] = 999
            path.write_text(json.dumps(obj), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                inspect_day(root, day="2026-11-07")


if __name__ == "__main__":
    unittest.main()
