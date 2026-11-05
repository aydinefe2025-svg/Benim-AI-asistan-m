import unittest
from organism_lab.supervisor import Supervisor

class SupervisorTests(unittest.TestCase):
    def test_verified_task(self):
        result = Supervisor().run([("research", "scan")],
                                  {"research": lambda task: "report"},
                                  {"research": lambda task, output: "checked"})
        self.assertEqual((result["checked"], result["failed"]), (1, 0))
        self.assertEqual(result["results"][0]["attempts"], 1)

    def test_retry_after_failure(self):
        calls = []
        def handler(task):
            calls.append(task)
            if len(calls) == 1:
                raise RuntimeError("temporary")
            return "recovered"
        result = Supervisor().run([("code", "check")],
                                  {"code": handler}, {"code": lambda task, output: "checked"})
        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["results"][0]["attempts"], 2)

    def test_permanent_failure_not_misreported(self):
        result = Supervisor().run([("security", "check")],
                                  {"security": lambda task: ""},
                                  {"security": lambda task, output: "ok"})
        self.assertEqual((result["checked"], result["failed"]), (0, 1))

    def test_missing_handler_rejected_before_execution(self):
        with self.assertRaises(ValueError):
            Supervisor().run([("research", "task")], {}, {})

    def test_malformed_tasks_rejected_without_side_effects(self):
        calls = []
        supervisor = Supervisor()
        for bad in (["research"], [("research",)], [("research", "ok"), ("code",)], [(1, "task")]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                supervisor.run(bad, {"research": lambda task: calls.append(task) or "ok"},
                               {"research": lambda task, output: "checked"})
        self.assertEqual(calls, [])
        self.assertEqual(supervisor.colony.audit, [])

    def test_queue_limit_enforced(self):
        with self.assertRaises(ValueError):
            Supervisor(max_tasks=1).run([("research", "one"), ("research", "two")], {}, {})

    def test_growth_requires_explicit_permission(self):
        tasks = [("robotics", str(i)) for i in range(5)]
        h = {"robotics": lambda task: "simulated"}
        v = {"robotics": lambda task, output: "checked"}
        self.assertEqual(Supervisor().run(tasks, h, v)["agents"], 8)
        self.assertEqual(Supervisor().run(tasks, h, v, allow_growth=True)["agents"], 9)

if __name__ == "__main__":
    unittest.main()
