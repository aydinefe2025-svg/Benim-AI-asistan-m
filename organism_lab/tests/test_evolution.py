import unittest
from organism_lab.evolution import World

class EvolutionTests(unittest.TestCase):
    def test_reproducible(self):
        a, b = World(seed=12), World(seed=12)
        self.assertEqual([a.step() for _ in range(10)], [b.step() for _ in range(10)])
    def test_births_and_lineage(self):
        w = World(seed=1, resources=20)
        for _ in range(10):
            w.step()
        self.assertGreater(w.births, 0)
        self.assertTrue(any(o.parent is not None and o.generation > 0 for o in w.organisms))
    def test_capacity(self):
        w = World(seed=1, capacity=3, resources=50)
        for _ in range(30):
            self.assertLessEqual(w.step()["population"], 3)
    def test_no_resources(self):
        w = World(resources=0)
        for _ in range(10):
            w.step()
        self.assertEqual(len(w.organisms), 0)
    def test_invalid_config(self):
        with self.assertRaises(ValueError):
            World(capacity=0)
