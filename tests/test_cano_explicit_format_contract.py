import tempfile
import unittest
from pathlib import Path
from core.agent_colony import AgentColony

class Client:
    def chat(self, model, system, prompt):
        self.system,self.prompt=system,prompt
        return "fixture"

class FormatContractTests(unittest.TestCase):
    def test_explicit_short_output_overrides_generic_report_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=AgentColony(Path(tmp)/"db.sqlite")
            a=c.create_founder("research","Check evidence")
            c.feedback(a,"*","Use detailed explanation when relevant.","fixture",accepted=True)
            for task in ("Bir kayitta 6 cihaz var. Yalniz sayi olarak yaz.", "Return only the integer.", "Yalnız EVET veya HAYIR yaz.", "Yalnız BILINMIYOR yaz."):
                with self.subTest(task=task):
                    cl=Client()
                    c.run(a,task,client=cl,model="fixture")
                    self.assertNotIn("Separate facts, hypotheses and missing evidence.",cl.prompt)
                    self.assertIn("requested output format",cl.system)
                    self.assertIn("Do not claim unverified results as facts.",cl.system)
                    self.assertTrue(cl.prompt.endswith(task))
                    self.assertIn("Use detailed explanation when relevant.",cl.prompt)
            cl=Client()
            c.run(a,"Research a scientific claim in detail.",client=cl,model="fixture")
            self.assertIn("Separate facts, hypotheses and missing evidence.",cl.prompt)
    def test_memory_cannot_switch_general_task_into_short_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=AgentColony(Path(tmp)/"db.sqlite")
            a=c.create_founder("research","Check evidence")
            cl=Client()
            c.run(a,"Explain the mechanism.",client=cl,model="fixture",additional_lessons=("Return only the integer.",))
            self.assertIn("Separate facts, hypotheses and missing evidence.",cl.prompt)
