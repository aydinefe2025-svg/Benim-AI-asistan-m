"""Tests for bounded digital-organism simulation (no networking or real replication)."""
import unittest

from core.digital_organism import DigitalHabitat, Organism


class DigitalOrganismTests(unittest.TestCase):
    def test_spawn_requires_permission_and_finite_resources(self):
        habitat = DigitalHabitat(allowed_zones={"sandbox"}, capacity=3, energy=4)
        parent = habitat.seed("sandbox")
        child = habitat.spawn(parent.id, zone="sandbox", approved=True)
        self.assertEqual(child.parent_id, parent.id)
        self.assertEqual(child.generation, 1)
        self.assertEqual(len(habitat.population), 2)
        self.assertEqual(habitat.energy, 2)
        self.assertTrue(habitat.audit_log[-1]["event"] == "spawn")

    def test_rejects_unapproved_zone_and_unapproved_spawn_without_mutation(self):
        habitat = DigitalHabitat(allowed_zones={"sandbox"}, capacity=5, energy=10)
        parent = habitat.seed("sandbox")
        before = (len(habitat.population), habitat.energy)
        with self.assertRaises(PermissionError):
            habitat.spawn(parent.id, zone="external-network", approved=True)
        with self.assertRaises(PermissionError):
            habitat.spawn(parent.id, zone="sandbox", approved=False)
        self.assertEqual((len(habitat.population), habitat.energy), before)

    def test_population_and_energy_bounds_prevent_runaway_replication(self):
        habitat = DigitalHabitat(allowed_zones={"sandbox"}, capacity=2, energy=10)
        parent = habitat.seed("sandbox")
        habitat.spawn(parent.id, zone="sandbox", approved=True)
        with self.assertRaises(RuntimeError):
            habitat.spawn(parent.id, zone="sandbox", approved=True)
        small = DigitalHabitat(allowed_zones={"sandbox"}, capacity=5, energy=1)
        founder = small.seed("sandbox")
        with self.assertRaises(RuntimeError):
            small.spawn(founder.id, zone="sandbox", approved=True)
        self.assertEqual(len(small.population), 1)

    def test_stop_switch_blocks_all_new_growth(self):
        habitat = DigitalHabitat(allowed_zones={"sandbox"}, capacity=5, energy=10)
        founder = habitat.seed("sandbox")
        habitat.stop()
        with self.assertRaises(RuntimeError):
            habitat.spawn(founder.id, zone="sandbox", approved=True)
        self.assertFalse(habitat.running)

    def test_no_automatic_spawn_and_bounded_lineage(self):
        habitat = DigitalHabitat(allowed_zones={"sandbox"}, capacity=4, energy=20, max_generation=1)
        founder = habitat.seed("sandbox")
        child = habitat.spawn(founder.id, zone="sandbox", approved=True)
        with self.assertRaises(RuntimeError):
            habitat.spawn(child.id, zone="sandbox", approved=True)
        self.assertEqual(len(habitat.population), 2)
        self.assertEqual([x["event"] for x in habitat.audit_log], ["seed", "spawn"])

    def test_invalid_configuration_fails_closed(self):
        with self.assertRaises(ValueError):
            DigitalHabitat(allowed_zones=set(), capacity=5, energy=10)
        with self.assertRaises(ValueError):
            DigitalHabitat(allowed_zones={"sandbox"}, capacity=0, energy=10)


if __name__ == "__main__":
    unittest.main()
