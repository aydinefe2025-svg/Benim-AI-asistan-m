"""End-to-end routing contract at the Streamlit chat-function boundary."""
import ast
import logging
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"


class FakeCodeJobStore:
    calls = []
    def __init__(self, database_url, owner_key):
        self.db, self.owner = database_url, owner_key
    def enqueue(self, goal):
        type(self).calls.append((self.db, self.owner, goal))
        return {"id":"12345678-abcd-4000-8000-000000000000",
                "status":"queued","duplicate":False}


class NaturalChatIntegrationTests(unittest.TestCase):
    def setUp(self):
        FakeCodeJobStore.calls.clear()

    def call_app(self, message, history, *, authenticated=True):
        from core import cano_code_jobs
        tree = ast.parse(APP.read_text(encoding="utf8"))
        func=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
                  and n.name=="asistani_calistir")
        ns={"st":SimpleNamespace(session_state={"messages":history}),
            "_AUTH_REQUIRED":authenticated,
            "_OWNER_KEY":("oidc_"+"a"*64) if authenticated else None,
            "logging":logging,"os":os}
        exec(compile(ast.Module(body=[func],type_ignores=[]),
                     str(APP),"exec"),ns)
        with patch.object(cano_code_jobs,"CodeJobStore",FakeCodeJobStore):
            with patch.dict(os.environ,{"AGENT_TASK_DATABASE_URL":
                           "postgresql://example.invalid/assistant_pg"}):
                try:
                    return ns["asistani_calistir"](message)
                except (ModuleNotFoundError,NameError):
                    return "UNHANDLED_BY_CODE_EXECUTOR"

    def test_natural_web_imperative_creates_real_job(self):
        answer=self.call_app("CANO web sohbetindeki kod hatasını düzelt",[])
        self.assertEqual(1,len(FakeCodeJobStore.calls))
        self.assertIn("kalıcı kuyruğa alındı",answer)

    def test_solution_followup_queues_last_solution_without_copying(self):
        history=[{"role":"assistant","content":
                  "Çözüm: CANO uygulamasında görev kuyruğu bağlantı sorununu düzelt; sonra test ekle ve Render'da doğrula."}]
        answer=self.call_app("CANO bunu uygula",history)
        self.assertEqual(1,len(FakeCodeJobStore.calls))
        self.assertIn("Render",FakeCodeJobStore.calls[0][2])
        self.assertIn("kalıcı kuyruğa alındı",answer)

    def test_generic_solution_followup_does_not_queue_code_job(self):
        history=[{"role":"assistant","content":
                  "Çözüm: Uygulama kodunu düzelt; sonra test ekle ve Render dağıtımı yap."}]
        answer=self.call_app("CANO bunu uygula",history)
        self.assertEqual([], FakeCodeJobStore.calls)
        self.assertNotIn("kalıcı kuyruğa alındı",answer)

    def test_desired_level_command_queues_canonical_self_development(self):
        from core.cano_solution_dispatch import SELF_DEVELOPMENT_GOAL
        for message in (
            "dostum şu CANOyu istediğim kıvama getir artık",
            "CANO'yu istediğim kıvama getir",
            "canom şu CANO'yu istediğim kıvama getir!",
        ):
            with self.subTest(message=message):
                FakeCodeJobStore.calls.clear()
                answer = self.call_app(message, [])
                self.assertEqual(1, len(FakeCodeJobStore.calls))
                self.assertEqual(SELF_DEVELOPMENT_GOAL, FakeCodeJobStore.calls[0][2])
                self.assertIn("kalıcı kuyruğa alındı", answer)

    def test_desired_level_command_still_requires_owner(self):
        answer = self.call_app("CANO'yu istediğim kıvama getir", [], authenticated=False)
        self.assertEqual([], FakeCodeJobStore.calls)
        self.assertIn("doğrulanmış Google girişi gerekli", answer)

    def test_desired_level_research_and_questions_do_not_queue(self):
        for message in (
            "Şu nötron yıldızını istediğim kıvama getir",
            "CANO'yu istediğim kıvama getirir misin?",
            "CANO'yu istediğim kıvama getirmek hakkında konuş",
            "CANO araştırmasını istediğim kıvama getir",
        ):
            with self.subTest(message=message):
                FakeCodeJobStore.calls.clear()
                self.call_app(message, [])
                self.assertEqual([], FakeCodeJobStore.calls)

    def test_one_click_action_is_available_behind_owner_gate(self):
        text=APP.read_text(encoding="utf8")
        self.assertIn('st.button("🛠️ Bu çözümü gerçekten uygula"',text)
        self.assertIn('actionable_solution(_last_solution)',text)
        self.assertIn('CodeJobStore(',text)
        self.assertIn('os.environ["AGENT_TASK_DATABASE_URL"], _OWNER_KEY',text)


if __name__ == "__main__":
    unittest.main()
