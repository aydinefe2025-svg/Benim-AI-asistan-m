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
        self.assertIn("İddiaları kaynak alıntılarıyla karşılaştır", source)
        self.assertIn("store.verify_schema()", source)
        self.assertNotIn("store.initialize()", source)


if __name__ == "__main__":
    unittest.main()
