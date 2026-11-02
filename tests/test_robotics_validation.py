import unittest

from core.digital_twin_demos import move_grid_robot


class RoboticsDataTests(unittest.TestCase):
    def test_invalid_start_data_rejected(self):
        for point in [(True, 0), (0.5, 0), (float('nan'), 0),
                      (float('inf'), 0), (0,), (0, 0, 1), '00', None]:
            with self.subTest(point=point), self.assertRaises(ValueError):
                move_grid_robot(point, [], width=3, height=3)

    def test_invalid_obstacle_data_rejected(self):
        for obstacle in [(True, 1), (0.5, 1), (3, 1), (0, 1, 2)]:
            with self.subTest(obstacle=obstacle), self.assertRaises(ValueError):
                move_grid_robot((0, 0), [], width=3, height=3, obstacles=[obstacle])

    def test_invalid_command_batch_rejected(self):
        for moves in [None, '10', [(True, 0)], [(1, 0), (0, 2)], [(1,)], [(1, 0, 0)]]:
            with self.subTest(moves=moves), self.assertRaises(ValueError):
                move_grid_robot((0, 0), moves, width=3, height=3)

    def test_json_arrays_normalized_without_mutating_input(self):
        start, moves, obstacles = [0, 0], [[1, 0], [0, 1]], [[1, 1]]
        result = move_grid_robot(start, moves, width=3, height=3, obstacles=obstacles)
        self.assertEqual(result['position'], (1, 0))
        self.assertEqual(result['blocked_steps'], 1)
        self.assertEqual(start, [0, 0])
        self.assertEqual(moves, [[1, 0], [0, 1]])
        self.assertTrue(result['simulation_only'])
        self.assertFalse(result['physical_robot_controlled'])
