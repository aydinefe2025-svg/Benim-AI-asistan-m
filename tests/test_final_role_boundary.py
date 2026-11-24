import tempfile
import unittest
from pathlib import Path
from core.agent_colony import AgentColony
from core.collaborative_mission import CollaborativeMission

class Client:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = 0
    def chat(self, model, system, prompt):
        self.calls += 1
        return next(self.outputs)

class FinalRoleBoundary(unittest.TestCase):
    def test_internal_reviewer_marker_blocks_final_and_preserves_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            colony = AgentColony(Path(d)/"mission.sqlite3")
            colony.create_founder("research","Research carefully")
            colony.grow_specialists(approved=True)
            mission = CollaborativeMission(colony)
            critique = "Check the calculation.\nCANO_LESSON_CANDIDATE: NONE"
            leaked = "12 x 7 = 84.\n**CANO_LESSON_CANDIDATE: NONE**"
            client = Client(["Plan.", "Draft.", critique, leaked])
            with self.assertRaisesRegex(RuntimeError, "reviewer marker"):
                mission.execute("Verify multiplication",client=client,model="test")
            partial = mission.interrupted()[0]
            self.assertEqual(partial["status"],"blocked")
            prior = mission.get(partial["id"])["stages"]
            self.assertEqual(len(prior),3)
            self.assertEqual(client.calls,4)
            clean = Client(["12 x 7 = 84."])
            result = mission.resume(partial["id"],client=clean,model="test")
            self.assertEqual(result["status"],"review_pending")
            self.assertEqual(result["stages"][:3],prior)
            self.assertEqual(clean.calls,1)

if __name__ == "__main__":
    unittest.main()
