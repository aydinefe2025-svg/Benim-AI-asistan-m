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


if __name__ == "__main__":
    unittest.main()

