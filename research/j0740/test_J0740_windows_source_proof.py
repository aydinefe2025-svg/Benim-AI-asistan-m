import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import J0740_windows_source_proof as app

class LauncherTests(unittest.TestCase):
    def test_git_blob_identity(self):
        self.assertEqual(app.git_blob_sha(b'hello'), 'b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0')

    def test_locate_existing_archive_without_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp); d=home/'Downloads';d.mkdir()
            p=d/app.ARCHIVE_FILENAME;p.write_bytes(b'test')
            self.assertEqual(app.locate_archive(None,home),p.resolve())

    def test_missing_or_multiple_archives_do_not_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            with self.assertRaises(FileNotFoundError):app.locate_archive(None,home)
            for folder in ('Downloads','Desktop'):
                d=home/folder;d.mkdir();(d/app.ARCHIVE_FILENAME).write_bytes(b'test')
            with self.assertRaisesRegex(ValueError,'Birden çok'):app.locate_archive(None,home)

    def test_private_summary_omits_paths_and_code_bytes(self):
        raw={'strict_lineage_verified':True,'issues':[],'compressed_archive_checksum_verified':True,
             'selected':{'matching_run_log':{'sha256':'ab'*32,'local_path':'C:/private/out.txt',
                         'actual_tar_member_name':'STU/.../out_run','bytes':65,'status':'FOUND'}}}
        summary=app.public_summary(raw)
        self.assertNotIn('C:/private',json.dumps(summary))
        self.assertNotIn('local_path',json.dumps(summary))
        self.assertEqual(summary['original_members']['matching_run_log']['sha256'],'ab'*32)
        self.assertEqual(summary['scientific_status'],
           'SOURCE_PROVENANCE_ONLY; NO_NATIVE_PHOTON_LIKELIHOOD_OR_EOS_BAYES_POSTERIOR')

    def test_runner_writes_only_redacted_summary_after_scanner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            archive=root/'already_here.tar.gz';archive.write_bytes(b'preexisting fixture')
            result_dir=root/'evidence'
            fake={'strict_lineage_verified':True,'issues':[],'compressed_archive_checksum_verified':True,
                  'source_full_archive_md5_observed_this_scan':app.ARCHIVE_MD5,
                  'selected':{'matching_run_log':{'status':'FOUND','sha256':'b'*64,
                             'local_path':'C:/secret/runlog','actual_tar_member_name':'out_test','bytes':100}}}
            def fake_run(cmd,**kwargs):
                p=Path(cmd[cmd.index('--out')+1]);p.mkdir(parents=True)
                (p/'source_run_probe_report.json').write_text(json.dumps(fake))
                class R: returncode=0; stdout='ok'
                return R()
            with patch.object(app,'pinned_code',return_value=b'hashed fixture'),patch.object(app.subprocess,'run',side_effect=fake_run):
                info=app.run(archive=archive,home=root,bundle=root,output=result_dir)
            self.assertTrue(info['strict_lineage_verified'])
            self.assertNotIn('C:/secret',(result_dir/'share_only_this_summary.json').read_text())
            self.assertTrue(archive.exists())

    def test_runner_fail_closed_when_scanner_rejects_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'already_here.tar.gz';archive.write_bytes(b'fixture')
            def fake_run(cmd,**kwargs):
                p=Path(cmd[cmd.index('--out')+1]);p.mkdir(parents=True)
                (p/'source_run_probe_report.json').write_text(json.dumps({
                  'strict_lineage_verified':False,'issues':['original_archive_md5_mismatch']}))
                class R: returncode=2;stdout='fake'
                return R()
            with patch.object(app,'pinned_code',return_value=b'hashed fixture'),patch.object(app.subprocess,'run',side_effect=fake_run):
                with self.assertRaises(SystemExit) as caught:
                    app.run(archive=archive,home=root,bundle=root,output=root/'evidence')
            self.assertEqual(caught.exception.code,2)

if __name__=='__main__':unittest.main()