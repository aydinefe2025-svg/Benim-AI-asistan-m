"""End-to-end contract: no CSV screen can authorize physical cell identity."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"/"battery_curve_audit"))
import battery_purpose_contract as contract
import customer_pipeline
import integrated_customer_gate


class PurposeContractTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        entries = []
        for cell, level in zip("ABCD",(4.2, 3.9, 3.6, 3.3)):
            name = cell+".csv"
            data = "Timestamp_1 [h],DC1 [V]\n" + "\n".join(
                f"{i},{level-0.002*i:.6f}" for i in range(120)
            ) + "\n"
            (self.root/name).write_text(data,encoding="utf-8")
            entries.append({"path":name,"cell":cell,"mode":"dchg"})
        self.manifest = {"schema":"cano.battery.customer-files.v1","files":entries}
        self.manifest_path = self.root/"manifest.json"
        self.manifest_path.write_text(json.dumps(self.manifest),encoding="utf-8")

    def test_pure_scope_bans_product_claims_even_on_clean_data(self):
        for decision in ("PASS_SCREEN_ONLY","SCREEN_ONLY_NO_CROSS_CELL_CANDIDATES"):
            s = contract.scope(decision)
            self.assertTrue(s["data_integrity_screen_clear"])
            self.assertEqual(s["permitted_use"], contract.SCREEN)
            for k in ("physical_cell_identity_independently_verified",
                      "real_field_fpr_fnr_established","battery_health_certified",
                      "physical_identity_or_field_release_allowed"):
                self.assertIs(s[k],False)
        self.assertFalse(contract.scope("REVIEW_REQUIRED")["data_integrity_screen_clear"])
        self.assertFalse(contract.scope("BLOCK_INSUFFICIENT_GROUPS")["data_integrity_screen_clear"])

    def test_explicit_physical_claims_are_rejected(self):
        contract.require_purpose(contract.SCREEN)
        for intent in ("physical-cell-identity","field-acceptance",
                       "certified-battery-health","unknown","DATA-INTEGRITY-SCREEN",None):
            with self.subTest(intent=intent),self.assertRaisesRegex(ValueError,"PURPOSE_REVIEW_REQUIRED"):
                contract.require_purpose(intent)

    def test_missing_or_string_boolean_scope_rejected(self):
        report={"decision":"PASS_SCREEN_ONLY","use_scope":contract.scope("PASS_SCREEN_ONLY")}
        self.assertTrue(contract.verify_scope(report))
        report["use_scope"]["physical_identity_or_field_release_allowed"]="false"
        with self.assertRaisesRegex(ValueError,"PURPOSE_REVIEW_REQUIRED"):
            contract.verify_scope(report)
        report["use_scope"]=contract.scope("PASS_SCREEN_ONLY")
        report["use_scope"]["physical_identity_or_field_release_allowed"]=0
        with self.assertRaisesRegex(ValueError,"PURPOSE_REVIEW_REQUIRED"):
            contract.verify_scope(report)
        report["use_scope"]=contract.scope("PASS_SCREEN_ONLY")
        report["use_scope"]["data_integrity_screen_clear"]=1
        with self.assertRaisesRegex(ValueError,"PURPOSE_REVIEW_REQUIRED"):
            contract.verify_scope(report)
        report["use_scope"]=None
        with self.assertRaisesRegex(ValueError,"PURPOSE_REVIEW_REQUIRED"):
            contract.verify_scope(report)

    def test_real_customer_pipeline_summary_and_private_holdout_never_certified(self):
        summary, private = customer_pipeline.audit_offline(self.manifest,self.root)
        self.assertEqual(summary["decision"],"SCREEN_ONLY_NO_CROSS_CELL_CANDIDATES")
        self.assertTrue(contract.verify_scope(summary))
        self.assertTrue(contract.verify_scope(private | {"decision":summary["decision"]}))
        self.assertIs(summary["use_scope"]["physical_identity_or_field_release_allowed"],False)
        self.assertEqual(private["status"],"NOT_CERTIFIED")
        self.assertNotIn("A.csv",json.dumps(summary))

    def test_integrated_screen_and_report_replay_reject_modified_scope(self):
        report=integrated_customer_gate.integrated_check(self.manifest,self.root)
        self.assertEqual(report["decision"],"PASS_SCREEN_ONLY")
        self.assertTrue(contract.verify_scope(report))
        self.assertTrue(integrated_customer_gate.verify_report(self.manifest,self.root,report))
        modified=json.loads(json.dumps(report))
        modified["use_scope"]["physical_cell_identity_independently_verified"]=True
        with self.assertRaisesRegex(ValueError,"PURPOSE_REVIEW_REQUIRED"):
            integrated_customer_gate.verify_report(self.manifest,self.root,modified)

    def test_clean_split_cli_is_explicitly_limited_to_data_screen(self):
        output=self.root/"checked.json"
        split=self.root/"proposed.json"
        rc=integrated_customer_gate.main([
            "--manifest",str(self.manifest_path),"--root",str(self.root),
            "--report",str(output),"--accepted-split",str(split),
            "--intended-use",contract.SCREEN,
        ])
        self.assertEqual(rc,0)
        self.assertTrue(contract.verify_scope(json.loads(output.read_text())))
        proposed=json.loads(split.read_text())
        self.assertEqual(proposed["use_scope"]["permitted_use"],contract.SCREEN)
        self.assertIs(proposed["use_scope"]["physical_identity_or_field_release_allowed"],False)

    def test_both_clis_refuse_physical_use_without_writing_any_outputs(self):
        for use in ("physical-cell-identity","field-acceptance","certified-battery-health"):
            for command in ("customer","integrated"):
                with self.subTest(use=use,command=command):
                    suffix=use+"-"+command
                    summary=self.root/(suffix+"-summary.json")
                    split=self.root/(suffix+"-split.json")
                    if command=="customer":
                        rc=customer_pipeline.main([
                            "--manifest",str(self.manifest_path),"--root",str(self.root),
                            "--summary",str(summary),"--private-split",str(split),
                            "--intended-use",use,
                        ])
                    else:
                        rc=integrated_customer_gate.main([
                            "--manifest",str(self.manifest_path),"--root",str(self.root),
                            "--report",str(summary),"--accepted-split",str(split),
                            "--intended-use",use,
                        ])
                    self.assertEqual(rc,2)
                    self.assertFalse(summary.exists())
                    self.assertFalse(split.exists())
        self.assertTrue(self.manifest_path.exists())
        self.assertEqual(len(list(self.root.glob("*.csv"))),4)

    def test_customer_report_only_cannot_bypass_purpose_block(self):
        out=self.root/"bad.json"
        rc=customer_pipeline.main([
            "--manifest",str(self.manifest_path),"--root",str(self.root),
            "--summary",str(out),"--report-only",
            "--intended-use","physical-cell-identity",
        ])
        self.assertEqual(rc,2)
        self.assertFalse(out.exists())


if __name__=="__main__":
    unittest.main()
