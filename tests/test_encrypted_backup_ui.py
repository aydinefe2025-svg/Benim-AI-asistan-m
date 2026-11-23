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

    def test_portable_download_survives_a_timestamp_only_streamlit_rerun(self):
        from datetime import datetime, timezone
        from unittest.mock import patch
        from core.cano_backup_bundle import create_portable_bundle

        colony = {part: [] for part in ("agents", "feedback", "reviews", "missions")}
        kwargs = dict(colony=colony, memories=[], research_tasks=b"{}",
                      authorized_queue=[], organism_records=[])
        with patch("core.cano_backup_bundle.datetime") as clock:
            clock.now.return_value = datetime(2026, 11, 23, 10, 30, tzinfo=timezone.utc)
            first = create_portable_bundle(**kwargs)
            clock.now.return_value = datetime(2026, 11, 23, 10, 31, tzinfo=timezone.utc)
            second = create_portable_bundle(**kwargs)

        self.assertNotEqual(first, second)
        password = "correct-horse-staple-cano-backup"
        st = FakeSt(passphrase=password, confirm=password, submit=True)
        render_encrypted_download(st, label="Download", filename="cano.canoenc",
                                  plaintext=first, storage_key="backup")
        self.assertIsNotNone(st.download)
        prepared = st.download["data"]
        self.assertEqual(decrypt_backup(prepared, password), first)

        # Streamlit executes the page again after submitting the form.
        st.download = None
        render_encrypted_download(st, label="Download", filename="cano.canoenc",
                                  plaintext=second, storage_key="backup")
        self.assertIsNotNone(st.download, "Rerun must not erase a prepared download")
        self.assertEqual(st.download["data"], prepared)


    def test_portable_download_invalidates_on_changed_owner_records(self):
        from core.cano_backup_bundle import create_portable_bundle

        old = {part: [] for part in ("agents", "feedback", "reviews", "missions")}
        changed = {**old, "agents": [{"id": "agent-2", "role": "researcher"}]}
        inputs = dict(memories=[], research_tasks=b"{}", authorized_queue=[],
                      organism_records=[])
        first = create_portable_bundle(colony=old, **inputs)
        second = create_portable_bundle(colony=changed, **inputs)
        password = "correct-horse-staple-cano-backup"
        st = FakeSt(passphrase=password, confirm=password, submit=True)
        render_encrypted_download(st, label="Download", filename="cano.canoenc",
                                  plaintext=first, storage_key="backup")
        self.assertIsNotNone(st.download)
        st.download = None
        render_encrypted_download(st, label="Download", filename="cano.canoenc",
                                  plaintext=second, storage_key="backup")
        self.assertIsNone(st.download, "Changed owner data must invalidate ciphertext")
        self.assertIsNone(st.session_state["backup_encrypted"])

    def test_non_portable_payload_keeps_byte_exact_invalidation(self):
        password = "correct-horse-staple-cano-backup"
        st = FakeSt(passphrase=password, confirm=password, submit=True)
        render_encrypted_download(st, label="Download", filename="other.canoenc",
                                  plaintext=b"original source", storage_key="backup")
        self.assertIsNotNone(st.download)
        st.download = None
        render_encrypted_download(st, label="Download", filename="other.canoenc",
                                  plaintext=b"modified source", storage_key="backup")
        self.assertIsNone(st.download)
        self.assertIsNone(st.session_state["backup_encrypted"])


    def test_invalid_source_clears_previous_ciphertext_and_password_fields(self):
        password = "correct-horse-staple-cano-backup"
        for broken_source in (b"", b"x" * (20 * 1024 * 1024 + 1)):
            with self.subTest(source_bytes=len(broken_source)):
                st = FakeSt(passphrase=password, confirm=password, submit=True)
                render_encrypted_download(st, label="Download",
                                          filename="cano.canoenc",
                                          plaintext=b"original records", storage_key="backup")
                self.assertIsNotNone(st.session_state["backup_encrypted"])
                self.assertIsNotNone(st.download)
                self.assertTrue(st.session_state["backup_source_digest"])

                # An export failure must never retain a previously prepared
                # ciphertext or sensitive form values in Streamlit session state.
                st.session_state["backup_passphrase"] = "stale-secret"
                st.session_state["backup_confirm"] = "stale-secret"
                st.download = None
                render_encrypted_download(st, label="Download",
                                          filename="cano.canoenc",
                                          plaintext=broken_source, storage_key="backup")

                self.assertIsNone(st.download)
                self.assertIsNone(st.session_state.get("backup_encrypted"))
                self.assertFalse(st.session_state.get("backup_source_digest"))
                self.assertEqual(st.session_state.get("backup_passphrase"), "")
                self.assertEqual(st.session_state.get("backup_confirm"), "")
                self.assertTrue(st.errors)


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

