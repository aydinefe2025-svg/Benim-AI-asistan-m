"""Regression tests for scheduled, finite digital genome replication."""
import json
import tempfile
import unittest
from pathlib import Path

from organism_lab.calendar_cycle import _day_and_tick, run_day
from organism_lab.genome_checkpoint import read_checkpoint


class CalendarCycleTests(unittest.TestCase):
    def test_restart_advances_not_resets_and_control_never_divides(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first = run_day(root, day="2026-11-07")
            self.assertEqual(first["tick"], 8)
            self.assertGreater(first["observed"]["births"], 0)
            self.assertEqual(first["division_disabled_control"]["births"], 0)
            later = run_day(root, day="2026-11-08")
            self.assertEqual(later["tick"], 16)
            self.assertLessEqual(later["observed"]["population"], 24)
            self.assertEqual(read_checkpoint(root / "genome-state.json")["ticks"], 16)
            self.assertTrue((root / "daily" / "2026-11-07.json").exists())
            self.assertTrue((root / "daily" / "2026-11-08.json").exists())

    def test_same_day_double_run_does_not_change_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a = run_day(root, day="2026-11-07")
            saved_state = (root / "genome-state.json").read_bytes()
            saved_report = (root / "daily" / "2026-11-07.json").read_bytes()
            b = run_day(root, day="2026-11-07")
            self.assertEqual(a, b)
            self.assertEqual(saved_state, (root / "genome-state.json").read_bytes())
            self.assertEqual(saved_report, (root / "daily" / "2026-11-07.json").read_bytes())

    def test_prior_day_verifies_existing_record_without_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first = run_day(root, day="2026-11-07")
            run_day(root, day="2026-11-09")
            state = (root / "genome-state.json").read_bytes()
            self.assertEqual(run_day(root, day="2026-11-07"), first)
            self.assertEqual((root / "genome-state.json").read_bytes(), state)

    def test_tampered_daily_report_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run_day(root, day="2026-11-07")
            path = root / "daily" / "2026-11-07.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["observed"]["births"] = 9999
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs"):
                run_day(root, day="2026-11-07")

    def test_tampered_checkpoint_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run_day(root, day="2026-11-07")
            path = root / "genome-state.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["ticks"] = 900
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                run_day(root, day="2026-11-08")

    def test_invalid_day_and_resource_horizon(self):
        for invalid in ("2026-11-06", "2026-11-7", "2099-01-01", "not-a-date", "2026-02-30"):
            with self.subTest(day=invalid):
                with self.assertRaises(ValueError):
                    _day_and_tick(invalid)


if __name__ == "__main__":
    unittest.main()