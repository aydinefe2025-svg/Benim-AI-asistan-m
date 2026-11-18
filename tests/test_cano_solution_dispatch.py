import unittest
from core.cano_solution_dispatch import infer_code_goal, actionable_solution

class CanoNaturalCodeDispatchTests(unittest.TestCase):
    def test_owner_explicit_fix_followup_after_known_provider_error_routes_to_code(self):
        from core.provider_failure import MESSAGES
        for category in ("request", "unknown", "response"):
            with self.subTest(category=category):
                history = [
                    {"role": "user", "content": "İzmir Ödemiş hava tahminleri"},
                    {"role": "assistant", "content": MESSAGES[category]},
                ]
                goal = infer_code_goal("Bu sorunu çöz cano", history)
                self.assertIsInstance(goal, str)
                self.assertIn("CANO", goal)
                self.assertIn("test", goal.casefold())
                self.assertLessEqual(len(goal), 1200)

        self.assertIsNone(infer_code_goal("Bu sorunu çöz cano", []))
        self.assertIsNone(infer_code_goal("Bu sorunu çöz cano", [
            {"role": "assistant", "content": "Merhaba, bugün hava güzel."}
        ]))
        self.assertIsNone(infer_code_goal(
            "Bu sorunu çöz cano sk-" + "x" * 30,
            [{"role": "assistant", "content": MESSAGES["request"]}],
        ))

    def test_direct_software_imperative_requires_no_special_prefix(self):
        self.assertEqual("CANO web sohbetindeki kod hatasını düzelt",
                         infer_code_goal("CANO web sohbetindeki kod hatasını düzelt", []))
    def test_implement_last_solution_without_copy_paste(self):
        previous=[
          {"role":"user","content":"CANO nasıl geliştirilir?"},
          {"role":"assistant","content":"Çözüm: CANO uygulamasında görev kuyruğu bağlantısını düzelt, ardından otomatik test ekle ve Render'da doğrula."},
          {"role":"user","content":"CANO bunu uygula"}
        ]
        result=infer_code_goal("CANO bunu uygula",previous)
        self.assertIn("görev kuyruğu",result)
        self.assertIn("Render",result)
        self.assertLessEqual(len(result),1200)
    def test_research_and_capability_question_not_swallowed(self):
        for q in ("CANO nötron yıldızını araştır", "CANO kendini geliştirebilir misin?", "Bugün hava nasıl?"):
            with self.subTest(q=q):
                self.assertIsNone(infer_code_goal(q,[]))
    def test_no_previous_actionable_solution_returns_none(self):
        self.assertIsNone(infer_code_goal("CANO bunu uygula",[
            {"role":"assistant","content":"Merhaba, size nasıl yardımcı olabilirim?"}
        ]))
    def test_existing_explicit_routing_remains_authoritative(self):
        self.assertIsNone(infer_code_goal("CANO kod: uygulama hatasını düzelt",[]))
        self.assertIsNone(infer_code_goal("CANO görev: araştırma hazırla",[]))
    def test_model_code_request_is_not_accepted_as_user_instruction(self):
        self.assertFalse(actionable_solution("İnternette bilgi buldum ve açıklıyorum."))
        self.assertFalse(actionable_solution("İş kimliği: 1245 · CANO kod işi kalıcı kuyruğa alındı"))
    def test_secret_in_context_never_queues(self):
        messages=[{"role":"assistant","content":"Çözüm: kodu güncelle, test et. sk-"+"X"*40}]
        self.assertIsNone(infer_code_goal("CANO bunu uygula",messages))

    def test_self_development_command_creates_repeatable_concrete_code_goal(self):
        instructions = (
            "Kendini geliştir cano",
            "CANO kendini geliştir",
            "Kendini geliştir",
            "CANO kendini geliştirmeye devam et",
        )
        goals = [infer_code_goal(message, []) for message in instructions]
        self.assertTrue(all(isinstance(goal, str) and len(goal) <= 1200
                            for goal in goals))
        self.assertEqual(len(set(goals)), 1)
        self.assertIn("test", goals[0].casefold())
        self.assertIn("GitHub", goals[0])
        self.assertIn("güven", goals[0].casefold())
        self.assertIsNone(infer_code_goal("CANO kendini geliştirebilir misin?", []))

    def test_authenticated_chat_self_development_enqueues_job_without_preview(self):
        import ast
        import logging
        import os
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch

        app_file = Path(__file__).resolve().parents[1] / "app.py"
        source = ast.parse(app_file.read_text(encoding="utf-8"))
        node = next(n for n in source.body
                    if isinstance(n, ast.FunctionDef) and n.name == "asistani_calistir")
        state = {"messages": [],
                 "_cano_chat_task_pending": {"task": "old draft", "id": "old-id"},
                 "cano_chat_request_id": {"task": "old draft", "id": "old-id"}}
        queued = []

        class RecordingJobStore:
            def __init__(self, database_url, owner_key):
                self.database_url = database_url
                self.owner_key = owner_key

            def enqueue(self, goal):
                queued.append((self.database_url, self.owner_key, goal))
                return {"id": "01234567-test-job", "status": "queued", "duplicate": False}

        namespace = {
            "st": SimpleNamespace(session_state=state),
            "_AUTH_REQUIRED": True,
            "_OWNER_KEY": "isolated-test-owner",
            "os": os,
            "logging": logging,
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(app_file), "exec"),
             namespace)
        with patch.dict(os.environ, {"AGENT_TASK_DATABASE_URL": "isolated-test-dsn"}):
            with patch("core.cano_code_jobs.CodeJobStore", RecordingJobStore):
                reply = namespace["asistani_calistir"]("Kendini geliştir cano")
        self.assertIn("kalıcı kuyruğa alındı", reply)
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0][:2], ("isolated-test-dsn", "isolated-test-owner"))
        self.assertIn("RED", queued[0][2])
        self.assertNotIn("_cano_chat_task_pending", state)
        self.assertNotIn("cano_chat_request_id", state)

    def test_completed_duplicate_does_not_pretend_to_enqueue_new_work(self):
        import ast
        import logging
        import os
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch

        app_file = Path(__file__).resolve().parents[1] / "app.py"
        source = ast.parse(app_file.read_text(encoding="utf-8"))
        fn = next(node for node in source.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "asistani_calistir")

        class CompletedStore:
            def __init__(self, url, owner):
                pass
            def enqueue(self, goal):
                return {"id": "01234567-old", "status": "deployed", "duplicate": True}

        state = {"messages": []}
        globals_ = {
            "st": SimpleNamespace(session_state=state),
            "_AUTH_REQUIRED": True, "_OWNER_KEY": "isolated-test-owner",
            "os": os, "logging": logging,
        }
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(app_file),
                     "exec"), globals_)
        with patch.dict(os.environ, {"AGENT_TASK_DATABASE_URL": "synthetic-dsn"}):
            with patch("core.cano_code_jobs.CodeJobStore", CompletedStore):
                text = globals_["asistani_calistir"]("Kendini geliştir cano")
        self.assertIn("tamamlandı", text)
        self.assertNotIn("kalıcı kuyruğa alındı", text)
        self.assertIn("yeni iş başlatılmadı", text)


    def test_status_message_with_memory_note_is_not_an_executable_code_solution(self):
        # A real queued job came from "CANO bunu uygula" after an assistant
        # described a previous queued job and offered to save a MEMORY NOTE.
        # 'ekleyebiliriz' must not count as the code-edit command 'ekle'.
        previous = (
            "Merhaba! Cano'nun her şeyi öğrenmesi model eğitimi demek değil. "
            "Kod geliştirme işi hâlâ kuyruğa alınmış. "
            "Kullanıcı notunu kalıcı hafızaya ekleyebiliriz; "
            "bir not oluşturup saklamak mümkün. Notu kaydedebiliriz."
        )
        self.assertFalse(actionable_solution(previous))
        self.assertIsNone(infer_code_goal(
            "CANO bunu uygula", [{"role": "assistant", "content": previous}]
        ))

