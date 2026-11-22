"""Regression tests for owner-local DPAPI to P0 restore, no real secrets."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "scripts"))


class OwnerLocalDPAPIRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.archive = self.root / "CANO_test.canoenc"
        self.archive.write_bytes(b"CANOENC1" + b"n" * 12 + b"synthetic" * 8 + b"t" * 16)
        self.sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.protected = self.root / "CANO_test_key.dpapi"
        self.protected.write_bytes(b"synthetic-dpapi-blob-fixture")

    def test_invalid_ciphertext_hash_never_unwraps_private_key(self):
        from cano_owner_dpapi_restore import run_local_recovery, RecoveryBlocked
        with patch("cano_owner_dpapi_restore._unprotect_current_user") as unwrap:
            with self.assertRaises(RecoveryBlocked):
                run_local_recovery(self.archive, self.protected, "0" * 64)
            unwrap.assert_not_called()

    def test_valid_verify_restores_previous_process_environment(self):
        from cano_owner_dpapi_restore import run_local_recovery
        raw_key = bytes.fromhex("5a" * 32)
        fake_proof = {"authenticated": True, "plaintext_sha256": "1" * 64,
                      "plaintext_size_bytes": 128, "isolated_restore_verified": False}
        with patch("cano_owner_dpapi_restore._unprotect_current_user",return_value=bytearray(raw_key)), \
             patch("cano_owner_dpapi_restore.verify_encrypted_archive_direct",return_value=fake_proof) as verify, \
             patch.dict(os.environ,{"CANO_BACKUP_KEY_HEX": "preexisting", "CANO_RESTORE_DATABASE_URL": "untouched"}):
            result = run_local_recovery(self.archive, self.protected, self.sha)
            self.assertEqual(os.environ["CANO_BACKUP_KEY_HEX"], "preexisting")
        self.assertEqual(result["ciphertext_sha256"],self.sha)
        self.assertTrue(result["authenticated"])
        self.assertFalse(result["isolated_restore_verified"])
        self.assertNotIn(raw_key.hex(),str(result))
        verify.assert_called_once()

    def test_no_preexisting_secret_is_left_in_process_environment(self):
        from cano_owner_dpapi_restore import run_local_recovery
        with patch("cano_owner_dpapi_restore._unprotect_current_user",return_value=bytearray(bytes.fromhex("6b" * 32))), \
             patch("cano_owner_dpapi_restore.verify_encrypted_archive_direct",return_value={"authenticated": True}), \
             patch.dict(os.environ,{},clear=True):
            run_local_recovery(self.archive, self.protected, self.sha)
            self.assertNotIn("CANO_BACKUP_KEY_HEX",os.environ)

    def test_restore_only_with_explicit_confirmation(self):
        from cano_owner_dpapi_restore import run_local_recovery, RecoveryBlocked
        with patch("cano_owner_dpapi_restore._unprotect_current_user") as unwrap:
            with self.assertRaises(RecoveryBlocked):
                run_local_recovery(self.archive,self.protected,self.sha,restore_isolated=True,confirm=False)
            unwrap.assert_not_called()

    def test_restore_delegates_to_existing_isolation_gate_after_authentication(self):
        from cano_owner_dpapi_restore import run_local_recovery
        with patch("cano_owner_dpapi_restore._unprotect_current_user",return_value=bytearray(bytes.fromhex("5a"*32))), \
             patch("cano_owner_dpapi_restore.verify_encrypted_archive_direct",return_value={"authenticated": True}), \
             patch("cano_owner_dpapi_restore.restore_to_empty_database",return_value={
                 "restored_to_new_database":True,"target_database_name":"cano_restore_smoketest"
             }) as restore:
            report=run_local_recovery(self.archive,self.protected,self.sha,
                                      restore_isolated=True,confirm=True)
        self.assertTrue(report["isolated_restore_verified"])
        self.assertTrue(report["authenticated"])
        restore.assert_called_once()
        self.assertTrue(restore.call_args.kwargs["confirm"])

    def test_wrong_key_or_unavailable_dpapi_never_claims_success(self):
        from cano_owner_dpapi_restore import run_local_recovery, RecoveryBlocked
        with patch("cano_owner_dpapi_restore._unprotect_current_user",side_effect=RuntimeError("SECRET-NEVER-LOG")):
            with self.assertRaises(RecoveryBlocked) as err:
                run_local_recovery(self.archive,self.protected,self.sha)
        self.assertNotIn("SECRET-NEVER-LOG",str(err.exception))

    def test_symlink_and_non_dpapi_files_refused_before_unprotect(self):
        from cano_owner_dpapi_restore import run_local_recovery, RecoveryBlocked
        with patch("cano_owner_dpapi_restore._unprotect_current_user") as unwrap:
            bad=self.root / "notprotected.txt"
            bad.write_bytes(b"x"*200)
            with self.assertRaises(RecoveryBlocked):
                run_local_recovery(self.archive,bad,self.sha)
            link=self.root / "link.dpapi"
            try: link.symlink_to(self.protected)
            except OSError: pass
            else:
                with self.assertRaises(RecoveryBlocked):
                    run_local_recovery(self.archive,link,self.sha)
            unwrap.assert_not_called()

    @unittest.skipUnless(sys.platform=="win32","Windows CurrentUser DPAPI only")
    def test_native_currentuser_dpapi_roundtrip_synthetic_secret(self):
        from cano_owner_dpapi_restore import _unprotect_current_user
        import ctypes
        from ctypes import wintypes
        class Blob(ctypes.Structure):
            _fields_=[("cbData",wintypes.DWORD),("pbData",ctypes.POINTER(ctypes.c_ubyte))]
        payload=b"5a"*32
        buf=(ctypes.c_ubyte*len(payload)).from_buffer_copy(payload)
        source=Blob(len(payload),buf)
        sealed=Blob()
        api=ctypes.WinDLL("crypt32",use_last_error=True).CryptProtectData
        api.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,
                      ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        api.restype=wintypes.BOOL
        self.assertTrue(api(ctypes.byref(source),None,None,None,None,0,ctypes.byref(sealed)))
        try:
            raw=ctypes.string_at(sealed.pbData,sealed.cbData)
        finally:
            ctypes.WinDLL("kernel32",use_last_error=True).LocalFree(sealed.pbData)
        pt=_unprotect_current_user(raw)
        self.assertEqual(bytes(pt),payload)
        for i in range(len(pt)):pt[i]=0


if __name__=="__main__":
    unittest.main()
