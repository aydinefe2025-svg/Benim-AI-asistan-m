"""Guard the least-privilege Neon migration used by the cloud archive."""
from pathlib import Path
import unittest


MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "0002_organism_lab_runtime_rls.sql"


class RuntimeMigrationTests(unittest.TestCase):
    def test_runtime_role_is_rls_limited_to_select_insert_update(self):
        sql = MIGRATION.read_text(encoding="utf-8").upper()
        self.assertIn("REVOKE ALL ON PUBLIC.ORGANISM_LAB_RECORDS FROM PUBLIC", sql)
        self.assertIn("GRANT USAGE ON SCHEMA PUBLIC TO ORGANISM_LAB_RUNTIME", sql)
        self.assertIn("REVOKE ALL ON PUBLIC.ORGANISM_LAB_RECORDS FROM ORGANISM_LAB_RUNTIME", sql)
        self.assertIn(
            "GRANT SELECT, INSERT, UPDATE ON PUBLIC.ORGANISM_LAB_RECORDS TO ORGANISM_LAB_RUNTIME",
            sql,
        )
        self.assertIn("ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("FOR SELECT TO ORGANISM_LAB_RUNTIME", sql)
        self.assertIn("FOR INSERT TO ORGANISM_LAB_RUNTIME", sql)
        self.assertIn("FOR UPDATE TO ORGANISM_LAB_RUNTIME", sql)
        self.assertNotIn("DELETE ON PUBLIC.ORGANISM_LAB_RECORDS TO ORGANISM_LAB_RUNTIME", sql)


if __name__ == "__main__":
    unittest.main()
