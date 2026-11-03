import unittest

from core.authentication import (
    auth_is_required,
    authenticated_owner_key,
    oidc_is_configured,
    render_auth_gate,
)


class AuthenticationTests(unittest.TestCase):
    def test_auth_is_disabled_only_without_explicit_truthy_setting(self):
        self.assertFalse(auth_is_required({}))
        for value in ("1", "true", "YES", "on"):
            self.assertTrue(auth_is_required({"APP_AUTH_REQUIRED": value}))
        self.assertFalse(auth_is_required({"APP_AUTH_REQUIRED": "false"}))

    def test_oidc_requires_all_streamlit_settings(self):
        self.assertFalse(oidc_is_configured({}))
        self.assertTrue(oidc_is_configured({"auth": {
            "redirect_uri": "https://example.test/oauth2callback",
            "cookie_secret": "local-test-secret",
            "owner_key_secret": "stable-owner-secret",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        }}))
        self.assertFalse(oidc_is_configured({"auth": {
            "redirect_uri": "https://example.test/oauth2callback",
            "cookie_secret": "local-test-secret",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        }}))

    def test_owner_key_is_stable_opaque_and_issuer_scoped(self):
        claims = {"iss": "https://accounts.google.com", "sub": "private-subject",
                  "email": "private@example.test"}
        first = authenticated_owner_key(claims, "test-cookie-secret")
        self.assertEqual(first, authenticated_owner_key(claims, "test-cookie-secret"))
        self.assertNotIn(claims["email"], first)
        self.assertNotIn(claims["sub"], first)
        self.assertNotEqual(first, authenticated_owner_key(
            {"iss": "https://other-issuer.test", "sub": claims["sub"]},
            "test-cookie-secret",
        ))
        self.assertIsNone(authenticated_owner_key({"iss": "issuer"}, "secret"))

    def test_cookie_rotation_does_not_change_owner_key(self):
        claims = {"iss": "https://accounts.google.com", "sub": "subject-1"}
        class Sidebar:
            def button(self, *args, **kwargs):
                pass

        class Streamlit:
            sidebar = Sidebar()
            user = {**claims, "is_logged_in": True}
            def __init__(self, cookie_secret):
                self.secrets = {"auth": {
                    "redirect_uri": "https://example.test/oauth2callback",
                    "cookie_secret": cookie_secret,
                    "owner_key_secret": "stable-owner-secret",
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                    "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
                }}
            def logout(self):
                pass

        original = render_auth_gate(Streamlit("old-cookie"), {"APP_AUTH_REQUIRED": "true"})
        rotated = render_auth_gate(Streamlit("new-cookie"), {"APP_AUTH_REQUIRED": "true"})
        self.assertEqual(original, rotated)


if __name__ == "__main__":
    unittest.main()
