import unittest

from core.storage_config import cano_database_url, memory_database_url


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

    def test_unconfigured_urls_remain_unconfigured(self):
        self.assertIsNone(cano_database_url({}))
        self.assertIsNone(memory_database_url({}))


if __name__ == "__main__":
    unittest.main()
