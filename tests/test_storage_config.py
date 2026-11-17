import unittest

from core.storage_config import cano_database_url, database_provider_label, memory_database_url


class StorageConfigTests(unittest.TestCase):
    def test_cano_url_is_preferred_over_legacy_database_url(self):
        env = {"DATABASE_URL": "legacy", "CANO_DATABASE_URL": "cano-only"}
        self.assertEqual(cano_database_url(env), "cano-only")

    def test_cano_only_credential_never_opens_general_memory_store(self):
        env = {"DATABASE_URL": "cano-only", "CANO_DATABASE_URL": "cano-only"}
        self.assertIsNone(memory_database_url(env))

    def test_explicit_memory_url_remains_independent(self):
        env = {
            "DATABASE_URL": "cano-only",
            "CANO_DATABASE_URL": "cano-only",
            "MEMORY_DATABASE_URL": "memory-only",
        }
        self.assertEqual(memory_database_url(env), "memory-only")

    def test_legacy_shared_url_is_preserved_without_cano_setting(self):
        env = {"DATABASE_URL": "legacy"}
        self.assertEqual(cano_database_url(env), "legacy")
        self.assertEqual(memory_database_url(env), "legacy")

    def test_app_binds_colony_sidebar_to_cano_owner_and_database(self):
        # The optional CANO_DATABASE_URL can be different from the general
        # memory store. The sidebar's backup must target the same owner and
        # database as the cockpit's snapshot CAS.
        import ast
        from pathlib import Path
        tree = ast.parse((Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8"))
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                 and node.func.id == "render_colony_panel"]
        self.assertEqual(len(calls), 1)
        keywords = {item.arg: item.value for item in calls[0].keywords}
        self.assertEqual(ast.unparse(keywords["owner_key"]), "_CANO_OWNER_KEY")
        self.assertEqual(
            ast.unparse(keywords["database_url"]),
            "cano_database_url(os.environ) if _CANO_OWNER_KEY else None")

    def test_unconfigured_urls_remain_unconfigured(self):
        self.assertIsNone(cano_database_url({}))
        self.assertIsNone(memory_database_url({}))

    def test_database_provider_label_never_exposes_url_secrets_or_host(self):
        self.assertEqual(
            database_provider_label("postgresql://user:secret@ep-cano.eu.neon.tech/db"),
            "Neon")
        self.assertEqual(
            database_provider_label("postgresql://user:secret@dpg-123.frankfurt-postgres.render.com/db"),
            "Render")
        self.assertEqual(database_provider_label("postgresql://user:secret@db.example/db"),
                         "harici PostgreSQL")
        self.assertEqual(database_provider_label(None), "yapılandırılmamış")
        self.assertEqual(database_provider_label("not-a-url-with-secret"),
                         "tanınmayan PostgreSQL")




class LiveNeonBindingAuditTests(unittest.TestCase):
    def test_effective_live_bindings_reveal_only_provider_classes(self):
        from core.storage_config import database_binding_providers
        env = {
            "DATABASE_URL": "postgresql://admin:OLD_PASSWORD@dpg-legacy.frankfurt-postgres.render.com/old",
            "CANO_DATABASE_URL": "postgresql://user:CANO_PASSWORD@ep-cano.eu-central-1.aws.neon.tech/assistant_pg",
            "MEMORY_DATABASE_URL": "postgresql://user:MEMORY_PASSWORD@ep-memory.eu-central-1.aws.neon.tech/assistant_pg",
            "AGENT_TASK_DATABASE_URL": "postgresql://user:TASK_PASSWORD@ep-task.eu-central-1.aws.neon.tech/assistant_pg",
        }
        receipt = database_binding_providers(env)
        self.assertEqual({"cano": "Neon", "memory": "Neon", "task": "Neon"}, receipt)
        for forbidden in ("PASSWORD", "dpg-legacy", "ep-cano", "postgresql://", "user"):
            self.assertNotIn(forbidden, repr(receipt))

    def test_missing_explicit_memory_remains_unconfigured(self):
        from core.storage_config import database_binding_providers
        env = {"DATABASE_URL": "postgresql://u:p@old.frankfurt-postgres.render.com/d",
               "CANO_DATABASE_URL": "postgresql://u:p@ep-a.eu.neon.tech/d",
               "AGENT_TASK_DATABASE_URL": "postgresql://u:p@ep-a.eu.neon.tech/d"}
        self.assertEqual({"cano": "Neon", "memory": "yapılandırılmamış",
                          "task": "Neon"}, database_binding_providers(env))

    def test_app_preflight_logs_only_classified_effective_bindings(self):
        import ast
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import Mock
        from core.storage_config import database_binding_providers
        app = Path(__file__).resolve().parents[1] / "app.py"
        tree = ast.parse(app.read_text(encoding="utf-8"))
        func = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef)
                    and n.name == "_cano_task_preflight_once")
        func.decorator_list = []
        logger = Mock()
        namespace = {
            "os": SimpleNamespace(environ={
                "CANO_DATABASE_URL": "postgresql://u:KEEP_PRIVATE@ep-a.eu.neon.tech/d",
                "MEMORY_DATABASE_URL": "postgresql://u:KEEP_PRIVATE@ep-b.eu.neon.tech/d",
                "AGENT_TASK_DATABASE_URL": "postgresql://u:KEEP_PRIVATE@ep-c.eu.neon.tech/d"}),
            "preflight_task_store": lambda url: {"ok": True},
            "preflight_authorized_queue": lambda url: {"ok": True},
            "database_binding_providers": database_binding_providers,
            "logging": SimpleNamespace(getLogger=lambda name: logger),
            "__name__": "cano.binding.audit.test",
        }
        exec(compile(ast.Module(body=[func], type_ignores=[]),
                     str(app), "exec"), namespace)
        self.assertTrue(namespace["_cano_task_preflight_once"]())
        calls = [c for c in logger.warning.call_args_list
                 if c.args and str(c.args[0]).startswith("CANO_DB_BINDINGS")]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[1:], ("Neon", "Neon", "Neon"))
        self.assertNotIn("KEEP_PRIVATE", str(calls))


if __name__ == "__main__":
    unittest.main()
