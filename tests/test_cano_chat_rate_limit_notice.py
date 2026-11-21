"""CANO owner chat must not mislabel a real provider quota failure as storage trouble."""
from __future__ import annotations

import ast
import logging
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from core.groq_team import TeamRateLimitError
from core.provider_failure import failure_category


class Cano429ChatNoticeTests(unittest.TestCase):
    def test_approved_chat_quota_failure_names_provider_not_postgresql(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        tree = ast.parse(app_path.read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "asistani_calistir"
        )
        calls = []
        private_error = "SYNTHETIC_PRIVATE_PROVIDER_BODY_MUST_NOT_APPEAR"

        def fake_team_answer(prompt):
            calls.append(prompt)
            if len(calls) == 3:
                raise TeamRateLimitError(private_error)
            return f"Completed synthetic stage {len(calls)}"

        state = {}
        scope = {
            "_CANO_OWNER_KEY": None,
            "GROQ_KEY": "synthetic-no-network-key",
            "_team_answer": fake_team_answer,
            "st": SimpleNamespace(session_state=state),
            "os": os,
            "uuid4": uuid4,
            "logging": logging,
            "failure_category": failure_category,
        }
        task = "CANO görev: sayısal gözlem planını karşılaştır"
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {
                "AGENT_COLONY_DB_PATH": str(Path(tmp) / "colony.sqlite3"),
            }):
                exec(
                    compile(
                        ast.Module(body=[function], type_ignores=[]),
                        str(app_path), "exec",
                    ), scope,
                )
                run = scope["asistani_calistir"]
                preview = run(task)
                self.assertIn("Henüz model çağrısı", preview)
                message = run(task, approved=True)

        self.assertEqual(3, len(calls), "Quota denial must not replay the provider")
        self.assertIn("kota", message.casefold())
        self.assertNotIn("PostgreSQL", message)
        self.assertNotIn(private_error, message)
        self.assertIn("Komuta Merkezi", message)


if __name__ == "__main__":
    unittest.main()
