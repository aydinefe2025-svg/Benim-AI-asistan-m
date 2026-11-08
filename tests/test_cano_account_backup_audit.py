"""Real CANOENC1 structure regression tests, no user data or passwords."""
import base64
from contextlib import redirect_stdout, redirect_stderr
from hashlib import sha256
from io import BytesIO, StringIO
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

PATH=Path(__file__).resolve().parents[1]/"scripts"/"cano_account_backup_audit.py"
SPEC=importlib.util.spec_from_file_location("audit", PATH)
audit=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
PASSPHRASE="synthetic-private-password-for-only-this-test"

def make_blob(*, version=2, missing=None, corrupt_manifest=False, invalid_lab=False):
    missing=missing or []
    items={"cano-colony.json":{"agents":[{"role":"synthetic"}],"feedback":[],"reviews":[],"missions":[]},
           "memory-library.json":{"schema":"test","entries":[]},
           "research-tasks.json":{"schema":"research-task-export-v1","tasks":[],"available":True},
           "authorized-queue.json":{"schema":"cano-authorized-queue-export-v1","jobs":[],"available":True}}
    if version==2:
        raw=json.dumps({"toy_data":7},sort_keys=True).encode()
        sh=sha256(raw).hexdigest()
        items["organism-lab-records.json"]={"schema":"cano-organism-lab-export-v1","records":[{"record_id":f"cano-organism-lab-v1-world-{sh}","kind":"world","sha256":sh,"data_b64":base64.b64encode(raw if not invalid_lab else b"garbled").decode()}]}
    blobs={n:json.dumps(v,sort_keys=True).encode() for n,v in items.items()}
    manifest={"schema":f"cano-portable-backup-v{version}","sources_available":{n:n not in missing for n in audit.REQUIRED_SOURCES},
              "components":{n:{"size_bytes":len(v),"sha256":sha256(v).hexdigest()} for n,v in blobs.items()}}
    if corrupt_manifest:manifest["components"]["cano-colony.json"]["sha256"]="f"*64
    out=BytesIO()
    with ZipFile(out,"w") as z:
        for n,v in blobs.items():z.writestr(n,v)
        z.writestr("manifest.json",json.dumps(manifest).encode())
    salt,nonce=b"s"*16,b"n"*12
    hdr=audit.MAGIC+salt+nonce
    key=Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(PASSPHRASE.encode())
    return hdr+AESGCM(key).encrypt(nonce,out.getvalue(),hdr)

class Tests(unittest.TestCase):
    def test_v2_complete_owner_scope_not_full_postgresql(self):
        a=audit.audit_export(make_blob(),PASSPHRASE)
        self.assertTrue(a["owner_scope_sections_all_available"])
        self.assertFalse(a["full_postgresql_disaster_recovery"])
        self.assertFalse(a["postgres_revision_history_included"])
        self.assertEqual(a["organism_lab_records_in_export"],1)
        self.assertEqual(a["status"],"OWNER_SCOPE_READY_NOT_FULL_PG")
    def test_live_v1_is_partial_missing_organism(self):
        a=audit.audit_export(make_blob(version=1),PASSPHRASE)
        self.assertFalse(a["owner_scope_sections_all_available"])
        self.assertIn("organism_lab",a["missing_owner_scope_sections"])
        self.assertEqual(a["status"],"OWNER_SCOPE_PARTIAL")
    def test_missing_mandatory_source_is_partial(self):
        a=audit.audit_export(make_blob(missing=["research_tasks"]),PASSPHRASE)
        self.assertEqual(a["missing_owner_scope_sections"],["research_tasks"])
    def test_wrong_passphrase_rejected(self):
        with self.assertRaises(audit.AuditError):audit.audit_export(make_blob(),"incorrect-but-long-password")
    def test_tampered_ciphertext_rejected(self):
        blob=bytearray(make_blob());blob[-12]^=1
        with self.assertRaises(audit.AuditError):audit.audit_export(bytes(blob),PASSPHRASE)
    def test_corrupted_component_manifest_rejected(self):
        with self.assertRaisesRegex(audit.AuditError,"integrity mismatch"):
            audit.audit_export(make_blob(corrupt_manifest=True),PASSPHRASE)
    def test_invalid_organism_record_rejected(self):
        with self.assertRaisesRegex(audit.AuditError,"hash"):
            audit.audit_export(make_blob(invalid_lab=True),PASSPHRASE)
    def test_reject_giant_or_not_cano_export(self):
        with self.assertRaises(audit.AuditError):audit.audit_export(b"not a valid archive",PASSPHRASE)
        with self.assertRaises(audit.AuditError):audit.audit_export(b"x"*(audit.MAX_PLAINTEXT_BYTES+audit.HEADER_BYTES+18),PASSPHRASE)
    def test_offline_cli_never_echoes_passphrase_or_user_data(self):
        with tempfile.TemporaryDirectory() as d:
            filename=Path(d)/"synthetic.canoenc";filename.write_bytes(make_blob())
            buf=StringIO()
            with patch.object(audit,"getpass",return_value=PASSPHRASE),redirect_stdout(buf):
                code=audit.main([str(filename)])
            self.assertEqual(code,0)
            self.assertNotIn(PASSPHRASE,buf.getvalue())
            self.assertNotIn("synthetic",buf.getvalue())
            self.assertTrue(json.loads(buf.getvalue())["zip_manifest_and_section_digests_verified"])
    def test_live_v1_cli_exit_nonzero_without_content(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/"partial.canoenc";file.write_bytes(make_blob(version=1))
            buf=StringIO()
            with patch.object(audit,"getpass",return_value=PASSPHRASE),redirect_stdout(buf):
                rc=audit.main([str(file)])
            self.assertEqual(rc,2)
            self.assertIn("OWNER_SCOPE_PARTIAL",buf.getvalue())
    def test_existing_application_encrypt_and_portable_bundle_contract(self):
        # Standalone ZIP users can run the first 11 tests without the app repo;
        # GitHub CI verifies this against the ACTUAL production implementation.
        try:
            from core.backup_encryption import encrypt_backup
            from core.cano_backup_bundle import create_portable_bundle
        except ImportError:
            self.skipTest("App core modules are only present inside full CANO repository")
        v2 = create_portable_bundle(
            colony={"agents":[],"feedback":[],"reviews":[],"missions":[]},
            memories=[],research_tasks=[],authorized_queue=[],organism_records=[])
        ciphertext=encrypt_backup(v2,PASSPHRASE)
        result=audit.audit_export(ciphertext,PASSPHRASE)
        self.assertTrue(result["owner_scope_sections_all_available"])
        self.assertFalse(result["full_postgresql_disaster_recovery"])
        v1 = create_portable_bundle(
            colony={"agents":[],"feedback":[],"reviews":[],"missions":[]},
            memories=[],research_tasks=[],authorized_queue=[])
        self.assertEqual(audit.audit_export(encrypt_backup(v1,PASSPHRASE),PASSPHRASE)["status"],"OWNER_SCOPE_PARTIAL")

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            original=Path(d)/"real";original.write_bytes(make_blob())
            link=Path(d)/"link"
            try:link.symlink_to(original)
            except (OSError,NotImplementedError):self.skipTest("symlink unsupported")
            buf=StringIO()
            with redirect_stderr(buf):rc=audit.main([str(link)])
            self.assertEqual(rc,3)
            self.assertNotIn(str(original),buf.getvalue())

if __name__=="__main__":unittest.main()
