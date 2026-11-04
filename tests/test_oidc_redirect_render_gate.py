"""Regression: Render OIDC login must reject a wrong public callback before login UI."""
import unittest
from types import SimpleNamespace

from core.authentication import render_auth_gate


class GateStopped(Exception):
    pass


class RenderRedirectGateTests(unittest.TestCase):
    @staticmethod
    def _secrets(redirect):
        return {"auth": {
            "redirect_uri": redirect,
            "cookie_secret": "synthetic-cookie-only",
            "owner_key_secret": "synthetic-owner-only",
            "client_id": "synthetic-id",
            "client_secret": "synthetic-client-only",
            "server_metadata_url":
                "https://accounts.google.com/.well-known/openid-configuration",
        }}

    def _gate(self, redirect):
        errors, titles = [], []

        def stop():
            raise GateStopped()

        st = SimpleNamespace(
            secrets=self._secrets(redirect),
            user={"is_logged_in": False},
            error=errors.append,
            title=titles.append,
            button=lambda *args, **kwargs: None,
            login=lambda: None,
            stop=stop,
        )
        with self.assertRaises(GateStopped):
            render_auth_gate(st, {
                "APP_AUTH_REQUIRED": "1",
                "RENDER": "true",
                "RENDER_EXTERNAL_URL": "https://cano-test.onrender.com",
            })
        return errors, titles

    def test_wrong_render_origin_fails_closed_before_login_button(self):
        errors, titles = self._gate(
            "https://other-host.onrender.com/oauth2callback")
        self.assertTrue(errors, "Invalid origin must display a safe config error")
        self.assertEqual(titles, [], "Invalid origin must not offer login")

    def test_wrong_callback_path_fails_closed_before_login_button(self):
        errors, titles = self._gate("https://cano-test.onrender.com/wrong")
        self.assertTrue(errors, "Invalid callback path must display a safe error")
        self.assertEqual(titles, [], "Invalid callback path must not offer login")

    def test_matching_render_callback_still_offers_login(self):
        errors, titles = self._gate(
            "https://cano-test.onrender.com/oauth2callback")
        self.assertEqual(errors, [])
        self.assertEqual(titles, ["Giriş gerekli"])


if __name__ == "__main__":
    unittest.main()
