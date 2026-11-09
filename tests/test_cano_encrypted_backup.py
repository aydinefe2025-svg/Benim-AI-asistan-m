"""Adversarial unit tests: synthetic bytes only, no production accounts."""
from pathlib import Path
import json
import os
import subprocess
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
from cano_encrypted_backup import (BackupError, make_encrypted_backup,
    verify_encrypted_backup, decrypt_to_sink, restore_to_empty_database,
    _require_pg18_dump_client)


class EncryptedBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.target=self.root/'private-backups'
        self.dump=self.root/'fake_pg_dump.py'
        self.dump.write_text('#!'+sys.executable+'\n'
            'import os,sys\n'
            'if "--version" in sys.argv:\n'
            ' print("pg_dump (PostgreSQL) 18.0")\n'
            ' raise SystemExit(0)\n'
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

    def test_pg18_version_probe_accepts_supported_banner_without_forwarding_secrets(self):
        result = subprocess.CompletedProcess(
            ['pg_dump', '--version'], 0,
            stdout=b'pg_dump (PostgreSQL) 18.3 (Debian 18.3-1.pgdg13+1)')
        with patch.dict(os.environ, {
                'PGPASSWORD': 'sensitive-db-password',
                'API_TOKEN': 'sensitive-provider-token',
                'CANO_BACKUP_KEY_HEX': self.key,
        }):
            with patch('cano_encrypted_backup.subprocess.run',
                       return_value=result) as probe:
                _require_pg18_dump_client(self.fake)
        self.assertNotIn('PGPASSWORD', probe.call_args.kwargs['env'])
        self.assertNotIn('API_TOKEN', probe.call_args.kwargs['env'])
        self.assertNotIn('CANO_BACKUP_KEY_HEX', probe.call_args.kwargs['env'])

    def test_direct_library_backup_rejects_unsafe_pg_dump_before_io(self):
        for banner in (b'pg_dump (PostgreSQL) 17.9',
                       b'pg_dump (PostgreSQL) 19.0',
                       b'pg_dump 18.0',
                       b'pg_dump (PostgreSQL) 18.0' + b' ' * 257):
            with self.subTest(banner=banner[:30]):
                probe_result = subprocess.CompletedProcess(
                    ['pg_dump', '--version'], 0, stdout=banner)
                with patch('cano_encrypted_backup.shutil.which', return_value=self.fake):
                    with patch('cano_encrypted_backup.subprocess.run', return_value=probe_result) as probe:
                        with patch('cano_encrypted_backup.subprocess.Popen') as dump:
                            with patch.dict(os.environ, {
                                'PGPASSWORD': 'sensitive-db-password',
                                'API_TOKEN': 'sensitive-provider-token',
                            }):
                                with self.assertRaises(BackupError):
                                    make_encrypted_backup(self.target, dump_bin=self.fake)
                dump.assert_not_called()
                probe.assert_called_once()
                self.assertNotIn('PGPASSWORD', probe.call_args.kwargs['env'])
                self.assertNotIn('API_TOKEN', probe.call_args.kwargs['env'])
                self.assertNotIn('CANO_BACKUP_KEY_HEX', probe.call_args.kwargs['env'])
                self.assertFalse(self.target.exists())

    def test_direct_library_backup_requires_successful_pg_dump_version_probe(self):
        with patch('cano_encrypted_backup.shutil.which', return_value=self.fake):
            with patch('cano_encrypted_backup.subprocess.run',
                       side_effect=subprocess.TimeoutExpired('pg_dump', 12)):
                with patch('cano_encrypted_backup.subprocess.Popen') as dump:
                    with self.assertRaisesRegex(BackupError, 'Cannot verify'):
                        make_encrypted_backup(self.target, dump_bin=self.fake)
        dump.assert_not_called()
        self.assertFalse(self.target.exists())

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

    def test_tampered_encrypted_stream_never_forwards_plaintext(self):
        """A failed GCM tag must never leak tentative plaintext to a child sink."""
        result = make_encrypted_backup(self.target, dump_bin=self.fake)
        archive = Path(result["archive"])
        altered = bytearray(archive.read_bytes())
        altered[-1] ^= 1
        archive.write_bytes(altered)
        forwarded = []
        with self.assertRaises(BackupError):
            decrypt_to_sink(archive, forwarded.append)
        self.assertEqual(forwarded, [], "unauthenticated bytes reached restore sink")

    def test_changed_valid_archive_between_restore_passes_never_reaches_child(self):
        """A different valid GCM archive cannot be applied after first-pass proof."""
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from types import SimpleNamespace
        first = make_encrypted_backup(self.target, dump_bin=self.fake)
        archive = Path(first["archive"])
        nonce = bytes(range(12))
        header = b"CANOENC1" + nonce
        enc = Cipher(algorithms.AES(bytes.fromhex(self.key)), modes.GCM(nonce)).encryptor()
        enc.authenticate_additional_data(header)
        replacement = b"PGDMP-another-valid-synthetic-archive" * 100
        other = header + enc.update(replacement) + enc.finalize() + enc.tag
        forwarded = []
        class Pipe:
            def write(self, data):
                forwarded.append(bytes(data))
                return len(data)
            def close(self):
                pass
        fake_child = SimpleNamespace(stdin=Pipe(), wait=lambda timeout: 0, poll=lambda: 0)
        original = decrypt_to_sink
        swapped = [False]
        def switch_after_preflight(path, sink, **kwargs):
            proof = original(path, sink, **kwargs)
            if sink is None and not swapped[0]:
                swapped[0] = True
                archive.write_bytes(other)
            return proof
        with patch.dict(os.environ, {
            "RESTORE_URL": "postgresql://user:other@localhost/cano_restore_safety",
        }):
            with patch("cano_encrypted_backup.decrypt_to_sink", side_effect=switch_after_preflight):
                with patch("cano_encrypted_backup.shutil.which", return_value="/synthetic/psql"):
                    with patch("cano_encrypted_backup.subprocess.run",
                               return_value=SimpleNamespace(returncode=0, stdout=b"0")):
                        with patch("cano_encrypted_backup.subprocess.Popen", return_value=fake_child):
                            with self.assertRaises(BackupError):
                                restore_to_empty_database(
                                    archive, target_db_url_env="RESTORE_URL",
                                    confirm=True,
                                )
        self.assertTrue(swapped[0], "first authenticated read never ran")
        self.assertEqual(forwarded, [], "changed archive reached isolated restore child")

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

    def test_restore_never_targets_active_memory_or_queue_database(self):
        # The app uses MEMORY_DATABASE_URL and AGENT_TASK_DATABASE_URL,
        # which can differ from the generic DATABASE_URL variable.
        target_url='postgresql://user:secret@localhost:5432/cano_restore_guard'
        for live_env in ('MEMORY_DATABASE_URL','AGENT_TASK_DATABASE_URL'):
            with self.subTest(active_db=live_env):
                with patch.dict(os.environ,{
                        'DATABASE_URL':'postgresql://user:secret@localhost/different_db',
                        live_env:'postgresql://user:secret@localhost/cano_restore_guard',
                        'RESTORE_URL':target_url}):
                    with patch('cano_encrypted_backup.decrypt_to_sink',
                               side_effect=AssertionError('attempted to decrypt before rejecting live database')):
                        with self.assertRaises(BackupError):
                            restore_to_empty_database(self.root/'nonexistent.canoenc',
                                target_db_url_env='RESTORE_URL',confirm=True)

    def test_restore_rejects_cano_database_url_before_any_process(self):
        # core.storage_config.cano_database_url selects CANO_DATABASE_URL
        # ahead of DATABASE_URL. The restore guard must honor that live alias.
        target = 'postgresql://owner:fake@localhost:5432/cano_restore_active'
        with patch.dict(os.environ, {
            'DATABASE_URL': 'postgresql://owner:fake@localhost/other_database',
            'CANO_DATABASE_URL': 'postgresql://owner:fake@localhost/cano_restore_active',
            'RESTORE_URL': target,
        }):
            with patch('cano_encrypted_backup.decrypt_to_sink',
                       side_effect=AssertionError('decryption occurred before source alias check')):
                with self.assertRaises(BackupError):
                    restore_to_empty_database(
                        self.root / 'nonexistent.canoenc',
                        target_db_url_env='RESTORE_URL', confirm=True)

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

    def test_hung_dump_must_timeout_and_remove_unpublished_files(self):
        """A real pg_dump can stall after first bytes: pipe.read must not hang forever."""
        hanging=self.root/'hang_dump.py'
        hanging.write_text('#!'+sys.executable+'\nimport sys,time\n'
            'sys.stdout.buffer.write(b"PGDMP synthetic partial")\n'
            'sys.stdout.buffer.flush()\n'
            'time.sleep(6)\n', encoding='utf8')
        hanging.chmod(hanging.stat().st_mode|stat.S_IXUSR)
        exe=str(hanging)
        if os.name=='nt':
            wrapper=hanging.with_suffix('.cmd')
            wrapper.write_text('@echo off\r\n"'+sys.executable+'" "'+str(hanging)+'" %*\r\n')
            exe=str(wrapper)
        start=time.monotonic()
        with self.assertRaises(BackupError):
            make_encrypted_backup(self.target,dump_bin=exe,max_seconds=0.4)
        self.assertLess(time.monotonic()-start,5.0)
        self.assertEqual(list(self.target.iterdir()),[])

    def test_receipt_archive_name_cannot_traverse(self):
        self.target.mkdir();receipt=self.target/'evil.receipt.json'
        receipt.write_text(json.dumps({'archive':'../stolen.canoenc'}))
        with self.assertRaises(BackupError):verify_encrypted_backup(receipt)

if __name__=='__main__':unittest.main()
