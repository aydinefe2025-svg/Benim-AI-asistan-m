"""Static guardrails for both daily cron windows; not proof of a scheduled run."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CALENDAR = ROOT / ".github/workflows/cano-digital-organism-calendar.yml"
WATCHDOG = ROOT / ".github/workflows/cano-digital-calendar-watchdog.yml"


def crons(text):
    return re.findall(r"^\s*- cron: ['\"]([^'\"]+)['\"]", text, flags=re.MULTILINE)


class CalendarScheduleReliabilityTests(unittest.TestCase):
    def test_two_distinct_calendar_attempts_before_watchdog(self):
        self.assertEqual(crons(CALENDAR.read_text(encoding="utf-8")),
                         ["47 5 * * *", "31 7 * * *"])

    def test_two_read_only_watchdog_attempts(self):
        data = WATCHDOG.read_text(encoding="utf-8")
        self.assertEqual(crons(data), ["17 8 * * *", "43 9 * * *"])
        self.assertIn("python -m organism_lab.calendar_health", data)
        self.assertNotIn("git push", data)
        self.assertNotIn("contents: write", data)

    def test_calendar_idempotence_lock_and_remote_verification(self):
        data = CALENDAR.read_text(encoding="utf-8")
        self.assertIn("group: cano-bounded-organism-calendar-cycle", data)
        self.assertIn("cancel-in-progress: false", data)
        self.assertEqual(data.count("python -m organism_lab.calendar_cycle --state-dir"), 2)
        self.assertGreaterEqual(data.count("python -m organism_lab.calendar_health"), 2)
        self.assertIn('git worktree add --detach "$RUNNER_TEMP/cano-check-remote"', data)
        self.assertIn("STATE_BRANCH: experiment/cano-digital-state-20261107", data)
        self.assertIn('git push origin "HEAD:refs/heads/', data)
        self.assertNotIn("--force", data)
        self.assertNotIn("force-with-lease", data)

    def test_watchdog_is_after_last_backup(self):
        def minutes(cron):
            m, h = map(int, cron.split()[:2])
            return h * 60 + m
        self.assertLess(max(map(minutes, crons(CALENDAR.read_text(encoding="utf-8")))),
                        min(map(minutes, crons(WATCHDOG.read_text(encoding="utf-8")))))


if __name__ == "__main__":
    unittest.main()
