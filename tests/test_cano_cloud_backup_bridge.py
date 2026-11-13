"""Fail-closed local tests; synthetic source and no real Render connections."""
import unittest
from scripts.cano_cloud_backup_bridge import authorized, parse_range, RescueState
from scripts.cano_install_pg18_client import fetch_verified

class Tests(unittest.TestCase):
    def test_token_auth(self):
        token="a"*64
        self.assertTrue(authorized("Bearer "+token,token))
        for bad in (None,token,"bearer "+token,"Bearer "+("b"*64),"Bearer "+token+"x"):
            self.assertFalse(authorized(bad,token))
        self.assertFalse(authorized("Bearer " + token,""))
    def test_ranges_restricted(self):
        self.assertEqual((0,9),parse_range(None,10))
        self.assertEqual((4,8),parse_range("bytes=4-8",10))
        self.assertEqual((9,9),parse_range("bytes=9-",10))
        self.assertEqual((0,8*1024*1024-1),parse_range(None,16*1024*1024))
        for bad in ("bytes=-1","bytes=100-", "bytes=5-4","bytes=0-0,1-1", "0-9", "bytes=1-2\r\nInjected"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_range(bad,10)
    def test_failed_status_no_false_backup(self):
        state=RescueState({"status":"pg18_readonly_connection_verified","internal_readonly_verified":True})
        self.assertFalse(state.health()["real_backup_created"])
        self.assertIsNone(state.artifact("archive"))
    def test_backup_will_not_start_without_source_gate(self):
        # Regression: a valid PGDMP can still be an empty/wrong database dump.
        # No database or real backup is accessed by this test.
        from unittest.mock import patch
        state = RescueState({"internal_readonly_verified": True})
        with patch("scripts.cano_cloud_backup_bridge.make_encrypted_backup") as backup:
            state.run_once()
        self.assertEqual("failed", state.backup_state)
        backup.assert_not_called()  # no verified app source, no dump

    def test_full_source_profile_is_required_before_dump(self):
        # Only simulated URIs and mocks: proves the order, no real PG access.
        import os
        from unittest.mock import patch
        required = {
            "CANO_RENDER_INTERNAL_URL":
                "postgresql://fake:fake@dpg-synthetic-a.region.render.com/research_library_persistent_db",
            "CANO_REQUIRED_RENDER_HOST_PREFIX": "dpg-synthetic-a",
            "CANO_REQUIRED_RENDER_DATABASE": "research_library_persistent_db",
        }
        state = RescueState({"internal_readonly_verified": True})
        with patch.dict(os.environ, required), patch(
                "scripts.cano_cloud_backup_bridge.require_application_source",
                return_value={"profile": "full", "nonempty_table_verified": True}) as gate, patch(
                "scripts.cano_cloud_backup_bridge.make_encrypted_backup",
                side_effect=RuntimeError("synthetic stop after safe preflight")) as backup:
            state.run_once()
        self.assertEqual("failed", state.backup_state)
        gate.assert_called_once()
        self.assertEqual(gate.call_args.args[1], "full")
        self.assertEqual(gate.call_args.kwargs["expected_database"],
                         "research_library_persistent_db")
        self.assertTrue(gate.call_args.kwargs["psql_bin"].endswith("psql18"))
        backup.assert_called_once()

    def test_pinned_source_mismatch_never_reaches_dump(self):
        import os
        from unittest.mock import patch
        wrong = {
            "CANO_RENDER_INTERNAL_URL":
                "postgresql://fake:fake@wrong.example.net/other_db",
            "CANO_REQUIRED_RENDER_HOST_PREFIX": "dpg-synthetic-a",
            "CANO_REQUIRED_RENDER_DATABASE": "research_library_persistent_db",
        }
        state = RescueState({"internal_readonly_verified": True})
        with patch.dict(os.environ, wrong), patch(
                "scripts.cano_cloud_backup_bridge.require_application_source") as gate, patch(
                "scripts.cano_cloud_backup_bridge.make_encrypted_backup") as backup:
            state.run_once()
        self.assertEqual("failed", state.backup_state)
        gate.assert_not_called()
        backup.assert_not_called()

    def test_official_binary_restricts_file_names(self):
        with self.assertRaises(RuntimeError):
            fetch_verified("untrusted.deb",1,"0"*64)

if __name__ == "__main__":
    unittest.main()