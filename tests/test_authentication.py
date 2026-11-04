import unittest

from core.authentication import (
    auth_is_required,
    authenticated_owner_key,
    oidc_is_configured,
)


class AuthenticationTests(unittest.TestCase):
    def test_auth_is_disabled_only_without_explicit_truthy_setting(self):
        self.assertFalse(auth_is_required({}))
        for value in ("1", "true", "YES", "on"):
            self.assertTrue(auth_is_required({"APP_AUTH_REQUIRED": value}))
        self.assertFalse(auth_is_required({"APP_AUTH_REQUIRED": "false"}))

    def test_malformed_auth_flag_must_fail_closed(self):
        # A typo in a production security toggle must not silently disable login.
        for value in ("tru", "enabled", "2", "perhaps", " true false "):
            with self.subTest(value=value):
                self.assertTrue(auth_is_required({"APP_AUTH_REQUIRED": value}))
        self.assertFalse(auth_is_required({"APP_AUTH_REQUIRED": "off"}))
        self.assertFalse(auth_is_required({"APP_AUTH_REQUIRED": "0"}))

    def test_oidc_requires_all_streamlit_settings(self):
        self.assertFalse(oidc_is_configured({}))
        self.assertTrue(oidc_is_configured({"auth": {
            "redirect_uri": "https://example.test/oauth2callback",
            "cookie_secret": "local-test-secret",
            "owner_key_secret": "separate-stable-owner-secret",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        }}))

    def test_owner_key_is_stable_opaque_and_issuer_scoped(self):
        claims = {"iss": "https://accounts.google.com", "sub": "private-subject",
                  "email": "private@example.test"}
        first = authenticated_owner_key(claims, "test-owner-secret")
        self.assertEqual(first, authenticated_owner_key(claims, "test-owner-secret"))
        self.assertNotIn(claims["email"], first)
        self.assertNotIn(claims["sub"], first)
        self.assertNotEqual(first, authenticated_owner_key(
            {"iss": "https://other-issuer.test", "sub": claims["sub"]},
            "test-owner-secret",
        ))
        self.assertNotEqual(first, authenticated_owner_key(claims, "rotated-owner-secret"))
        self.assertIsNone(authenticated_owner_key({"iss": "issuer"}, "secret"))


if __name__ == "__main__":
    unittest.main()
