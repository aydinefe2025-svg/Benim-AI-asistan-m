"""Prevent owner-only Notion upload authorization from crossing HTTP redirects.

Only synthetic requests/files; never accesses Notion, Render, secrets, or DBs.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.request import Request, HTTPRedirectHandler, build_opener

from scripts import cano_cloud_encrypted_export as exporter


class _FakeUploadResponse:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _):
        return b'{"status":"uploaded"}'


class UploadRedirectRegression(unittest.TestCase):
    def test_cross_origin_302_cannot_forward_bearer(self):
        token = "Bearer synthetic-test-not-a-real-token"
        request = Request(
            "https://api.notion.com/v1/mcp/file_uploads/test/send",
            data=b"synthetic", headers={"Authorization": token}, method="POST")
        self.assertIsNone(exporter._RejectUploadRedirect().redirect_request(
            request, None, 302, "Found", {}, "https://untrusted.invalid/"))
        self.assertIsNone(exporter._RejectUploadRedirect().redirect_request(
            request, None, 303, "See Other", {},
            "https://api.notion.com/v1/mcp/other"))
        self.assertIsNone(exporter._RejectUploadRedirect().redirect_request(
            request, None, 307, "Temporary Redirect", {},
            "https://untrusted.invalid/"))
        self.assertIsNone(exporter._RejectUploadRedirect().redirect_request(
            request, None, 308, "Permanent Redirect", {},
            "https://untrusted.invalid/"))

    def test_custom_opener_has_no_permissive_redirect_handler(self):
        handlers = [h for h in build_opener(exporter._RejectUploadRedirect()).handlers
                    if isinstance(h, HTTPRedirectHandler)]
        self.assertEqual(1, len(handlers))
        self.assertIsInstance(handlers[0], exporter._RejectUploadRedirect)

    def test_offsite_worker_uses_only_non_redirecting_opener(self):
        previous = dict(exporter._state)
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                archive = root / "test.canoenc"
                receipt = root / "receipt.json"
                archive.write_bytes(b"CANOENC1synthetic-ciphertext-not-plaintext")
                receipt.write_text('{"source":"synthetic"}', encoding="utf-8")

                def synthetic_backup():
                    exporter._state.update(
                        phase="ready", archive=str(archive), receipt=str(receipt))

                mock_opener = MagicMock()
                mock_opener.open.return_value = _FakeUploadResponse()
                with patch.dict(os.environ, {
                     "CANO_NOTION_UPLOAD_URL":
                        "https://api.notion.com/v1/mcp/file_uploads/synthetic/send",
                     "CANO_NOTION_UPLOAD_AUTH": "Bearer " + "a" * 64,
                }), patch.object(exporter, "_root", root), \
                     patch.object(exporter, "_worker", side_effect=synthetic_backup), \
                     patch.object(exporter, "build_opener", return_value=mock_opener, create=True), \
                     patch.object(exporter, "urlopen", side_effect=AssertionError(
                         "Default opener must never send a bearer token"), create=True):
                    exporter._state["phase"] = "idle"
                    exporter._auto_upload_worker()
                    self.assertEqual("upload_http_accepted",
                                     exporter._state["offsite_phase"])
                    mock_opener.open.assert_called_once()
                    sent, = mock_opener.open.call_args.args
                    self.assertEqual("POST", sent.get_method())
                    self.assertEqual("api.notion.com", sent.host)
                    self.assertEqual("Bearer " + "a" * 64,
                                     sent.get_header("Authorization"))
                    self.assertNotIn(b"a" * 64, sent.data)
        finally:
            exporter._state.clear()
            exporter._state.update(previous)


if __name__ == "__main__":
    unittest.main()
