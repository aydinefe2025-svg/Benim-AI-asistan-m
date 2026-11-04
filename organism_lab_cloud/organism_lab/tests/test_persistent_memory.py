import sqlite3
import tempfile
import unittest
from pathlib import Path

from organism_lab.persistent_memory import (augment_with_memory, list_memories,
                                            retrieve_memories, save_memory)


class PersistentMemoryTests(unittest.TestCase):
    def test_user_confirmed_notes_persist_and_are_retrieved_by_relevance(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = save_memory(tmp, "Project", "The local assistant should answer in Turkish.")
            save_memory(tmp, "Research", "The experiment uses paired simulation seeds.")
            self.assertEqual(first["provenance"], "user-confirmed")
            found = retrieve_memories(tmp, "Please answer in Turkish for the project")
            self.assertEqual([row["topic"] for row in found], ["Project"])
            self.assertEqual(len(list_memories(tmp)), 2)
            prompt = augment_with_memory("What language should you use?", found)
            self.assertIn("The local assistant should answer in Turkish", prompt)
            self.assertIn("GÜNCEL İSTEK", prompt)

    def test_duplicate_save_is_idempotent_and_no_match_adds_no_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = save_memory(tmp, "Style", "Use concise answers.")
            b = save_memory(tmp, "Style", "Use concise answers.")
            self.assertEqual(a["id"], b["id"])
            self.assertEqual(len(list_memories(tmp)), 1)
            self.assertEqual(retrieve_memories(tmp, "quantum spacecraft"), [])
            self.assertEqual(augment_with_memory("hello", []), "hello")

    def test_turkish_inflections_retrieve_the_saved_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_memory(tmp, "Sistem hedefi", "Asistan kalıcı olarak gelişsin ve araştırmaya odaklansın.")
            found = retrieve_memories(tmp, "Sistemin ana hedefi ne olmalı?")
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["topic"], "Sistem hedefi")

    def test_secret_like_values_and_unbounded_text_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for topic, content in (("API", "gsk_" + "1234567890abcdef"),
                                   ("key", "sk-1234567890abcdefghijkl"),
                                   ("", "some note"),
                                   ("topic", "x" * 4001)):
                with self.subTest(topic=topic), self.assertRaises(ValueError):
                    save_memory(tmp, topic, content)
            self.assertFalse((Path(tmp) / "assistant_memory.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
