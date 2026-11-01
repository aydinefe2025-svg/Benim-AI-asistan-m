"""Property-style invariant tests across bounded virtual-world configurations."""
import unittest
from organism_lab.shared_world import run_shared_world
from organism_lab.robot_factory import RobotFactory
from organism_lab.evolution import World

class InvariantTests(unittest.TestCase):
    def test_shared_world_conserves_budgets(self):
        for energy in (0, 1, 2, 3, 10, 40, 100):
            for materials in (0, 1, 3, 4, 8, 20):
                with self.subTest(energy=energy, materials=materials):
                    r = run_shared_world(steps=20, energy=energy, materials=materials)
                    self.assertEqual(r["materials_left"], materials - 4 * r["robots"])
                    self.assertEqual(r["energy_left"],
                                     energy - 2 * r["robots"] - 3 * r["births"]
                                     - 8 * r["successful_routes"])
                    self.assertGreaterEqual(r["energy_left"], 0)
                    self.assertGreaterEqual(r["materials_left"], 0)
                    self.assertLessEqual(r["organisms"], 32)
    def test_factory_inventory_never_negative(self):
        for count in range(5):
            f = RobotFactory(parts={part: count for part in RobotFactory.REQUIRED},
                             max_robots=10)
            parent = f.assemble()
            if parent is not None:
                for _ in range(12):
                    f.replicate(parent.identifier)
            self.assertEqual(len(f.robots), count)
            self.assertTrue(all(v == 0 for v in f.parts.values()))
    def test_evolution_population_and_lineage(self):
        for seed in range(10):
            world = World(seed=seed, capacity=16, resources=8)
            known = {0}
            for _ in range(40):
                world.step()
                self.assertLessEqual(len(world.organisms), 16)
                self.assertEqual(len({o.id for o in world.organisms}), len(world.organisms))
                for o in world.organisms:
                    self.assertGreater(o.energy, 0)
                    self.assertGreaterEqual(o.efficiency, 1)
                    if o.parent is not None:
                        self.assertLess(o.parent, o.id)
                    known.add(o.id)
            self.assertEqual(world.births + 1, len(known))

if __name__ == "__main__":
    unittest.main()
