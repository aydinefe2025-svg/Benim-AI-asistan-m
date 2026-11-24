import ast
import pathlib
import unittest
from types import SimpleNamespace

from core.fallback_chat_client import FallbackChatClient
from core.provider_failure import failure_category

class Client:
    def __init__(self, error=None):
        self.error = error
        self.calls = 0
    def chat(self, model, system, prompt, **kw):
        self.calls += 1
        if self.error:
            raise self.error
        return "ok"

class TeamProviderResilienceTests(unittest.TestCase):
    def test_team_keeps_successful_fallback_across_stages(self):
        app = pathlib.Path("app.py").read_text(encoding="utf-8")
        tree = ast.parse(app)
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_team_answer")
        primary = Client(TimeoutError("private"))
        fallback = Client()
        builds = []
        def build(**kw):
            builds.append(1)
            return FallbackChatClient(primary, fallback=fallback, fallback_model="free", allow_fallback=True)
        ns = dict(_new_provider_router=build, aktif_llm_adi="primary", extract_cano_task=lambda p:p,
                  build_cano_source_context=lambda *a:"", os=__import__("os"),
                  __file__="app.py", _team_router=None)
        exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), ns)
        self.assertEqual(ns["_team_answer"]("stage one"), "ok")
        self.assertEqual(ns["_team_answer"]("stage two"), "ok")
        self.assertEqual(len(builds), 1)
        self.assertEqual(primary.calls, 1)
        self.assertEqual(fallback.calls, 2)

    def test_exhausted_fallback_preserves_status_without_secret(self):
        e=RuntimeError("secret response")
        e.status_code=429
        router=FallbackChatClient(Client(TimeoutError("private")), fallback=Client(e),
                                  fallback_model="free", allow_fallback=True)
        with self.assertRaises(RuntimeError) as caught:
            router.chat("primary", "system", "prompt")
        self.assertEqual(failure_category(caught.exception), "rate_limit")
        self.assertEqual(caught.exception.status_code, 429)
        self.assertNotIn("secret response", str(caught.exception))

if __name__ == "__main__":
    unittest.main()
