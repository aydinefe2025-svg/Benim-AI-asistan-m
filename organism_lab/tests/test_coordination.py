import unittest
from organism_lab.core import Colony
from organism_lab.coordination import execute_task, grow_on_demand

class CoordinationTests(unittest.TestCase):
    def test_verified_task(self):
        colony = Colony.initialize()
        result = execute_task(colony, "research", "summarize", lambda task: "finding", lambda task, output: "checked")
        self.assertEqual(result.status, "checked")
        self.assertEqual(colony.audit[-1]["evidence"], "checked")
    def test_missing_evidence_is_failure(self):
        result = execute_task(Colony.initialize(), "code", "test", lambda task: "done", lambda task, output: "")
        self.assertEqual(result.status, "failed")
    def test_executor_exception_is_failure(self):
        def fail(task):
            raise RuntimeError("unavailable")
        result = execute_task(Colony.initialize(), "code", "test", fail, lambda task, output: "yes")
        self.assertEqual(result.status, "failed")
    def test_growth_under_load(self):
        colony = Colony.initialize()
        child = grow_on_demand(colony, "research", queued_tasks=4)
        self.assertEqual(child.role, "research")
        self.assertEqual(child.generation, 1)
    def test_no_growth_without_demand(self):
        self.assertIsNone(grow_on_demand(Colony.initialize(), "research", queued_tasks=2))
    def test_population_limit(self):
        colony = Colony.initialize()
        colony.maximum_agents = 8
        self.assertIsNone(grow_on_demand(colony, "research", queued_tasks=100))
    def test_bad_role(self):
        with self.assertRaises(ValueError):
            grow_on_demand(Colony.initialize(), "unknown", queued_tasks=5)
