import unittest

from core.backup_encryption import decrypt_backup, encrypt_backup, prepare_encrypted_download


class BackupEncryptionTests(unittest.TestCase):
    def test_password_encrypted_backup_round_trip(self):
        plain = "Türkçe CANO yedeği — özel veri".encode("utf-8")
        encrypted = encrypt_backup(plain, "dogru-ve-uzun-yedek-parolasi-2026")
        self.assertNotIn(plain, encrypted)
        self.assertEqual(decrypt_backup(encrypted, "dogru-ve-uzun-yedek-parolasi-2026"), plain)

    def test_each_encryption_uses_fresh_salt_and_nonce(self):
        first = encrypt_backup(b"private", "dogru-ve-uzun-yedek-parolasi-2026")
        second = encrypt_backup(b"private", "dogru-ve-uzun-yedek-parolasi-2026")
        self.assertNotEqual(first, second)

    def test_wrong_password_and_tampering_fail_closed(self):
        encrypted = encrypt_backup(b"private", "dogru-ve-uzun-yedek-parolasi-2026")
        with self.assertRaisesRegex(ValueError, "Wrong passphrase"):
            decrypt_backup(encrypted, "yanlis-ve-uzun-yedek-parolasi-2026")
        corrupt = bytearray(encrypted)
        corrupt[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "Wrong passphrase"):
            decrypt_backup(bytes(corrupt), "dogru-ve-uzun-yedek-parolasi-2026")

    def test_password_and_format_bounds_are_enforced(self):
        with self.assertRaises(ValueError):
            encrypt_backup(b"private", "short")
        with self.assertRaises(ValueError):
            decrypt_backup(b"not a CANO archive", "long-enough-password")
        with self.assertRaises(ValueError):
            encrypt_backup(b"", "dogru-ve-uzun-yedek-parolasi-2026")

    def test_streamlit_callback_clears_password_and_stores_only_ciphertext(self):
        class FakeSt:
            session_state = {
                "export_passphrase": "dogru-ve-uzun-yedek-parolasi-2026",
                "export_confirm": "dogru-ve-uzun-yedek-parolasi-2026",
            }

        fake = FakeSt()
        prepare_encrypted_download(fake, "export", b"private")
        self.assertEqual(fake.session_state["export_passphrase"], "")
        self.assertEqual(fake.session_state["export_confirm"], "")
        self.assertIsInstance(fake.session_state["export_encrypted"], bytes)
        self.assertEqual(fake.session_state["export_error"], "")
        self.assertEqual(
            decrypt_backup(fake.session_state["export_encrypted"],
                           "dogru-ve-uzun-yedek-parolasi-2026"), b"private")


if __name__ == "__main__":
    unittest.main()

