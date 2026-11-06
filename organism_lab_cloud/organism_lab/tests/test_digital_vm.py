import unittest

from organism_lab.digital_vm import COPY_REST, DIVIDE, GenomeWorld, NOP, execute_genome


class DigitalVMTests(unittest.TestCase):
    def test_self_copying_instruction_sequence(self):
        self.assertEqual(execute_genome((COPY_REST, DIVIDE)), (COPY_REST, DIVIDE))

    def test_incomplete_program_cannot_reproduce(self):
        self.assertIsNone(execute_genome((COPY_REST, NOP)))
        self.assertIsNone(execute_genome((DIVIDE,)))

    def test_mutation_can_disable_descendant_replication(self):
        world = GenomeWorld(seed=3, mutation_rate=1)
        for _ in range(3):
            world.step()
        self.assertGreater(world.births, 0)
        self.assertTrue(any(execute_genome(item.genome) is None for item in world.organisms))

    def test_control_does_not_divide(self):
        world = GenomeWorld(seed=1, resources_per_tick=20, allow_replication=False)
        for _ in range(30):
            world.step()
        self.assertEqual(world.births, 0)
        self.assertLessEqual(len(world.organisms), 1)

    def test_population_is_bounded_and_runs_are_repeatable(self):
        a = GenomeWorld(seed=9, capacity=5, resources_per_tick=100)
        b = GenomeWorld(seed=9, capacity=5, resources_per_tick=100)
        for _ in range(30):
            self.assertEqual(a.step(), b.step())
            self.assertLessEqual(len(a.organisms), 5)

    def test_invalid_world_boundaries_rejected(self):
        for kwargs in ({"capacity": 0}, {"resources_per_tick": -1},
                       {"mutation_rate": 1.1}, {"mutation_rate": True},
                       {"initial_genome": (DIVIDE,)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                GenomeWorld(**kwargs)


if __name__ == "__main__":
    unittest.main()
