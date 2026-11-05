import unittest
from organism_lab.mission import run_mission

class MissionTests(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(run_mission(), run_mission())
    def test_robot_population_bounded(self):
        r = run_mission(steps=20, parts_per_kind=2)
        self.assertLessEqual(r["robot_metrics"]["robots"], 2)
    def test_mission_history(self):
        self.assertEqual(len(run_mission(steps=4)["history"]), 4)
    def test_no_inventory(self):
        self.assertEqual(run_mission(parts_per_kind=0)["robot_metrics"]["robots"], 0)
    def test_invalid_steps(self):
        with self.assertRaises(ValueError):
            run_mission(steps=-1)
    def test_path(self):
        self.assertEqual(run_mission(steps=1)["history"][0]["route_length"], 9)
