"""Deterministic, bounded 'one seed to a resilient colony' model tests."""
import json
import unittest

from core.seed_ecosystem import SeedEcosystem


class SeedEcosystemTests(unittest.TestCase):
    def test_no_growth_without_harvest_and_explicit_simulation_authorization(self):
        lab = SeedEcosystem(capacity=6)
        with self.assertRaises(PermissionError):
            lab.step({"solar": 5})
        self.assertEqual(lab.population_size, 1)
        dormant = lab.step({}, authorized=True)
        self.assertEqual(dormant["mode"], "dormant")
        self.assertEqual(lab.population_size, 1)
        self.assertEqual(lab.energy, 0)

    def test_child_can_reproduce_after_founder_is_lost(self):
        lab = SeedEcosystem(capacity=7, max_generation=5, energy_cap=24)
        for _ in range(3):
            lab.step({"solar": 8}, authorized=True)
        self.assertGreaterEqual(lab.population_size, 3)
        previous_ids = {node.id for node in lab.nodes.values()}
        lost = lab.fail_nodes((1,), authorized=True)
        self.assertEqual(lost, (1,))
        self.assertNotIn(1, lab.nodes)
        for _ in range(3):
            lab.step({"water": 8}, authorized=True)
        self.assertGreater(lab.population_size, 2)
        self.assertTrue(any(node.generation >= 2 for node in lab.nodes.values()))
        self.assertEqual(len(lab.nodes), len(set(lab.nodes)))
        self.assertTrue(any(node.id > max(previous_ids) for node in lab.nodes.values()))

    def test_multiple_sources_are_more_resilient_to_solar_outage(self):
        solar = SeedEcosystem(capacity=10, energy_cap=12)
        diversified = SeedEcosystem(capacity=10, energy_cap=12)
        solar_dormant = varied_dormant = 0
        for value in (4, 4, 4, 0, 0, 0, 4, 4):
            a = solar.step({"solar": value}, authorized=True)
            b = diversified.step(
                {"solar": value, "water": 2, "thermal": 1}, authorized=True
            )
            solar_dormant += a["mode"] == "dormant"
            varied_dormant += b["mode"] == "dormant"
        self.assertLess(varied_dormant, solar_dormant)
        self.assertGreaterEqual(diversified.population_size, solar.population_size)

    def test_finite_capacity_and_energy_budget(self):
        lab = SeedEcosystem(capacity=3, energy_cap=9)
        for _ in range(30):
            record = lab.step({"solar": 9}, authorized=True)
            self.assertLessEqual(record["energy_after"], 9)
            self.assertLessEqual(lab.population_size, 3)
        self.assertEqual(lab.population_size, 3)
        self.assertGreaterEqual(lab.discarded_energy, 0)

    def test_invalid_input_does_not_mutate_state(self):
        lab = SeedEcosystem()
        before = lab.checkpoint()
        for bad in ({"solar": -1}, {"solar": 1.5}, {"unlisted": 5}, {"solar": True}):
            with self.assertRaises(ValueError):
                lab.step(bad, authorized=True)
        self.assertEqual(before, lab.checkpoint())

    def test_equal_total_harvest_distribution_prevents_dormancy(self):
        # Same simulated total energy (44), different temporal/source profile.
        single = SeedEcosystem(capacity=10, energy_cap=12, max_generation=8)
        mixed = SeedEcosystem(capacity=10, energy_cap=12, max_generation=8)
        for tick, (a, b) in enumerate(zip(
                (9, 9, 9, 0, 0, 0, 9, 8),
                (4, 4, 4, 0, 0, 0, 4, 4)), start=1):
            if tick == 4:
                single.fail_nodes((1,), authorized=True)
                mixed.fail_nodes((1,), authorized=True)
            single.step({"solar": a}, authorized=True)
            mixed.step({"solar": b, "water": 2, "thermal": 1}, authorized=True)
        self.assertEqual(single.total_harvested, mixed.total_harvested)
        self.assertEqual(mixed.total_harvested, 44)
        self.assertEqual(single.dormant_ticks, 2)
        self.assertEqual(mixed.dormant_ticks, 0)

    def test_energy_conservation_ledger(self):
        lab = SeedEcosystem(capacity=8, energy_cap=8)
        for input_amount in (8, 8, 1, 0, 8):
            lab.step({"water": input_amount}, authorized=True)
        spent_on_maintenance = sum(r["maintenance"] for r in lab.audit)
        self.assertEqual(
            lab.total_harvested,
            spent_on_maintenance + 2 * lab.total_births
            + lab.energy + lab.discarded_energy,
        )

    def test_extinction_does_not_magically_replicate_without_seed(self):
        lab = SeedEcosystem()
        lab.fail_nodes((1,), authorized=True)
        result = lab.step({"solar": 10}, authorized=True)
        self.assertEqual(result["mode"], "extinct")
        self.assertEqual(lab.population_size, 0)

    def test_checkpoint_readback_survives_restart_and_rejects_corruption(self):
        lab = SeedEcosystem(capacity=8, max_generation=5, energy_cap=30)
        for _ in range(3):
            lab.step({"water": 8}, authorized=True)
        checkpoint = lab.checkpoint()
        loaded = SeedEcosystem.from_checkpoint(json.loads(json.dumps(checkpoint)))
        self.assertEqual(checkpoint, loaded.checkpoint())
        self.assertEqual(
            lab.step({"thermal": 6}, authorized=True),
            loaded.step({"thermal": 6}, authorized=True),
        )
        corrupted = json.loads(json.dumps(checkpoint))
        corrupted["payload"]["energy"] = 9999
        with self.assertRaises(ValueError):
            SeedEcosystem.from_checkpoint(corrupted)

    def test_unauthorized_failure_does_not_remove_nodes(self):
        lab = SeedEcosystem()
        with self.assertRaises(PermissionError):
            lab.fail_nodes((1,))
        self.assertEqual(lab.population_size, 1)


if __name__ == "__main__":
    unittest.main()
