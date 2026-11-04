import unittest

from core.browser_memory import decode_snapshot, write_confirmed
from core.user_memory import export_library, new_memory, memory_context


class BrowserMemoryTests(unittest.TestCase):
    def test_roundtrip_after_new_session(self):
        saved = [new_memory("Benim test kodum CANO-2026-1103", ["test"])]
        stored = export_library(saved)
        reloaded = decode_snapshot({"status": "ok", "payload": stored})
        self.assertEqual(reloaded, saved)

    def test_empty_storage_is_valid(self):
        self.assertEqual(decode_snapshot({"status": "ok", "payload": ""}), [])

    def test_corrupt_storage_never_silently_overwrites(self):
        for snapshot in (None, {}, {"status": "error"}, {"status": "ok", "payload": "{"}):
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(ValueError):
                    decode_snapshot(snapshot)

    def test_confirm_requires_readback(self):
        pending = {"token": "w-1", "payload": "saved-data"}
        self.assertTrue(write_confirmed(
            {"status": "ok", "ack": "w-1", "payload": "saved-data"}, pending))
        self.assertFalse(write_confirmed(
            {"status": "ok", "ack": "w-1", "payload": "old"}, pending))
        self.assertFalse(write_confirmed(
            {"status": "ok", "ack": "wrong", "payload": "saved-data"}, pending))

    def test_explicit_chat_save_request(self):
        from core.browser_memory import explicit_memory_request
        self.assertTrue(explicit_memory_request(
            "Benim test kodum CANO-2026-1103. Bunu hafızana kaydet ve hatırla."))
        self.assertFalse(explicit_memory_request("Sana kaydetmeni söylediğim test kodu neydi?"))
        self.assertFalse(explicit_memory_request("Selam!"))

    def test_memory_context_for_test_code_query(self):
        saved = [new_memory("Benim test kodum CANO-2026-1103", ["test", "kod"])]
        self.assertIn("CANO-2026-1103",
                      memory_context(saved, "Sana kaydetmeni söylediğim test kodu neydi?"))


if __name__ == "__main__":
    unittest.main()
