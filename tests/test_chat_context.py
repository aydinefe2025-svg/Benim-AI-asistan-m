"""Ensure the app does not duplicate its latest user turn to Groq."""
import ast
import re
import types
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"


class ChatContextTests(unittest.TestCase):
    def test_groq_receives_current_user_message_only_once(self):
        source = ast.parse(APP.read_text(encoding="utf-8"))
        func = next(n for n in source.body
                    if isinstance(n, ast.FunctionDef) and n.name == "asistani_calistir")
        captured = []
        class FakeCompletions:
            def create(self, **kwargs):
                captured.extend(kwargs["messages"])
                return types.SimpleNamespace(
                    choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="Tamam"))]
                )
        class FakeGroq:
            def __init__(self, api_key):
                assert api_key == "demo"
                self.chat = types.SimpleNamespace(completions=FakeCompletions())
        fake_st = types.SimpleNamespace(session_state=types.SimpleNamespace(
            messages=[
                {"role": "user", "content": "Önceki soru"},
                {"role": "assistant", "content": "Önceki yanıt"},
                {"role": "user", "content": "Yeni soru"},
            ]
        ))
        namespace = {
            "st": fake_st, "Groq": FakeGroq, "GROQ_KEY": "demo",
            "secilen_model": "Groq GPT-OSS", "aktif_llm_adi": "openai/gpt-oss-120b",
            "internette_ara": lambda query: "Test verisi", "re": re,
        }
        exec(compile(ast.Module(body=[func], type_ignores=[]), str(APP), "exec"), namespace)
        result = namespace["asistani_calistir"]("Yeni soru")
        self.assertEqual(result, "Tamam")
        users = [m["content"] for m in captured if m["role"] == "user"]
        self.assertEqual(users, ["Önceki soru", "Yeni soru"])


if __name__ == "__main__":
    unittest.main()
