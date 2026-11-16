"""Synthetic regression tests; NEVER evidence for real Salmi source file bytes."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from published_source_lineage import (
    EXPECTED, README_MD5, POSTERIOR_MEMBER, POSTERIOR_SUBSET_SHA256,
    POSTERIOR_ARCHIVE_MD5, FULL_ARCHIVE_MD5, KNOWN_LOGZ,
    KNOWN_LOGZ_ERROR, PROOF_LABEL, SourceBindingError,
    verify_published_headline_manifest, _xpsi_version_from_log,
)

class LineageTests(unittest.TestCase):
    def test_original_boxed_out_log_banner(self):
        banner = ('/=============================================\\\n'
                  '| X-PSI: X-ray Pulse Simulation and Inference |\n'
                  '|---------------------------------------------|\n'
                  '|                Version: 1.2.0               |\n')
        self.assertEqual(_xpsi_version_from_log(banner), 'v1.2.0')

    def test_conflicting_or_unrelated_versions_fail_closed(self):
        for text in (
            'X-PSI started\n' + 'unrelated\n' * 20 + 'Version: 1.2.0',
            'X-PSI version: 1.2.0\nX-PSI version: 1.2.1',
        ):
            with self.assertRaisesRegex(SourceBindingError, 'unambiguous'):
                _xpsi_version_from_log(text)

    def fixture(self, root):
        m = {
            'schema': 'j0740-publisher-headline-v2',
            'binding_proof': PROOF_LABEL,
            'published_readme_md5': README_MD5,
            'posterior_member': POSTERIOR_MEMBER,
            'posterior_subset_sha256': POSTERIOR_SUBSET_SHA256,
            'posterior_archive_md5': POSTERIOR_ARCHIVE_MD5,
            'full_archive_md5': FULL_ARCHIVE_MD5,
            'xpsi_version': 'v1.2.0',
            'reported_evidence': {
                k: {'logz': KNOWN_LOGZ, 'error': KNOWN_LOGZ_ERROR}
                for k in ('stats', 'out')
            },
            'artifacts': {},
        }
        pins = {}
        for role, (member, _) in EXPECTED.items():
            p = Path(root) / (role + '.txt')
            p.write_text('X-PSI version v1.2.0\n' if role == 'out_log' else 'synthetic '+role, encoding='utf-8')
            pins[role] = hashlib.sha256(p.read_bytes()).hexdigest()
            m['artifacts'][role] = {'original_archive_member': member,
                                    'local_path': p.name, 'sha256': pins[role]}
        manifest = Path(root) / 'manifest.json'
        manifest.write_text(json.dumps(m), encoding='utf-8')
        return manifest, m, pins

    def test_documented_cross_prefix_mapping_not_literal_gamma_in_config(self):
        with tempfile.TemporaryDirectory() as d:
            p, _, pins = self.fixture(d)
            r = verify_published_headline_manifest(p, expected_hashes=pins, allow_synthetic_test=True)
            self.assertEqual(r['status'], 'SYNTHETIC_TEST_ONLY')
            self.assertFalse(r['native_photon_likelihood_recomputed'])
            self.assertEqual(r['EOS_Bayes'], 'NOT_RUN')

    def test_no_fixture_override_for_production(self):
        with tempfile.TemporaryDirectory() as d:
            p, _, pins = self.fixture(d)
            with self.assertRaisesRegex(SourceBindingError, 'test pins'):
                verify_published_headline_manifest(p, expected_hashes=pins)
            with self.assertRaisesRegex(SourceBindingError, 'pinned original'):
                verify_published_headline_manifest(p)

    def test_wrong_archive_member_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p, m, pins = self.fixture(d)
            m['artifacts']['prior']['original_archive_member'] = 'STU/other/prior.py'
            p.write_text(json.dumps(m), encoding='utf-8')
            with self.assertRaisesRegex(SourceBindingError, 'wrong published archive member'):
                verify_published_headline_manifest(p, expected_hashes=pins, allow_synthetic_test=True)

    def test_tampered_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p, _, pins = self.fixture(d)
            (Path(d) / 'prior.txt').write_text('evil', encoding='utf-8')
            with self.assertRaisesRegex(SourceBindingError, 'original byte identity fails'):
                verify_published_headline_manifest(p, expected_hashes=pins, allow_synthetic_test=True)

    def test_wrong_xpsi_version_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p, m, pins = self.fixture(d)
            m['xpsi_version'] = 'v1.2.1'
            p.write_text(json.dumps(m), encoding='utf-8')
            with self.assertRaisesRegex(SourceBindingError, 'manifest version differs'):
                verify_published_headline_manifest(p, expected_hashes=pins, allow_synthetic_test=True)

    def test_fabricated_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p, m, pins = self.fixture(d)
            m['reported_evidence']['stats']['logz'] = -42
            p.write_text(json.dumps(m), encoding='utf-8')
            with self.assertRaisesRegex(SourceBindingError, 'published logz mismatch'):
                verify_published_headline_manifest(p, expected_hashes=pins, allow_synthetic_test=True)

    def test_missing_stats_or_log_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p, m, pins = self.fixture(d)
            del m['artifacts']['stats']
            p.write_text(json.dumps(m), encoding='utf-8')
            with self.assertRaisesRegex(SourceBindingError, 'missing/extra'):
                verify_published_headline_manifest(p, expected_hashes=pins, allow_synthetic_test=True)

if __name__ == '__main__':
    unittest.main()

