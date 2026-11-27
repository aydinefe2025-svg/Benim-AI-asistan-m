import tempfile
import unittest
from pathlib import Path
from core.agent_colony import AgentColony

class Client:
    def __init__(self,answer): self.answer=answer; self.calls=0
    def chat(self,model,system,prompt):
        self.calls+=1
        return self.answer

class IntegerFormatTests(unittest.TestCase):
    def test_exact_verified_equation_is_rendered_as_integer_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=AgentColony(Path(tmp)/"db.sqlite")
            a=c.create_founder("research","Check evidence")
            for task,answer,expected in (
                ("18 kayıt var, 5 tanesi eksik. Kalanı yalnız sayı olarak yaz.","18 - 5 = 13","13"),
                ("How many remain? Return only the integer.","15 - 6 = 9","9"),
                ("Return only the integer.","-4 + 3 = -1","-1"),
                ("Yalnız sayı olarak yaz.","6 × 7 = 42","42"),
            ):
                with self.subTest(task=task,answer=answer):
                    cl=Client(answer)
                    result=c.run(a,task,client=cl,model="fixture")
                    self.assertEqual(result["output"],expected)
                    self.assertEqual(result["status"],"draft_unverified")
                    self.assertEqual(cl.calls,1)
    def test_ambiguous_incorrect_or_non_numeric_contract_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=AgentColony(Path(tmp)/"db.sqlite")
            a=c.create_founder("research","Check evidence")
            for task,answer in (
                ("Return only the integer.","9 - 3 = 7"),
                ("Return only the integer.","9 - 3 = 6 or 7"),
                ("Return only the integer.","Evidence: 9 - 3 = 6"),
                ("Return only the integer.","3 / 0 = 0"),
                ("Return only the integer.","9 - 3 = 6; 7 + 1 = 8"),
                ("Explain the calculation.","9 - 3 = 6"),
                ("Yalnız EVET veya HAYIR yaz.","9 - 3 = 6"),
                ("Return only the integer.","8"),
            ):
                with self.subTest(task=task,answer=answer):
                    self.assertEqual(c.run(a,task,client=Client(answer),model="fixture")["output"],answer)
