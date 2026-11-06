"""Smoke gate: the second CANO page must be importable and self-contained."""
import ast
import unittest
from pathlib import Path


class EvidencePageSmokeTests(unittest.TestCase):
    def test_source_page_compiles_and_has_json_import(self):
        path = Path(__file__).resolve().parents[1] / "pages" / "01_CANO_Kaynak_Denetimi.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        imports = {
            alias.asname or alias.name.split(".")[0]
            for node in tree.body if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertIn("json", imports)
        self.assertIn("st", imports)
        self.assertIn("audit_claim_quotes", source)
        self.assertIn("record_source_claim_review", source)
        self.assertIn("reviewer_id=owner", source)
        self.assertIn("full_text_excerpt", source)
        self.assertIn("İddiaları çıkar ve ayrı AI modeliyle kuşkucu incele", source)
        self.assertIn("generate_claim_verification_json", source)
        self.assertIn("Görevdeki DOI kaynaklarını yeniden oku", source)
        self.assertIn("manager.inspect_source_documents(mid, refresh_missing=True)", source)
        self.assertIn("store.verify_schema()", source)
        self.assertIn("except LookupError:", source)
        self.assertIn("except PermissionError:", source)
        self.assertIn("except RuntimeError:", source)
        self.assertNotIn("store.initialize()", source)


    def test_evidence_restore_uses_cano_only_database_url(self):
        """The second page must use the least-privilege CANO database URL."""
        path = Path(__file__).resolve().parents[1] / "pages" / "01_CANO_Kaynak_Denetimi.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn("from core.storage_config import cano_database_url", source)
        self.assertEqual(source.count("ColonySnapshotStore(cano_database_url(os.environ))"), 5)
        self.assertNotIn('os.environ["DATABASE_URL"]', source)


if __name__ == "__main__":
    unittest.main()
