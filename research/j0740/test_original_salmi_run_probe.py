"""Offline source provenance regression fixtures; no large public archives."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import original_salmi_run_probe as source_probe
import source_lineage_gate as lineage_gate

from original_salmi_run_probe import (
    canonical_member, classify, discover_archive, discover_directory,
    build_report, RunLineageNotProven,
)

PREFIX='J0740_GAMMA_zenodo/'
MODULES=PREFIX+'STU/STU_NICER_XMM_hr/STU_modules/'
OUTPUT=PREFIX+'STU/STU_NICER_XMM_hr/STU_outputs/run1_lp40k_Xse001_Dfix/'
RUNNER=b'from CustomPrior_GLS_compressed_scaling_Dfix import CustomPrior\nprior=CustomPrior()\n'
PRIOR=b'class CustomPrior: pass\n'
CONFIG=b'run=J0740_gamma_NxX_lp40k_se001\n'
LOG=b'config: run1_lp40k_Xse001_Dfix\nX-PSI version: v1.2.0\n'


def make_members(*, config=CONFIG, include_log=True, two_logs=False, extra=None):
    d = {
        MODULES+'main_lp40k_Xse001_Dfix.py':RUNNER,
        MODULES+'CustomPrior_GLS_compressed_scaling_Dfix.py':PRIOR,
        MODULES+'config_postprocess_J0740_gamma.ini':config,
    }
    if include_log:
        d[OUTPUT+'out_sample.txt']=LOG
    if two_logs:
        d[OUTPUT+'out_other.txt']=LOG
    if extra:
        d.update(extra)
    return d


def tar_from_dict(path, members):
    with tarfile.open(path, mode='w:gz') as tar:
        for name, data in members.items():
            info=tarfile.TarInfo(name)
            info.size=len(data)
            tar.addfile(info,io.BytesIO(data))


class OriginalRunScannerTests(unittest.TestCase):
    def test_original_archive_member_names_and_optional_prefix(self):
        self.assertEqual(canonical_member(MODULES+'main_lp40k_Xse001_Dfix.py'),
                         'STU/STU_NICER_XMM_hr/STU_modules/main_lp40k_Xse001_Dfix.py')
        self.assertEqual(classify(MODULES+'config_postprocess_J0740_gamma.ini'),
                         'matching_sampler_config')
        self.assertIsNone(classify('STU/STU_NICER_old/STU_modules/main_lp40k_Xse001_Dfix.py'))

    def test_prevent_path_traversal(self):
        for path in ('../other/file','/absolute/run','C:/windows/file',
                     'J0740_GAMMA_zenodo/../STU/fake'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                canonical_member(path)

    def test_small_original_tar_four_sources_and_strict_gate(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            tar_from_dict(p/'small.tar.gz',make_members(extra={PREFIX+'BULK_DATA.bin':b'0'*8192}))
            archive=p/'small.tar.gz'
            expected_md5=hashlib.md5(archive.read_bytes()).hexdigest()
            expected_sha256=hashlib.sha256(archive.read_bytes()).hexdigest()
            found=discover_archive(archive)
            self.assertEqual(len(found),4)
            self.assertEqual(found.observed_archive_md5, expected_md5)
            self.assertEqual(found.observed_archive_sha256, expected_sha256)
            # A synthetic fixture has a different digest from the real 12.9GB
            # source. Patch BOTH published checksum constants for the success
            # test only. Default behavior must reject unrecognized archives.
            with (patch.object(source_probe, 'SOURCE_FULL_ARCHIVE_MD5', expected_md5),
                  patch.object(lineage_gate, 'SOURCE_FULL_ARCHIVE_MD5', expected_md5)):
                report=build_report(found,p/'out',actual_archive=True,
                       expected_runner_sha256=hashlib.sha256(RUNNER).hexdigest(),
                       expected_prior_sha256=hashlib.sha256(PRIOR).hexdigest())
            self.assertEqual(report['issues'],[])
            self.assertTrue(report['compressed_archive_checksum_verified'])
            self.assertEqual(report['source_full_archive_sha256_observed_this_scan'], expected_sha256)
            self.assertTrue(report['strict_lineage_verified'])
            m=json.loads((p/'out/matched_run_manifest_candidate.json').read_text())
            self.assertEqual(m['xpsi_version'],'v1.2.0')
            self.assertEqual(m['matching_run_log']['sha256'],hashlib.sha256(LOG).hexdigest())
            self.assertNotIn('BULK_DATA.bin',repr(m))

    def test_untrusted_tar_with_identical_four_source_members_is_not_original(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            archive=p/'lookalike.tar.gz'
            tar_from_dict(archive,make_members())
            self.assertNotEqual(hashlib.md5(archive.read_bytes()).hexdigest(),
                                source_probe.SOURCE_FULL_ARCHIVE_MD5)
            report=build_report(discover_archive(archive),p/'out',actual_archive=True,
                 expected_runner_sha256=hashlib.sha256(RUNNER).hexdigest(),
                 expected_prior_sha256=hashlib.sha256(PRIOR).hexdigest())
            self.assertIn('original_archive_md5_mismatch',report['issues'])
            self.assertFalse(report['compressed_archive_checksum_verified'])
            self.assertFalse(report['strict_lineage_verified'])
            self.assertFalse((p/'out/matched_run_manifest_candidate.json').exists())

    def test_extra_bytes_after_tar_end_marker_change_archive_digest(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); archive=p/'test.tar.gz'
            tar_from_dict(archive,make_members())
            with archive.open('ab') as raw:
                raw.write(b'garbage-after-gzip-trailer-should-not-be-ignored')
            found=discover_archive(archive)
            self.assertEqual(found.observed_archive_md5,hashlib.md5(archive.read_bytes()).hexdigest())
            self.assertEqual(found.observed_archive_sha256,hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual(len(found),4)

    def test_archive_claim_without_actual_tar_scan_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            for name,data in make_members().items():
                q=p/name; q.parent.mkdir(parents=True,exist_ok=True); q.write_bytes(data)
            extracted=discover_directory(p)
            report=build_report(extracted,p/'out',actual_archive=True,
                 expected_runner_sha256=hashlib.sha256(RUNNER).hexdigest(),
                 expected_prior_sha256=hashlib.sha256(PRIOR).hexdigest())
            self.assertIn('original_archive_md5_not_computed',report['issues'])
            self.assertFalse(report['strict_lineage_verified'])

    def test_source_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            tar_from_dict(p/'small.tar.gz',make_members())
            r=build_report(discover_archive(p/'small.tar.gz'),p/'out',actual_archive=True,
                           expected_runner_sha256='0'*64,
                           expected_prior_sha256=hashlib.sha256(PRIOR).hexdigest())
            self.assertFalse(r['strict_lineage_verified'])
            self.assertIn('matching_runner:original_sha_differs_from_recovered_F30',r['issues'])
            self.assertFalse((p/'out/matched_run_manifest_candidate.json').exists())

    def test_bad_config_blocks_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            tar_from_dict(p/'small.tar.gz',make_members(config=b'other run\n'))
            r=build_report(discover_archive(p/'small.tar.gz'),p/'out',actual_archive=True,
                           expected_runner_sha256=hashlib.sha256(RUNNER).hexdigest(),
                           expected_prior_sha256=hashlib.sha256(PRIOR).hexdigest())
            self.assertIn('sampler_config_exact_posterior_label_absent',r['issues'])
            self.assertFalse(r['strict_lineage_verified'])

    def test_missing_log_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            tar_from_dict(p/'small.tar.gz',make_members(include_log=False))
            r=build_report(discover_archive(p/'small.tar.gz'),p/'out',actual_archive=True)
            self.assertIn('matching_run_log:missing',r['issues'])
            self.assertFalse(r['strict_lineage_verified'])

    def test_ambiguous_out_log_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            tar_from_dict(p/'small.tar.gz',make_members(two_logs=True))
            with self.assertRaisesRegex(RunLineageNotProven,'Ambiguous duplicate matching_run_log'):
                discover_archive(p/'small.tar.gz')
            found=discover_archive(p/'small.tar.gz',log_name='out_sample.txt')
            self.assertEqual(len(found),4)

    def test_extracted_directory_is_diagnostic_only(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            for name,data in make_members().items():
                q=p/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(data)
            r=build_report(discover_directory(p),p/'out',actual_archive=False)
            self.assertIn('extracted_directory_not_cryptographically_attached_to_original_tar',r['issues'])
            self.assertFalse(r['strict_lineage_verified'])
            self.assertFalse((p/'out/matched_run_manifest_candidate.json').exists())


if __name__ == '__main__':unittest.main()
