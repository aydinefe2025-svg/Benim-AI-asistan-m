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
        self.assertIn("retry_unavailable_skeptical_pass", source)
        claim_evidence_imports = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "core.claim_evidence"
            for alias in node.names
        }
        self.assertIn("retry_unavailable_skeptical_pass", claim_evidence_imports)
        self.assertIn("Kuşkucu geçişi yeniden dene (1 çağrı)", source)
        self.assertIn("Güvenli hata ayrıntısı:", source)
        self.assertIn("reviewer_id=owner", source)
        self.assertIn("full_text_excerpt", source)
        self.assertIn("İddiaları çıkar ve ayrı kuşkucu AI geçişi çalıştır", source)
        self.assertIn("generate_claim_verification_json", source)
        self.assertIn("run_claim_review_benchmark", source)
        self.assertIn("CASES as FIXED_BENCHMARK_CASES", source)
        self.assertIn("CANO modelini 12 sabit vakada test et (1 çağrı)", source)
        self.assertIn("cases=FIXED_BENCHMARK_CASES", source)
        self.assertIn("cano_claim_review_runtime_smoke_v1", source)
        self.assertIn("HUMAN_COMPARISON_CASES", source)
        self.assertIn("run_blind_model_benchmark", source)
        self.assertIn("cano_gold_model_v3", source)
        self.assertIn("cano_gold_model_v4", source)
        self.assertLess(source.index("cano_gold_model_v3"), source.index("if isinstance(saved_human_labels, dict)"))
        self.assertLess(source.index("cano_gold_model_v4"), source.index("if isinstance(v4_saved_labels, dict)"))
        self.assertIn("Kaynağı aç:", source)
        self.assertIn("source_url", source)
        self.assertIn("CANO_HUMAN_BENCHMARK_ANSWER_KEY", source)
        self.assertIn("load_expected_labels", source)
        self.assertIn('answer_key_json=os.environ.get("CANO_HUMAN_BENCHMARK_ANSWER_KEY")', source)
        self.assertIn("24 insan değerlendirmesini kaydet", source)
        self.assertIn("Kaynak anahtarıyla CANO'yu çalıştır (24 vaka, 1 çağrı)", source)
        self.assertIn("cano_claim_review_human_labels_v3", source)
        self.assertIn("score_labels(\n            HUMAN_COMPARISON_CASES, saved_human_labels, human_answer_key)", source)
        self.assertIn("gerçek dünya", source)
        self.assertIn("Görevdeki DOI kaynaklarını yeniden oku", source)
        self.assertIn("manager.inspect_source_documents(mid, refresh_missing=True)", source)
        self.assertIn("store.verify_schema()", source)
        self.assertIn("except LookupError:", source)
        self.assertIn("except PermissionError:", source)
        self.assertIn("except RuntimeError:", source)
        self.assertNotIn("store.initialize()", source)


    def test_fixed_runtime_benchmark_is_not_gated_by_blind_human_form(self):
        path = Path(__file__).resolve().parents[1] / "pages" / "01_CANO_Kaynak_Denetimi.py"
        source = path.read_text(encoding="utf-8")
        runtime_button = source.index("CANO modelini 12 sabit vakada test et (1 çağrı)")
        human_form = source.index('st.form("cano_blind_human_labels_v3")')
        self.assertLess(runtime_button, human_form)
        self.assertIn("CANO görev kayıtlarını ", source)
        self.assertIn("değiştirmez ve kör insan karşılaştırmasının", source)


    def test_evidence_restore_uses_cano_only_database_url(self):
        """The second page must use the least-privilege CANO database URL."""
        path = Path(__file__).resolve().parents[1] / "pages" / "01_CANO_Kaynak_Denetimi.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn("from core.storage_config import cano_database_url", source)
        self.assertEqual(source.count("ColonySnapshotStore(cano_database_url(os.environ))"), 6)
        self.assertNotIn('os.environ["DATABASE_URL"]', source)


    def test_supplemental_cohort_is_separate_and_uses_private_answer_key(self):
        path = Path(__file__).resolve().parents[1] / "pages" / "01_CANO_Kaynak_Denetimi.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn("SUPPLEMENTAL_COMPARISON_CASES", source)
        self.assertIn("cano_claim_review_human_labels_v4", source)
        self.assertIn("CANO_HUMAN_BENCHMARK_ANSWER_KEY_V4", source)
        self.assertIn("Ek 24 insan değerlendirmesini kaydet", source)
        self.assertIn("Ek kohortta CANO'yu gizli kaynak anahtarıyla çalıştır (24 vaka, 1 çağrı)", source)
        self.assertIn('answer_key_json=os.environ.get("CANO_HUMAN_BENCHMARK_ANSWER_KEY_V4")', source)
        self.assertIn("v4_agreement", source)
        self.assertIn("cevap anahtarı gösterilmedi", source)


    def test_gold_model_runs_are_available_before_human_labels(self):
        path = Path(__file__).resolve().parents[1] / "pages" / "01_CANO_Kaynak_Denetimi.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn("run_blind_model_benchmark", source)
        self.assertIn("cano_gold_model_v3", source)
        self.assertIn("cano_gold_model_v4", source)
        self.assertLess(source.index("cano_gold_model_v3"),
                        source.index("if isinstance(saved_human_labels, dict)"))
        self.assertLess(source.index("cano_gold_model_v4"),
                        source.index("if isinstance(v4_saved_labels, dict)"))
        self.assertIn("v3 kaynak anahtarına uyum", source)
        self.assertIn("v4 kaynak anahtarına uyum", source)
        self.assertIn("yalnızca kuşkucu pasaj sınıflandırmasını ölçer", source)


if __name__ == "__main__":
    unittest.main()
