import unittest

from core.user_memory import (
    export_library, import_library, memory_context, new_memory, normalize_library,
    relevant_memories,
)


class UserMemoryTests(unittest.TestCase):
    def test_export_import_round_trip(self):
        original = [new_memory("Proje notu: araştırma hafızası", ["proje"])]
        restored = import_library(export_library(original))
        self.assertEqual(restored, original)

    def test_retrieval_returns_relevant_notes_only(self):
        items = [
            new_memory("Render ücretsiz planda dosyalar kalıcı değildir"),
            new_memory("Kullanıcı Türkçe yanıt tercih ediyor"),
        ]
        self.assertEqual(
            relevant_memories(items, "Render dosyaları kalıcı mı?"),
            [items[0]],
        )
        self.assertEqual(memory_context(items, "Render dosyaları kalıcı mı?").count("\n- "), 1)

    def test_bad_or_oversized_import_rejected(self):
        with self.assertRaises(ValueError):
            import_library('{"schema_version": 2, "items": []}')
        with self.assertRaises(ValueError):
            normalize_library({"schema_version": 1, "items": [{"text": "x" * 2001}]})

    def test_empty_query_does_not_return_all_memories(self):
        self.assertEqual(relevant_memories([new_memory("Bir not")], "ve de"), [])


if __name__ == "__main__":
    unittest.main()
