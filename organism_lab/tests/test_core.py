import unittest
from organism_lab.core import Colony, grid_route

class ColonyTests(unittest.TestCase):
    def test_initial_roles(self):
        self.assertEqual(len(Colony.initialize().agents), 8)
    def test_spawn_generation(self):
        c = Colony.initialize()
        self.assertEqual(c.spawn("robotics-0").generation, 1)
        self.assertEqual(len(c.agents), 9)
    def test_population_cap(self):
        c = Colony.initialize()
        c.maximum_agents = 8
        with self.assertRaises(RuntimeError):
            c.spawn("code-0")
    def test_assignment(self):
        c = Colony.initialize()
        self.assertEqual(c.assign("research", "Explore")["status"], "queued")
    def test_invalid_task(self):
        with self.assertRaises(ValueError):
            Colony.initialize().assign("research", "")
    def test_route(self):
        route = grid_route(4, 4, (0, 0), (3, 3), [(1, 0)])
        self.assertEqual(route[0], (0, 0))
        self.assertEqual(route[-1], (3, 3))
        self.assertEqual(len(route), 7)
    def test_unreachable(self):
        self.assertIsNone(grid_route(2, 2, (0, 0), (1, 1), [(0, 1), (1, 0)]))

if __name__ == "__main__":
    unittest.main()
