"""Adversarial unit tests: synthetic bytes only, no production accounts."""
from pathlib import Path
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
from cano_encrypted_backup import BackupError, make_encrypted_backup, verify_encrypted_backup, decrypt_to_sink, restore_to_empty_database


class EncryptedBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.target=self.root/'private-backups'
        self.dump=self.root/'fake_pg_dump.py'
        self.dump.write_text('#!'+sys.executable+'\n'
            'import os,sys\n'
            'assert os.getenv("PGPASSWORD")=="private-example-secret"\n'
            'assert "CANO_BACKUP_KEY_HEX" not in os.environ\n'
            'assert "private-example-secret" not in " ".join(sys.argv)\n'
            'sys.stdout.buffer.write(b"PGDMP-PRIVATE-DATABASE-CONTENTS\\x00\\x01"*1200)\n')
        self.dump.chmod(self.dump.stat().st_mode|stat.S_IXUSR)
        self.fake=str(self.dump)
        if os.name=='nt':
            wrapper=self.root/'fake_pg_dump.cmd'
            wrapper.write_text('@echo off\r\n"'+sys.executable+'" "'+str(self.dump)+'" %*\r\n')
            self.fake=str(wrapper)
        self.key='1f'*32
        self.env=patch.dict(os.environ,{
            'CANO_BACKUP_KEY_HEX':self.key,
            'DATABASE_URL':'postgresql://user:private-example-secret@localhost/test?sslmode=require'
        })
        self.env.start();self.addCleanup(self.env.stop)

    def test_backup_streams_only_authenticated_ciphertext_and_receipt(self):
        result=make_encrypted_backup(self.target,dump_bin=self.fake)
        files=list(self.target.iterdir())
        self.assertEqual(len(files),2)
        self.assertFalse(any(x.suffix=='.dump' for x in files))
        data=Path(result['archive']).read_bytes()
        self.assertTrue(data.startswith(b'CANOENC1'))
        self.assertNotIn(b'PRIVATE-DATABASE-CONTENTS',data)
        self.assertNotIn('private-example-secret',json.dumps(result))
        report=verify_encrypted_backup(Path(result['receipt']))
        self.assertEqual(report['plaintext_sha256'],result['plaintext_sha256'])
        self.assertEqual(report['archive_sha256'],result['archive_sha256'])
        self.assertEqual(report['authenticated'],True)
        buf=bytearray()
        decrypt_to_sink(Path(result['archive']),lambda b:buf.extend(b))
        self.assertEqual(bytes(buf),b'PGDMP-PRIVATE-DATABASE-CONTENTS\x00\x01'*1200)
        if os.name=='posix':
            self.assertTrue(all((p.stat().st_mode&0o777)==0o600 for p in files))

    def test_wrong_key_and_tampering_fail_before_restore(self):
        result=make_encrypted_backup(self.target,dump_bin=self.fake)
        file=Path(result['archive'])
        with patch.dict(os.environ,{'CANO_BACKUP_KEY_HEX':'22'*32}):
            with self.assertRaises(BackupError):verify_encrypted_backup(Path(result['receipt']))
        arr=bytearray(file.read_bytes());arr[-25]^=1;file.write_bytes(arr)
        with self.assertRaises(BackupError):verify_encrypted_backup(Path(result['receipt']))
        with self.assertRaises(BackupError):restore_to_empty_database(file,target_db_url_env='RESTORE_URL',confirm=True)

    def test_missing_key_blocks_before_archive_created(self):
        with patch.dict(os.environ,{'CANO_BACKUP_KEY_HEX':''}):
            with self.assertRaises(BackupError):make_encrypted_backup(self.target,dump_bin=self.fake)
        self.assertFalse(self.target.exists())

    def test_reject_symlink_destination_and_archive(self):
        link=self.root/'link';link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(BackupError):make_encrypted_backup(link,dump_bin=self.fake)
        result=make_encrypted_backup(self.target,dump_bin=self.fake)
        archive=Path(result['archive']);archive.unlink();archive.symlink_to(self.dump)
        with self.assertRaises(BackupError):verify_encrypted_backup(Path(result['receipt']))

    def test_restore_requires_separate_safe_target_without_process_call(self):
        result=make_encrypted_backup(self.target,dump_bin=self.fake)
        with patch.dict(os.environ,{'RESTORE_URL':'postgresql://user:other@localhost/production'}):
            with self.assertRaises(BackupError):restore_to_empty_database(Path(result['archive']),target_db_url_env='RESTORE_URL',confirm=True)
        with patch.dict(os.environ,{'RESTORE_URL':'postgresql://user:other@localhost/cano_restore_test'}):
            with self.assertRaises(BackupError):restore_to_empty_database(Path(result['archive']),target_db_url_env='RESTORE_URL',confirm=False)

    def test_failing_pg_dump_removes_partial_ciphertext(self):
        bad=self.root/'bad.py'
        bad.write_text('#!'+sys.executable+'\nimport sys\nsys.stdout.buffer.write(b"PGDMP partial")\nsys.exit(2)\n')
        bad.chmod(bad.stat().st_mode|stat.S_IXUSR)
        if os.name=='nt':
            wrapper=self.root/'bad_pg_dump.cmd'
            wrapper.write_text('@echo off\r\n"'+sys.executable+'" "'+str(bad)+'" %*\r\n')
            bad=wrapper
        with self.assertRaises(BackupError):make_encrypted_backup(self.target,dump_bin=str(bad))
        self.assertEqual(list(self.target.iterdir()),[])

    def test_archive_limit_prevents_unbounded_output_and_cleans_up(self):
        with self.assertRaises(BackupError):
            make_encrypted_backup(self.target,dump_bin=self.fake,max_plaintext_bytes=1024)
        self.assertEqual(list(self.target.iterdir()),[])

    def test_receipt_archive_name_cannot_traverse(self):
        self.target.mkdir();receipt=self.target/'evil.receipt.json'
        receipt.write_text(json.dumps({'archive':'../stolen.canoenc'}))
        with self.assertRaises(BackupError):verify_encrypted_backup(receipt)

if __name__=='__main__':unittest.main()
