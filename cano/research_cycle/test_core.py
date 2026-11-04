import pathlib
import tempfile
import unittest
from unittest.mock import patch
import core

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=pathlib.Path(self.tmp.name)/'test.sqlite3'
        self.c=core.connect(self.db)
    def tearDown(self):
        self.c.close();self.tmp.cleanup()
    def test_dedup(self):
        core.add(self.c,'sift_synthetic');core.add(self.c,'sift_synthetic')
        self.assertEqual(len(core.report(self.c)['tasks']),1)
    def test_disallowed(self):
        with self.assertRaises(ValueError):core.add(self.c,'shell_anything')
    def test_persistence(self):
        core.add(self.c,'sift_robustness')
        self.c.close();self.c=core.connect(self.db)
        self.assertEqual(core.report(self.c)['counts']['pending'],1)
    def test_real_sift(self):
        self.assertEqual(core.run(self.c,'sift_synthetic')['status'],'completed')
    def test_real_robustness(self):
        self.assertEqual(core.run(self.c,'sift_robustness')['status'],'completed')
    def test_exit_zero_without_valid_evidence_fails(self):
        from subprocess import CompletedProcess
        with patch.object(core.subprocess,'run',return_value=CompletedProcess([],0,'{}','')):
            self.assertEqual(core.run(self.c,'sift_synthetic')['status'],'failed')
    def test_nonzero_fails(self):
        from subprocess import CompletedProcess
        with patch.object(core.subprocess,'run',return_value=CompletedProcess([],2,'','bad')):
            self.assertEqual(core.run(self.c,'sift_synthetic')['status'],'failed')
    def test_timeout_fails(self):
        import subprocess
        with patch.object(core.subprocess,'run',side_effect=subprocess.TimeoutExpired('test',1)):
            self.assertEqual(core.run(self.c,'sift_synthetic')['status'],'failed')
    def test_concurrent_claim_blocked(self):
        core.claim(self.c,'sift_synthetic')
        other=core.connect(self.db)
        try:
            with self.assertRaises(RuntimeError):core.claim(other,'sift_synthetic')
        finally:
            other.close()
    def test_manual_recovery(self):
        core.claim(self.c,'sift_synthetic')
        self.assertTrue(core.recover(self.c,'sift_synthetic')['recovered'])
        self.assertEqual(core.report(self.c)['counts']['interrupted'],1)
    def test_event_audit(self):
        core.run(self.c,'sift_synthetic')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM events').fetchone()[0],2)
    def test_health(self):
        self.assertTrue(core.health(self.c)['healthy'])
    def test_nan_evidence_rejected(self):
        import json
        x={'mode':'synthetic','ratio_matches':10,'ransac_inliers':8,'median_ground_truth_error_px':float('nan')}
        self.assertFalse(core.verify('sift_synthetic',json.dumps(x)))
    def test_inconsistent_evidence_rejected(self):
        import json
        x={'mode':'synthetic','ratio_matches':4,'ransac_inliers':50,'median_ground_truth_error_px':0.1}
        self.assertFalse(core.verify('sift_synthetic',json.dumps(x)))
    def test_missing_dependency_flag(self):
        from unittest.mock import patch
        with patch.object(core.hashlib,'sha256',wraps=core.hashlib.sha256):
            self.assertIn('scripts',core.health(self.c))
    def test_timeout_bounds(self):
        with self.assertRaises(ValueError):core.run(self.c,'sift_synthetic',timeout=0)

    def test_manifest_roundtrip(self):
        self.assertTrue(core.verify_manifest(core.file_manifest()))
    def test_manifest_tamper_rejected(self):
        m=core.file_manifest();m['files'][0]['sha256']='0'*64
        self.assertFalse(core.verify_manifest(m))
    def test_audit_real_run(self):
        core.run(self.c,'sift_synthetic')
        self.assertTrue(core.evidence_audit(self.c)['passed'])
    def test_audit_fake_completion_rejected(self):
        core.add(self.c,'sift_synthetic')
        self.c.execute("UPDATE tasks SET status='completed',output='{}' WHERE name='sift_synthetic'");self.c.commit()
        self.assertFalse(core.evidence_audit(self.c)['passed'])
    def test_manifest_missing_script_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(core.verify_manifest(core.file_manifest(),pathlib.Path(d)))

if __name__=='__main__':unittest.main()