import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import core
import resilience

class ResilienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.c=core.connect(Path(self.tmp.name)/'test.sqlite3')
    def tearDown(self):
        self.c.close();self.tmp.cleanup()
    def test_invalid_task(self):
        with self.assertRaises(ValueError):resilience.repair(self.c,'arbitrary')
    def test_bounded_attempts(self):
        with self.assertRaises(ValueError):resilience.repair(self.c,'sift_synthetic',4)
    def test_manifest_block(self):
        with patch.object(resilience,'diagnose',return_value={'manifest_ok':False,'health':{'healthy':True}}):
            self.assertEqual(resilience.repair(self.c,'sift_synthetic')['state'],'blocked')
    def test_running_task_block(self):
        core.claim(self.c,'sift_synthetic')
        with patch.object(resilience,'diagnose',return_value={'manifest_ok':True,'health':{'healthy':True}}):
            self.assertEqual(resilience.repair(self.c,'sift_synthetic')['state'],'blocked')
    def test_no_retry_for_non_transient(self):
        with patch.object(resilience,'diagnose',return_value={'manifest_ok':True,'health':{'healthy':True}}):
            with patch.object(core,'run',return_value={'status':'failed','run_id':'a','detail':'invalid output'}) as runner:
                r=resilience.repair(self.c,'sift_synthetic')
                self.assertEqual(r['attempts'],1);runner.assert_called_once()
    def test_retry_timeout_then_success(self):
        outputs=[{'status':'failed','run_id':'a','detail':'TimeoutExpired'},{'status':'completed','run_id':'b','detail':''}]
        with patch.object(resilience,'diagnose',return_value={'manifest_ok':True,'health':{'healthy':True}}):
            with patch.object(core,'run',side_effect=outputs):
                self.assertEqual(resilience.repair(self.c,'sift_synthetic')['attempts'],2)
    def test_no_retry_for_missing_file(self):
        with patch.object(resilience,'diagnose',return_value={'manifest_ok':True,'health':{'healthy':True}}):
            with patch.object(core,'run',return_value={'status':'failed','run_id':'a','detail':'FileNotFoundError'}) as runner:
                self.assertEqual(resilience.repair(self.c,'sift_synthetic')['state'],'failed');runner.assert_called_once()

if __name__=='__main__':unittest.main()