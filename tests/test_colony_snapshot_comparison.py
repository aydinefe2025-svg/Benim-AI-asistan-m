import unittest

from core.colony_panel import snapshots_match


class SnapshotComparisonTests(unittest.TestCase):
    def test_row_order_does_not_change_snapshot_identity(self):
        left = {"agents": [{"id": "b", "role": "review"}, {"id": "a", "role": "plan"}],
                "missions": [], "feedback": [], "reviews": []}
        right = {"reviews": [], "feedback": [], "missions": [],
                 "agents": [{"role": "plan", "id": "a"}, {"role": "review", "id": "b"}]}
        self.assertTrue(snapshots_match(left, right))

    def test_real_snapshot_changes_are_detected(self):
        saved = {"agents": [{"id": "a", "role": "plan"}],
                 "missions": [], "feedback": [], "reviews": []}
        changed = {"agents": [{"id": "a", "role": "review"}],
                   "missions": [], "feedback": [], "reviews": []}
        self.assertFalse(snapshots_match(saved, changed))
        self.assertFalse(snapshots_match(saved, {**saved, "missions": [{"id": "m1"}]}))


if __name__ == "__main__":
    unittest.main()
