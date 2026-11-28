import tempfile
import unittest
from pathlib import Path
from core.agent_colony import AgentColony
from core.agent_review_loop import AgentReviewLoop

class ReviewIntentTests(unittest.TestCase):
    def test_original_task_survives_all_review_stages_and_large_drafts(self):
        for length in (80, 3000):
            with self.subTest(length=length), tempfile.TemporaryDirectory() as tmp:
                colony=AgentColony(Path(tmp)/'colony.sqlite')
                author=colony.create_founder('research','Research carefully.')
                reviewer=colony.spawn(author,'skeptic','Check evidence.',approved=True)
                task=('UNIQUE-OWNER-REQUEST: Return only the requested result. ' + 'x'*3000)[:length]
                class Client:
                    def __init__(self): self.prompts=[]
                    def chat(self, model, system, prompt):
                        self.prompts.append(prompt)
                        return ('D'*12000 if len(self.prompts)==1 else 'C'*12000 if len(self.prompts)==2 else 'Final')
                client=Client()
                result=AgentReviewLoop(colony).execute(author,reviewer,task,client=client,model='fixture')
                self.assertEqual(len(client.prompts),3)
                self.assertIn(task,client.prompts[1])
                self.assertIn(task,client.prompts[2])
                self.assertIn('D'*1000,client.prompts[2])
                self.assertIn('C'*1000,client.prompts[2])
                self.assertEqual(result['task'],task)
                self.assertEqual(result['status'],'review_pending')

    def test_final_revision_respects_format_and_retrieves_original_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            colony = AgentColony(Path(tmp) / "colony.sqlite")
            author = colony.create_founder("author", "Solve carefully.")
            reviewer = colony.spawn(author, "reviewer", "Check carefully.", approved=True)
            task = "Return only the ZEFIR result as an integer."
            colony.feedback(author, "ZEFIR", "Use the ZEFIR rule.", "fixture:valid", accepted=True)
            colony.feedback(author, "NORVIK", "Use the NORVIK rule.", "fixture:unrelated", accepted=True)
            class Client:
                def __init__(self):
                    self.calls = []
                def chat(self, model, system, prompt):
                    self.calls.append((system, prompt))
                    return ("NORVIK draft" if len(self.calls) == 1 else
                            "NORVIK critique" if len(self.calls) == 2 else "42")
            client = Client()
            result = AgentReviewLoop(colony).execute(
                author, reviewer, task, client=client, model="fixture")
            system, prompt = client.calls[2]
            self.assertIn("final revision", system.lower())
            self.assertIn("requested output format", system.lower())
            self.assertNotIn("Separate facts, hypotheses and missing evidence.", prompt)
            self.assertIn("Use the ZEFIR rule.", prompt)
            self.assertNotIn("Use the NORVIK rule.", prompt)
            self.assertIn("NORVIK draft", prompt)
            self.assertIn("NORVIK critique", prompt)
            self.assertTrue(prompt.endswith(task))
            self.assertIn("Separate facts, hypotheses and missing evidence.", client.calls[0][1])
            self.assertEqual(result["revision"], "42")
            self.assertEqual(result["status"], "review_pending")
