"""No existing customer file may be overwritten or deleted by acceptance gate."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
TOOL = BASE / 'research' / 'battery_curve_audit' / 'integrated_customer_gate.py'
sys.path.insert(0, str(TOOL.parent))
import integrated_customer_gate as gate


class IntegratedOutputSafetyTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)
        (self.root/'A.csv').write_text('Timestamp_1 [h],DC1 [V]\n0,3.4\n1,3.3\n', encoding='utf-8')
        self.manifest = self.root/'manifest.json'
        self.manifest.write_text(json.dumps({'schema':'cano.battery.customer-files.v1',
            'files':[{'cell':'A','mode':'dchg','path':'A.csv'}]}), encoding='utf-8')

    def test_rejected_input_must_not_delete_arbitrary_existing_accepted_file(self):
        existing = self.root/'NOT_OURS_custom_client_file.json'
        existing.write_text('DO NOT DELETE', encoding='utf-8')
        report = self.root/'report.json'
        r = subprocess.run([sys.executable,str(TOOL), '--manifest',str(self.manifest),
              '--root',str(self.root),'--report',str(report),'--accepted-split',str(existing)],
              capture_output=True,text=True)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(existing.read_text(encoding='utf-8'), 'DO NOT DELETE')
        self.assertFalse(report.exists())

    def test_never_overwrite_preexisting_report_even_with_valid_payload(self):
        existing = self.root/'important_archive.json'
        existing.write_text('HISTORIC CONTENT', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            gate.write_json(existing, {'decision':'PASS_SCREEN_ONLY'})
        self.assertEqual(existing.read_text(encoding='utf-8'), 'HISTORIC CONTENT')

    def test_precheck_rejects_existing_report_before_processing(self):
        existing = self.root/'report.json'
        existing.write_text('IMMUTABLE', encoding='utf-8')
        r = subprocess.run([sys.executable,str(TOOL),'--manifest',str(self.manifest),
              '--root',str(self.root),'--report',str(existing)],capture_output=True,text=True)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(existing.read_text(encoding='utf-8'), 'IMMUTABLE')


if __name__ == '__main__':
    unittest.main()
