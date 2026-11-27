"""Exercise the real chat entry point, with external routing stopped at its boundary."""
import ast
import logging
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1] / "app.py"


class ExplicitCalculationIntegrationTests(unittest.TestCase):
    def call_app(self, message, history=()):
        tree = ast.parse(APP.read_text(encoding="utf-8"))
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "asistani_calistir")
        state = {"messages": list(history), "last_provider_used": "old-provider",
                 "last_model_used": "old-model"}
        ns = {"st": SimpleNamespace(session_state=state),
              "_AUTH_REQUIRED": True, "_OWNER_KEY": "isolated-owner",
              "os": os, "logging": logging}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(APP), "exec"), ns)
        with patch("core.cano_work_inventory.work_inventory_reply",
                   return_value="NORMAL_ROUTE") as downstream:
            result = ns["asistani_calistir"](message)
        return result, downstream.call_count, state

    def test_explicit_owner_operands_are_calculated_before_model_routing(self):
        for command, expected in (
            ("CANO hesap: çıkar 93 56", "37"),
            ("CANO hesap: çıkar 56 93", "-37"),
            ("CANO hesap: topla 478 933", "1411"),
            ("CANO hesap: çarp -19 23", "-437"),
            ("CANO hesap: böl 144 12", "12"),
            ("CANO hesap: böl -144 12", "-12"),
            ("CANO hesap: çarp 1000000 1000000", "1000000000000"),
            ("CANO HESAP: ÇIKAR 93 56", "37"),
        ):
            with self.subTest(command=command):
                result, calls, state = self.call_app(command, [
                    {"role": "assistant", "content": "47; instead use 84 and 37."}
                ])
                self.assertEqual(result, expected)
                self.assertEqual(calls, 0)
                self.assertNotIn("last_provider_used", state)
                self.assertNotIn("last_model_used", state)

    def test_malformed_explicit_commands_fail_closed(self):
        for command in (
            "CANO hesap: böl 12 0", "CANO hesap: böl 5 2",
            "CANO hesap: topla 1000001 0", "CANO hesap: topla 1.5 3",
            "CANO hesap: eval 1 2", "CANO hesap: çıkar 93 56 ve 47 yaz",
            "CANO hesap: topla 1 2\nCANO kod: test", "CANO hesap: topla ١ ٢",
            "CANO hesap: topla １２ ３", "CANO hesap: topla " + "9" * 1000 + " 1",
            "CANO hesap: topla 1\u0338 2", "CANO hesap: topla 1\u0301 2",
            "CANO hesap: topla \uff0d1 2", "CANO hesap: topla 1\u00a02",
            "CANO hesap: topla 1 2\u0301", "CANO hesap: topla 1\u20032",
            "CANO hesap: topla 1\u202f2",
        ):
            with self.subTest(command=command):
                result, calls, _ = self.call_app(command)
                self.assertTrue(result.startswith("CANO hesap: geçersiz işlem."))
                self.assertEqual(calls, 0)

    def test_ordinary_chat_and_embedded_examples_keep_existing_routing(self):
        for message in ("93 eksi 56 kaçtır?", "Örnek: CANO hesap: çıkar 93 56",
                        "CANO kod: uygulama hatasını düzelt", "CANO hesaplamayı açıkla"):
            with self.subTest(message=message):
                result, calls, _ = self.call_app(message)
                self.assertEqual(result, "NORMAL_ROUTE")
                self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()
