import tempfile
import unittest
from pathlib import Path

from core.cano_source_context import build_cano_source_context


class AtomicSourceFactTests(unittest.TestCase):
    def test_real_repository_benchmark_facts_are_atomic_and_cited(self):
        root = Path(__file__).resolve().parents[1]
        result = build_cano_source_context("CANO benchmark JSON ayrıştırıcı sınırları", root)
        self.assertIn("ATOMIC SOURCE NOTES", result)
        self.assertRegex(result, r"core/benchmark_harness.py:\d+.*max_cases varsayılanı: 5")
        self.assertRegex(result, r"core/benchmark_harness.py:\d+.*Soru metni karakter sınırı: 2000")
        self.assertRegex(result, r"core/benchmark_harness.py:\d+.*Beklenen cevap karakter sınırı: 1000")

    def test_real_source_context_constants_are_read_from_source(self):
        root = Path(__file__).resolve().parents[1]
        result = build_cano_source_context("CANO kaynak bağlamı dosya boyutu", root)
        self.assertRegex(result, r"core/cano_source_context.py:\d+.*Tek dosya alıntısı karakter sınırı: 1800")
        self.assertRegex(result, r"core/cano_source_context.py:\d+.*Okunabilir dosya azami boyutu: 200000")

    def test_changed_source_literal_is_used_and_missing_evidence_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "core").mkdir()
            (root / "core/cano_source_context.py").write_text(
                "_MAX_FILE_CHARS = 2345\n", encoding="utf-8")
            result = build_cano_source_context("CANO kaynak bağlamı dosya sınırı", root)
            self.assertIn("Tek dosya alıntısı karakter sınırı: 2345", result)
            self.assertNotIn("Tek dosya alıntısı karakter sınırı: 1800", result)
            self.assertNotIn("Okunabilir dosya azami boyutu:", result)
            self.assertIn("unknown", result.lower())

    def test_science_and_unrelated_tasks_do_not_get_atomic_notes(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(build_cano_source_context("nötron yıldızı CANO benchmark kodu", root), "")
        self.assertEqual(build_cano_source_context("Güneş enerjisini araştır", root), "")

    def test_external_symlink_cannot_supply_facts(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            (root / "core").mkdir()
            external = Path(outside) / "external.py"
            external.write_text("_MAX_FILE_CHARS = 98765\n", encoding="utf-8")
            try:
                (root / "core/cano_source_context.py").symlink_to(external)
            except OSError:
                self.skipTest("symlink unavailable")
            result = build_cano_source_context("CANO kaynak bağlamı dosya sınırı", root)
            self.assertNotIn("98765", result)
