import unittest

from organism_lab.digital_vm import (
    COPY_REST, DIVIDE, GenomeWorld, NOP, execute_genome, genome_fingerprint,
)


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

    def test_lineage_snapshot_records_parent_genome_and_no_mutation_control(self):
        world = GenomeWorld(seed=4, resources_per_tick=20, mutation_rate=0)
        world.step()
        records = world.lineage_snapshot()
        founder = next(row for row in records if row["organism_id"] == 0)
        child = next(row for row in records if row["organism_id"] == 1)

        self.assertIsNone(founder["parent_id"])
        self.assertEqual(founder["generation"], 0)
        self.assertEqual(child["parent_id"], founder["organism_id"])
        self.assertEqual(child["generation"], 1)
        self.assertEqual(child["parent_genome_sha256"], founder["genome_sha256"])
        self.assertEqual(child["genome"], founder["genome"])
        self.assertEqual(child["mutation_count"], 0)

    def test_mutation_provenance_counts_changed_opcodes(self):
        world = GenomeWorld(seed=7, resources_per_tick=20, mutation_rate=1)
        world.step()
        records = world.lineage_snapshot()
        founder = next(row for row in records if row["organism_id"] == 0)
        child = next(row for row in records if row["organism_id"] == 1)

        changed = sum(a != b for a, b in zip(founder["genome"], child["genome"]))
        self.assertEqual(child["parent_genome_sha256"], founder["genome_sha256"])
        self.assertEqual(child["mutation_count"], changed)
        self.assertEqual(changed, len(founder["genome"]))
        self.assertNotEqual(child["genome_sha256"], founder["genome_sha256"])
        self.assertGreater(world.metrics()["unique_genomes"], 1)

    def test_genotype_and_lineage_are_seed_reproducible(self):
        a = GenomeWorld(seed=12, capacity=8, resources_per_tick=20, mutation_rate=0.4)
        b = GenomeWorld(seed=12, capacity=8, resources_per_tick=20, mutation_rate=0.4)
        for _ in range(12):
            a.step()
            b.step()
        self.assertEqual(a.lineage_snapshot(), b.lineage_snapshot())

    def test_genome_fingerprint_rejects_invalid_input(self):
        self.assertEqual(genome_fingerprint([COPY_REST, DIVIDE]),
                         genome_fingerprint((COPY_REST, DIVIDE)))
        with self.assertRaises(ValueError):
            genome_fingerprint((999,))

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
