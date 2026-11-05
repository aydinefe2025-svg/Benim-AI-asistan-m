import unittest
from organism_lab.robot_factory import RobotFactory

class RobotFactoryTests(unittest.TestCase):
    def test_assembly(self):
        f = RobotFactory()
        r = f.assemble()
        self.assertEqual(r.generation, 0)
        self.assertEqual(len(r.modules), 4)
    def test_replication(self):
        f = RobotFactory()
        parent = f.assemble()
        child = f.replicate(parent.identifier)
        self.assertEqual(child.parent, parent.identifier)
        self.assertEqual(child.generation, 1)
    def test_part_depletion(self):
        f = RobotFactory(parts={part: 1 for part in RobotFactory.REQUIRED})
        self.assertIsNotNone(f.assemble())
        self.assertIsNone(f.assemble())
    def test_capacity(self):
        f = RobotFactory(max_robots=1)
        parent = f.assemble()
        self.assertIsNone(f.replicate(parent.identifier))
    def test_invalid_parent(self):
        with self.assertRaises(KeyError):
            RobotFactory().replicate(10)
    def test_invalid_inventory(self):
        with self.assertRaises(ValueError):
            RobotFactory(parts={"wheel": -1})
