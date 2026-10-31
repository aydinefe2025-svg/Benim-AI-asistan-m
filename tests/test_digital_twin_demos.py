"""Small, transparent virtual demos; never actuate hardware or grow cells."""
import unittest
from core.digital_twin_demos import move_grid_robot, life_step


class DigitalTwinTests(unittest.TestCase):
    def test_robot_moves_without_obstacle_and_stops_at_collision(self):
        result = move_grid_robot((0, 0), [(1, 0), (1, 0)], width=3, height=3,
                                 obstacles={(2, 0)})
        self.assertEqual(result["position"], (1, 0))
        self.assertEqual(result["successful_steps"], 1)
        self.assertEqual(result["blocked_steps"], 1)
        self.assertFalse(result["physical_robot_controlled"])

    def test_robot_cannot_leave_grid(self):
        result = move_grid_robot((0, 0), [(-1, 0)], width=2, height=2)
        self.assertEqual(result["position"], (0, 0))
        self.assertEqual(result["blocked_steps"], 1)

    def test_binary_cellular_automaton_blinker_pattern(self):
        before = {(1, 0), (1, 1), (1, 2)}
        after = life_step(before, width=3, height=3)
        self.assertEqual(after, {(0, 1), (1, 1), (2, 1)})
        self.assertEqual(life_step(after, width=3, height=3), before)

    def test_invalid_parameters_rejected(self):
        with self.assertRaises(ValueError):
            move_grid_robot((0, 0), [(1, 0)], width=0, height=4)
        with self.assertRaises(ValueError):
            life_step({(6, 2)}, width=4, height=4)


if __name__ == "__main__":
    unittest.main()
