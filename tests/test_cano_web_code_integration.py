"""CANO code instructions must enter the durable worker queue, not the LLM."""
import ast
import logging
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"


def function():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    return next(n for n in tree.body if isinstance(n,ast.FunctionDef)
                and n.name == "asistani_calistir")


class FakeJobStore:
    calls = []
    def __init__(self,db,owner):
        self.db,self.owner=db,owner
    def enqueue(self,goal):
        type(self).calls.append((self.db,self.owner,goal))
        return {"id":"12345678-0000-0000-0000-000000000000",
                "status":"queued","duplicate":False}


class WebCodeIntegrationTests(unittest.TestCase):
    def setUp(self):
        FakeJobStore.calls=[]

    def test_explicit_command_enqueues_once_before_model_or_task_routing(self):
        ns={"st": SimpleNamespace(session_state={}),
            "_AUTH_REQUIRED":True,"_OWNER_KEY":"oidc_"+"a"*64,
            "logging":logging,"os":os}
        exec(compile(ast.Module(body=[function()],type_ignores=[]),
                     str(APP),"exec"),ns)
        with patch("core.cano_code_jobs.CodeJobStore",FakeJobStore),\
             patch.dict(os.environ,{"AGENT_TASK_DATABASE_URL":
                                    "postgresql://example.invalid/assistant_pg"}):
            answer=ns["asistani_calistir"](
                "CANO kod: Geliştirme işçisi için tekrar testi yaz")
        self.assertIn("kalıcı kuyruğa alındı",answer)
        self.assertEqual(1,len(FakeJobStore.calls))
        self.assertIn("tekrar testi",FakeJobStore.calls[0][2])

    def test_anonymous_command_fails_closed_without_enqueuing(self):
        ns={"st":SimpleNamespace(session_state={}),"_AUTH_REQUIRED":True,
            "_OWNER_KEY":None,"logging":logging,"os":os}
        exec(compile(ast.Module(body=[function()],type_ignores=[]),
                     str(APP),"exec"),ns)
        with patch("core.cano_code_jobs.CodeJobStore",FakeJobStore):
            result=ns["asistani_calistir"]("CANO kod: Bir hata denetimi yap")
        self.assertIn("Google girişi",result)
        self.assertEqual([],FakeJobStore.calls)

    def test_sidebar_only_for_authenticated_owner_and_code_path_precedes_llm(self):
        source=APP.read_text(encoding="utf-8")
        self.assertIn('if _OWNER_KEY and os.environ.get("AGENT_TASK_DATABASE_URL"):',source)
        self.assertIn('with st.sidebar.expander("🛠️ CANO Kod İşçisi"',source)
        self.assertLess(source.index("code_goal = parse_code_request"),
                        source.index("task_goal = parse_task_request"))
        self.assertIn('except Exception as _code_queue_error:',source)


if __name__ == "__main__":
    unittest.main()
