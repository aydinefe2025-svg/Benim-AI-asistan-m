"""Ensure the app sends the current user turn once through the provider router."""
import ast
import re
import types
import unittest
from pathlib import Path

from core.safety_policy import safe_response_for_prompt

APP = Path(__file__).resolve().parents[1] / "app.py"


class FakeState(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key, value):
        self[key] = value


class ChatContextTests(unittest.TestCase):
    def test_router_receives_current_user_message_only_once(self):
        source = ast.parse(APP.read_text(encoding="utf-8"))
        func = next(n for n in source.body
                    if isinstance(n, ast.FunctionDef) and n.name == "asistani_calistir")
        captured = []

        class FakeRouter:
            last_provider_used = "Groq"
            last_model_used = "openai/gpt-oss-120b"

            def chat(self, model, system, prompt):
                captured.append((model, system, prompt))
                return "Tamam"

        state = FakeState(
            saved_memories=[],
            messages=[
                {"role": "user", "content": "Önceki soru"},
                {"role": "assistant", "content": "Önceki yanıt"},
                {"role": "user", "content": "Yeni soru"},
            ],
        )
        fake_st = types.SimpleNamespace(session_state=state)
        namespace = {
            "st": fake_st,
            "_new_provider_router": lambda: FakeRouter(),
            "secilen_model": "Groq GPT-OSS",
            "aktif_llm_adi": "openai/gpt-oss-120b",
            "internette_ara": lambda query: "Test verisi",
            "memory_context": lambda items, query: "MEMORY_CONTEXT",
            "safe_response_for_prompt": safe_response_for_prompt,
            "label_research_answer": lambda answer, **kwargs: answer,
            "re": re,
        }
        exec(compile(ast.Module(body=[func], type_ignores=[]), str(APP), "exec"), namespace)
        result = namespace["asistani_calistir"]("Yeni soru")
        self.assertEqual(result, "Tamam")
        model, system, prompt = captured[0]
        self.assertEqual(model, "openai/gpt-oss-120b")
        self.assertIn("MEMORY_CONTEXT", system)
        self.assertEqual(prompt.count("user: Yeni soru"), 1)
        self.assertIn("user: Önceki soru", prompt)
        self.assertEqual(state["last_provider_used"], "Groq")
        self.assertEqual(state["last_model_used"], "openai/gpt-oss-120b")


if __name__ == "__main__":
    unittest.main()

