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


    def test_owner_switch_purges_private_session_data_not_ui_preferences(self):
        from core import authentication
        isolate = getattr(authentication, "isolate_owner_session", None)
        self.assertTrue(callable(isolate), "Account session isolation missing")
        state = {
            "_cano_session_owner": "oidc_" + "a" * 64,
            "messages": [{"role": "user", "content": "Owner A private"}],
            "saved_memories": [{"id": "A", "content": "Owner A secret"}],
            "_cano_chat_saved": [{"role": "user", "content": "A baseline"}],
            "cano_cockpit_latest_mission": {"task": "A private mission"},
            "cano_organism_lab_campaign_result": {"result": "A"},
            "_cano_chat_task_pending": {"task": "Owner A"},
            "_cano_secure_export_ciphertext": "A ciphertext",
            "_browser_pending": {"note": "A"},
            "lora_specialist_mission_result": {"result": "A"},
            "last_model_used": "Owner A model",
            "last_provider_used": "Owner A provider",
            "user_theme": "dark",
        }
        self.assertTrue(isolate(state, "oidc_" + "b" * 64))
        self.assertEqual(state, {
            "_cano_session_owner": "oidc_" + "b" * 64,
            "user_theme": "dark",
        })

    def test_same_owner_keeps_work_and_unmarked_legacy_session_fails_closed(self):
        from core import authentication
        isolate = getattr(authentication, "isolate_owner_session", None)
        self.assertTrue(callable(isolate), "Account session isolation missing")
        owner = "oidc_" + "a" * 64
        state = {"_cano_session_owner": owner, "messages": ["A"],
                 "saved_memories": ["A"], "user_theme": "light"}
        self.assertFalse(isolate(state, owner))
        self.assertEqual(state["messages"], ["A"])
        self.assertEqual(state["saved_memories"], ["A"])

        # Existing Streamlit clients upgraded mid-session lack the owner marker.
        legacy = {"messages": ["Unknown owner's chat"],
                  "saved_memories": ["Unknown owner's memory"], "user_theme": "dark"}
        self.assertTrue(isolate(legacy, owner))
        self.assertNotIn("messages", legacy)
        self.assertNotIn("saved_memories", legacy)
        self.assertEqual(legacy["user_theme"], "dark")

    def test_live_app_enforces_owner_reset_before_memory_bindings(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "app.py").read_text(
            encoding="utf-8")
        auth = source.index("_OWNER_KEY = render_auth_gate(st, os.environ)")
        reset = source.index("isolate_owner_session(st.session_state, _OWNER_KEY)")
        memory = source.index("_MEMORY_STORE = None")
        self.assertLess(auth, reset)
        self.assertLess(reset, memory)


    def test_logout_gate_discards_previous_owner_data_before_stopping(self):
        from types import SimpleNamespace
        from core.authentication import render_auth_gate

        class Stopped(Exception):
            pass

        def stop():
            raise Stopped()

        state = {
            "_cano_session_owner": "oidc_" + "a" * 64,
            "messages": [{"role": "user", "content": "A private conversation"}],
            "saved_memories": [{"content": "A private note"}],
            "_cano_secure_export_buffer": "A encrypted export",
            "user_theme": "dark",
        }
        auth = {
            "redirect_uri": "https://example.test/oauth2callback",
            "cookie_secret": "unit-test-cookie",
            "owner_key_secret": "unit-test-owner-secret",
            "client_id": "synthetic-client",
            "client_secret": "synthetic-secret",
            "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        }
        st = SimpleNamespace(
            secrets={"auth": auth},
            user={"is_logged_in": False},
            session_state=state,
            title=lambda *_: None,
            button=lambda *_, **__: False,
            login=lambda: None,
            stop=stop,
        )
        with self.assertRaises(Stopped):
            render_auth_gate(
                st, {"APP_AUTH_REQUIRED": "true",
                     "RENDER_EXTERNAL_URL": "https://example.test"}
            )
        self.assertNotIn("messages", state)
        self.assertNotIn("saved_memories", state)
        self.assertNotIn("_cano_secure_export_buffer", state)
        self.assertEqual(state["user_theme"], "dark")
        self.assertIsNone(state["_cano_session_owner"])


if __name__ == "__main__":
    unittest.main()
