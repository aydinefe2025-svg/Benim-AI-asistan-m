"""Imported memory backups must never overwrite a different existing entry."""
import unittest

from core.user_memory import merge_libraries, new_memory


class MemoryMergeSafetyTests(unittest.TestCase):
    def test_distinct_entries_are_appended_without_changing_existing(self):
        existing = [new_memory("Keep first")]
        incoming = [new_memory("Add second")]
        result = merge_libraries(existing, incoming)
        self.assertEqual(result, existing + incoming)
        self.assertEqual(len(existing), 1)

    def test_conflicting_id_preserves_existing_and_imported_text(self):
        original = new_memory("Original stays")
        conflict = {**original, "text": "Imported alternative"}
        result = merge_libraries([original], [conflict])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], original)
        self.assertEqual(result[1]["text"], "Imported alternative")
        self.assertNotEqual(result[1]["id"], original["id"])

    def test_repeated_import_is_idempotent_for_identical_records(self):
        entry = new_memory("Same record")
        self.assertEqual(merge_libraries([entry], [entry]), [entry])

    def test_over_capacity_rejected_without_mutating_inputs(self):
        existing = [new_memory(f"Old {i}") for i in range(200)]
        incoming = [new_memory("One too many")]
        snapshot = [dict(x) for x in existing]
        with self.assertRaises(ValueError):
            merge_libraries(existing, incoming)
        self.assertEqual(existing, snapshot)

    def test_at_capacity_identical_records_are_allowed(self):
        existing = [new_memory(f"Old {i}") for i in range(200)]
        self.assertEqual(merge_libraries(existing, [existing[0]]), existing)


if __name__ == "__main__":
    unittest.main()
