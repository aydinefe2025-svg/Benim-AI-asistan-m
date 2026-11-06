import unittest
from contextlib import nullcontext

from core.backup_encryption import decrypt_backup
from core.encrypted_backup_ui import render_encrypted_download


class FakeSt:
    def __init__(self, *, passphrase="", confirm="", submit=False):
        self.session_state = {"backup_passphrase": passphrase,
                              "backup_confirm": confirm}
        self.submit = submit
        self.download = None
        self.errors = []

    def expander(self, *args, **kwargs):
        return nullcontext()

    def form(self, *args, **kwargs):
        return nullcontext()

    def text_input(self, label, *, key, **kwargs):
        return self.session_state.setdefault(key, "")

    def form_submit_button(self, label, *, on_click=None, args=(), **kwargs):
        if self.submit:
            self.submit = False
            on_click(*args)
            return True
        return False

    def error(self, message):
        self.errors.append(message)

    def caption(self, message):
        pass

    def download_button(self, label, **kwargs):
        self.download = kwargs

    def warning(self, message):
        self.errors.append(message)


class EncryptedBackupUiTests(unittest.TestCase):
    def test_matching_password_produces_authenticated_download_and_clears_secret(self):
        password = "correct-horse-staple-cano-backup"
        st = FakeSt(passphrase=password, confirm=password, submit=True)
        render_encrypted_download(st, label="Download", filename="cano.canoenc",
                                  plaintext=b"secret CANO records", storage_key="backup")
        self.assertEqual(st.download["file_name"], "cano.canoenc")
        self.assertEqual(st.download["mime"], "application/octet-stream")
        self.assertEqual(decrypt_backup(st.download["data"], password), b"secret CANO records")
        self.assertEqual(st.session_state["backup_passphrase"], "")
        self.assertEqual(st.session_state["backup_confirm"], "")

    def test_mismatched_password_never_offers_download(self):
        st = FakeSt(passphrase="correct-horse-staple-cano-backup",
                    confirm="different-passphrase-cano", submit=True)
        render_encrypted_download(st, label="Download", filename="cano.canoenc",
                                  plaintext=b"secret CANO records", storage_key="backup")
        self.assertIsNone(st.download)
        self.assertTrue(any("eşleşmiyor" in error for error in st.errors))
        self.assertEqual(st.session_state["backup_passphrase"], "")


if __name__ == "__main__":
    unittest.main()

