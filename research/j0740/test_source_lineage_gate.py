import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from source_lineage_gate import (
    RunLineageNotProven, inspect_legacy_pair, require_proven_lineage,
    verify_matched_run_manifest, SOURCE_POSTERIOR_RUN, SOURCE_POSTERIOR_MEMBER,
    SOURCE_POSTERIOR_SHA256, SOURCE_FULL_ARCHIVE_MD5, SOURCE_POSTERIOR_ARCHIVE_MD5,
)


class RunLineageGateTests(unittest.TestCase):
    def test_primary_zenodo_readme_links_gamma_to_stu_headline(self):
        from source_lineage_gate import documented_headline_mapping
        m= documented_headline_mapping()
        self.assertEqual(m["run_mapping"], "PUBLISHED_README_HEADLINE_RUN_DIRECTORY_CONFIRMED")
        self.assertTrue(m["runner_member"].endswith("main_lp40k_Xse001_Dfix.py"))
        self.assertTrue(m["output_directory"].endswith("run1_lp40k_Xse001_Dfix/"))
        self.assertFalse(m["exact_original_prior_bytes_verified"])


    def test_default_blocks_unverified_gamma_vs_stu(self):
        with self.assertRaisesRegex(RunLineageNotProven, "not yet verified"):
            require_proven_lineage()

    def test_historical_proxy_explicitly_nonfinal(self):
        x = require_proven_lineage(historical_proxy_only=True)
        self.assertEqual(x["status"], "UNVERIFIED_HISTORICAL_PROXY_ONLY")
        self.assertNotIn("BAYES_EVIDENCE_VALIDATED", x["status"])

    def test_original_posterior_metadata_does_not_prove_prior_identity(self):
        x = inspect_legacy_pair({"source_file": Path(SOURCE_POSTERIOR_MEMBER).name,
                                 "settings": "lp40k_se001", "source_archive_md5": SOURCE_POSTERIOR_ARCHIVE_MD5})
        self.assertFalse(x["posterior_prior_exact_run_link_proven"])
        self.assertTrue(x["posterior_prior_same_run_directory_documented"])
        self.assertFalse(x["posterior_prior_exact_original_file_bytes_verified"])
        self.assertEqual(len(x["needed_evidence"]), 3)

    def test_posterior_mismatch_rejected(self):
        with self.assertRaisesRegex(RunLineageNotProven, "Unexpected"):
            inspect_legacy_pair({"source_file": "STU_post_equal_weights.dat"})

    def make(self, td, *, run_in_config=True, tag="v1.2.1"):
        p = Path(td)
        files = {}
        for key, content in {
            "matching_prior": "class CustomPrior: pass\n",
            "matching_runner": "from CustomPrior import CustomPrior\n",
            "matching_sampler_config": "run=" + (SOURCE_POSTERIOR_RUN if run_in_config else "STU_NICER_XMM_hr") + "\n",
            "matching_run_log": "X-PSI version: " + tag + "\n",
        }.items():
            f = p / ("out_headline_test.txt" if key == "matching_run_log" else key + ".py")
            f.write_text(content, encoding="utf-8")
            archive_member = ("STU/STU_NICER_XMM_hr/STU_outputs/run1_lp40k_Xse001_Dfix/out_headline_test.txt"
                              if key == "matching_run_log" else "STU/" + f.name)
            files[key] = {"local_path": str(f), "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                          "original_archive_member": archive_member}
        m = {"provenance_schema": "j0740-gamma-nxx-run-match-v1",
             "posterior_subset_sha256": SOURCE_POSTERIOR_SHA256,
             "posterior_source_member": SOURCE_POSTERIOR_MEMBER,
             "posterior_run": SOURCE_POSTERIOR_RUN,
             "full_archive_md5": SOURCE_FULL_ARCHIVE_MD5,
             "source_archive_md5": SOURCE_POSTERIOR_ARCHIVE_MD5,
             "xpsi_version": tag,
             "verified_run_identity": "exact_gamma_NxX_lp40k_se001_source_and_prior",
             "binding_proof": "source_sampler_configuration_names_exact_posterior_run", **files}
        path = p / "manifest.json"
        path.write_text(json.dumps(m), encoding="utf-8")
        return path, files

    def test_explicit_source_run_manifest_requires_real_sha(self):
        with tempfile.TemporaryDirectory() as td:
            path, files = self.make(td)
            result=verify_matched_run_manifest(path)
            self.assertEqual(result["status"], "BYTE_IDENTITIES_AND_EXPLICIT_CONFIG_RUN_LABEL_VERIFIED")
            self.assertEqual(result["xpsi_version_from_verified_out_log"], "v1.2.1")
            Path(files["matching_prior"]["local_path"]).write_text("modified", encoding="utf-8")
            with self.assertRaisesRegex(RunLineageNotProven, "byte hash fails"):
                verify_matched_run_manifest(path)

    def test_unmatched_sampler_config_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            path, _ = self.make(td, run_in_config=False)
            with self.assertRaisesRegex(RunLineageNotProven, "does not name"):
                verify_matched_run_manifest(path)

    def test_unverified_xpsi_version_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            path, _ = self.make(td, tag="v0.7.5")
            with self.assertRaisesRegex(RunLineageNotProven, "outside official"):
                verify_matched_run_manifest(path)


    def test_version_v120_is_valid_if_original_out_log_proves_it(self):
        with tempfile.TemporaryDirectory() as td:
            path, _ = self.make(td, tag="v1.2.0")
            self.assertEqual(
                verify_matched_run_manifest(path)["xpsi_version_from_verified_out_log"],
                "v1.2.0",
            )

    def test_version_manifest_cannot_override_verified_log(self):
        with tempfile.TemporaryDirectory() as td:
            path, _ = self.make(td, tag="v1.2.0")
            m = json.loads(path.read_text())
            m["xpsi_version"] = "v1.2.1"
            path.write_text(json.dumps(m))
            with self.assertRaisesRegex(RunLineageNotProven, "does not match"):
                verify_matched_run_manifest(path)

    def test_absent_original_out_log_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path, _ = self.make(td)
            m = json.loads(path.read_text())
            del m["matching_run_log"]
            path.write_text(json.dumps(m))
            with self.assertRaisesRegex(RunLineageNotProven, "Missing exact source entry"):
                verify_matched_run_manifest(path)

    def test_out_log_wrong_run_directory_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path, _ = self.make(td)
            m = json.loads(path.read_text())
            m["matching_run_log"]["original_archive_member"] = "unrelated/out_other.txt"
            path.write_text(json.dumps(m))
            with self.assertRaisesRegex(RunLineageNotProven, "original headline ST-U"):
                verify_matched_run_manifest(path)

if __name__ == "__main__":
    unittest.main()
