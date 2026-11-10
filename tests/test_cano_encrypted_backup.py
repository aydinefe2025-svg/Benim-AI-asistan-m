"""Adversarial unit tests: synthetic bytes only, no production accounts."""
from pathlib import Path
import json
import os
import stat
import sys
import tempfile
import time
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
        link=self.root/'link'
        try:
            link.symlink_to(self.root,target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink creation is unavailable in this environment: {exc}")
        with self.assertRaises(BackupError):make_encrypted_backup(link,dump_bin=self.fake)
        result=make_encrypted_backup(self.target,dump_bin=self.fake)
        archive=Path(result['archive']);archive.unlink()
        try:
            archive.symlink_to(self.dump)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink creation is unavailable in this environment: {exc}")
        with self.assertRaises(BackupError):verify_encrypted_backup(Path(result['receipt']))

    def test_restore_uses_authenticated_snapshot_after_original_archive_changes(self):
        """An operator archive may be replaced after the first proof but before pg_restore.

        The restore must stream only the already authenticated immutable copy.
        No real SQL, owner record, network, or pg_restore binary is used.
        """
        result = make_encrypted_backup(self.target, dump_bin=self.fake)
        archive = Path(result['archive'])
        expected = b'PGDMP-PRIVATE-DATABASE-CONTENTS\x00\x01' * 1200

        class RecordingPipe:
            def __init__(self):
                self.chunks = []
                self.closed = False

            def write(self, data):
                self.chunks.append(bytes(data))
                return len(data)

            def close(self):
                self.closed = True

        class FakeRestore:
            def __init__(self):
                self.stdin = RecordingPipe()

            def wait(self, timeout=None):
                return 0

            def poll(self):
                return 0

            def kill(self):
                raise AssertionError('Unexpected forced termination')

        fake_restore = FakeRestore()
        def mutate_original_during_preflight(*args, **kwargs):
            # This hook is reached only AFTER the initial authentication.
            altered = bytearray(archive.read_bytes())
            altered[-25] ^= 1
            archive.write_bytes(altered)
            class Result:
                returncode = 0
                stdout = b'0'
            return Result()

        with patch.dict(os.environ, {'RESTORE_URL':
                'postgresql://user:example@localhost/cano_restore_snapshot'}):
            with patch('cano_encrypted_backup.shutil.which', side_effect=lambda name: name):
                with patch('cano_encrypted_backup.subprocess.run',
                           side_effect=mutate_original_during_preflight):
                    with patch('cano_encrypted_backup.subprocess.Popen',
                               return_value=fake_restore):
                        recovered = restore_to_empty_database(
                            archive, target_db_url_env='RESTORE_URL', confirm=True)

        self.assertTrue(recovered['authenticated'])
        self.assertTrue(recovered['restored_to_new_database'])
        self.assertEqual(b''.join(fake_restore.stdin.chunks), expected)
        self.assertTrue(fake_restore.stdin.closed)

    def test_bad_tag_never_reaches_any_encrypted_restore_sink(self):
        """No tentative plaintext may cross the sink boundary before GCM finalize."""
        result = make_encrypted_backup(self.target, dump_bin=self.fake)
        archive = Path(result["archive"])
        modified = bytearray(archive.read_bytes())
        modified[-1] ^= 1
        archive.write_bytes(modified)
        forwarded = []
        with self.assertRaises(BackupError):
            decrypt_to_sink(archive, forwarded.append)
        self.assertEqual(forwarded, [], "bad-tag plaintext crossed the sink boundary")

    def test_changed_valid_snapshot_never_reaches_restore_child_before_proof(self):
        """The existing private ciphertext snapshot still needs auth-before-write."""
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from types import SimpleNamespace
        from cano_encrypted_backup import _decrypt_from_file
        result = make_encrypted_backup(self.target, dump_bin=self.fake)
        archive = Path(result["archive"])
        nonce = bytes(range(12))
        header = b"CANOENC1" + nonce
        cipher = Cipher(algorithms.AES(bytes.fromhex(self.key)), modes.GCM(nonce)).encryptor()
        cipher.authenticate_additional_data(header)
        replacement = b"PGDMP-authenticated-but-different-synthetic-payload" * 100
        second = header + cipher.update(replacement) + cipher.finalize() + cipher.tag
        sent = []
        class Pipe:
            def write(self, data):
                sent.append(bytes(data))
                return len(data)
            def close(self):
                pass
        child = SimpleNamespace(stdin=Pipe(), wait=lambda timeout: 0, poll=lambda: 0)
        changed = [False]
        def change_private_snapshot_after_first_proof(inp, sink, **kwargs):
            proof = _decrypt_from_file(inp, sink, **kwargs)
            if sink is None and not changed[0]:
                changed[0] = True
                inp.seek(0)
                inp.truncate()
                inp.write(second)
                inp.flush()
            return proof
        with patch.dict(os.environ, {
            "RESTORE_URL": "postgresql://user:other@localhost/cano_restore_snapshot_guard",
        }):
            with patch("cano_encrypted_backup._decrypt_from_file",
                       side_effect=change_private_snapshot_after_first_proof):
                with patch("cano_encrypted_backup.shutil.which", return_value="/synthetic/psql"):
                    with patch("cano_encrypted_backup.subprocess.run",
                               return_value=SimpleNamespace(returncode=0, stdout=b"0")):
                        with patch("cano_encrypted_backup.subprocess.Popen", return_value=child):
                            with self.assertRaises(BackupError):
                                restore_to_empty_database(
                                    archive, target_db_url_env="RESTORE_URL",
                                    confirm=True,
                                )
        self.assertTrue(changed[0])
        self.assertEqual(sent, [], "unverified modified snapshot reached restore child")

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

