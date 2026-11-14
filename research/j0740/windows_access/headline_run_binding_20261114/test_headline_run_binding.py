import hashlib
import tempfile
import unittest
from pathlib import Path
from headline_run_binding import (
    EXPECTED_SOURCE_MEMBERS, PINS, README_MD5, SourceMismatch,
    verify_published_binding,
)

class OfficialLineageTests(unittest.TestCase):
    def fixture(self, root, *, tamper=None):
        paths={}
        pins={}
        for k in PINS:
            p=Path(root)/(k+'.txt')
            p.write_text('X-PSI version: v1.2.0\n' if k=='out_log' else 'test '+k,encoding='utf-8')
            paths[k]=p
            pins[k]=hashlib.sha256(p.read_bytes()).hexdigest()
        poster=Path(root)/'published_posterior.tar.gz'
        poster.write_bytes(b'test archive')
        return paths, pins, poster

    def call(self, paths, pins, poster, **kwargs):
        return verify_published_binding(
            paths, EXPECTED_SOURCE_MEMBERS, readme_md5=README_MD5,
            source_posterior_archive_path=poster,
            stats_logz=-21889.986812013929, out_logz=-21889.9868120139,
            stats_error=.0244091345940078905, out_error=.02440913459400789,
            expected_file_hashes=pins,**kwargs)

    def test_official_stu_headline_mapping_allows_gamma_vs_yesmm_nomm_names(self):
        with tempfile.TemporaryDirectory() as d:
            paths,pins,poster=self.fixture(d)
            # Replaced in the test by a miniature fixture hash for the source archive.
            # A real production call MUST still verify the official MD5.
            from unittest.mock import patch
            with patch('headline_run_binding.POSTERIOR_ARCHIVE_MD5',hashlib.md5(poster.read_bytes()).hexdigest()):
                x=self.call(paths,pins,poster)
            self.assertEqual(x['run_link'],'PUBLISHER_README_MAPS_GAMMA_NXX_MR_TO_STU_HEADLINE_DIR')
            self.assertEqual(x['status'],'SYNTHETIC_TEST_FIXTURE_ONLY')
            self.assertEqual(x['source_version_from_out_log'],'v1.2.0')
            self.assertFalse(x['sample_to_actual_historical_runner_execution_attested'])
            self.assertEqual(x['EOS_Bayes'],'NOT_RUN')

    def test_tampered_prior_bytes_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            paths,pins,poster=self.fixture(d)
            paths['prior'].write_text('tampered',encoding='utf-8')
            with self.assertRaisesRegex(SourceMismatch,'source byte hash mismatch: prior'):
                from unittest.mock import patch
                with patch('headline_run_binding.POSTERIOR_ARCHIVE_MD5',hashlib.md5(poster.read_bytes()).hexdigest()):
                    self.call(paths,pins,poster)

    def test_wrong_posterior_archive_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            paths,pins,poster=self.fixture(d)
            with self.assertRaisesRegex(SourceMismatch,'posterior archive MD5 mismatch'):
                self.call(paths,pins,poster)

    def test_mismatched_evidence_value_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            paths,pins,poster=self.fixture(d)
            from unittest.mock import patch
            with patch('headline_run_binding.POSTERIOR_ARCHIVE_MD5',hashlib.md5(poster.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(SourceMismatch,'evidence numbers disagree'):
                    verify_published_binding(paths, EXPECTED_SOURCE_MEMBERS,
                        readme_md5=README_MD5,source_posterior_archive_path=poster,
                        stats_logz=-21889.98,out_logz=-21889.9868,stats_error=.0244,
                        out_error=.0244,expected_file_hashes=pins)

    def test_unexpected_directory_member_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            paths,pins,poster=self.fixture(d)
            from unittest.mock import patch
            members=dict(EXPECTED_SOURCE_MEMBERS)
            members['out_log']='unrelated/run/out_'
            with patch('headline_run_binding.POSTERIOR_ARCHIVE_MD5',hashlib.md5(poster.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(SourceMismatch,'unexpected publisher archive member'):
                    verify_published_binding(paths,members,readme_md5=README_MD5,
                      source_posterior_archive_path=poster,stats_logz=-21889.986812013929,
                      out_logz=-21889.9868120139,stats_error=.0244091345940078905,
                      out_error=.02440913459400789,expected_file_hashes=pins)

    def test_out_of_scope_xpsi_version_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            paths,pins,poster=self.fixture(d)
            paths['out_log'].write_text('X-PSI version: v3.0.0\n',encoding='utf-8')
            pins['out_log']=hashlib.sha256(paths['out_log'].read_bytes()).hexdigest()
            from unittest.mock import patch
            with patch('headline_run_binding.POSTERIOR_ARCHIVE_MD5',hashlib.md5(poster.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(SourceMismatch,'outside publisher'):
                    self.call(paths,pins,poster)

    def test_bad_readme_identity_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            paths,pins,poster=self.fixture(d)
            with self.assertRaisesRegex(SourceMismatch,'README identity'):
                verify_published_binding(paths,EXPECTED_SOURCE_MEMBERS,readme_md5='bad',
                  source_posterior_archive_path=poster,stats_logz=0,out_logz=0,
                  stats_error=0,out_error=0,expected_file_hashes=pins)

if __name__=='__main__':unittest.main()