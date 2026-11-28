import json
import tempfile
import unittest
from pathlib import Path

from summarize_mesh_root_artifact import summarize


def model(status="MATCHED_FIXED_MASS_RNS_GR_AND_STATIC_TOV_VALIDATED", radius=12.0,
          spin=346.5, reason=None):
    row = {"status": status}
    if reason:
        row["reason"] = reason
    if status.startswith("MATCHED"):
        row.update({
            "rns_rotating_at_target": {"mass_msun": 2.073, "radius_eq_km": radius,
                "central_energy_density_g_cm3": 1e15, "spin_hz_reported": spin},
            "rns_static_at_same_gravitational_mass": {"mass_msun": 2.073,
                "radius_eq_km": radius-0.1, "central_energy_density_g_cm3": 1e15},
            "rns_minus_jester_static_tov_km": 0.01,
            "scan": {"rotating_models": [{"mass_msun": 2.0}],
                "rotating_failures": [{"reason": "retained"}],
                "nonrotating_models": [], "nonrotating_failures": []},
        })
    return row


class SummarizeMeshArtifactTests(unittest.TestCase):
    def test_partial_fine_run_and_failure_are_preserved_with_root_deltas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for grid in ("151x301","201x401"):
                directory=root/grid
                directory.mkdir()
                rows={name:model(radius=12.0 if grid=="151x301" else 12.04,
                                 spin=346.5 if grid=="151x301" else 346.52)
                      for name in ("APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2")}
                if grid=="201x401":
                    rows["WFF1"]=model("NO_VALIDATED_STABLE_CROSSING",reason="target not bracketed")
                    rows["WFF1"]["scan"]={
                        "rotating_models":[
                            {"central_energy_density_g_cm3":1e15,"mass_msun":2.00},
                            {"central_energy_density_g_cm3":1.1e15,"mass_msun":2.06},
                            {"central_energy_density_g_cm3":1.2e15,"mass_msun":2.04}],
                        "rotating_failures":[{"reason":"preserved failure"}],
                        "nonrotating_models":[
                            {"central_energy_density_g_cm3":1e15,"mass_msun":2.00},
                            {"central_energy_density_g_cm3":1.1e15,"mass_msun":2.10}],
                        "nonrotating_failures":[]}
                report={"status":"ALL_SEVEN_VALIDATED" if grid=="151x301" else "PARTIAL_NOT_FINAL",
                        "validated_eos_count":7 if grid=="151x301" else 6,"eos":rows}
                (directory/"J0740_fixed_mass_spin.json").write_text(json.dumps(report))
            result=summarize(root)
            self.assertEqual(result["models"]["WFF1"]["fine_status"],"NO_VALIDATED_STABLE_CROSSING")
            self.assertEqual(result["models"]["WFF1"]["fine_reason"],"target not bracketed")
            scan=result["models"]["WFF1"]["fine_scan"]
            self.assertEqual(scan["rotating_target_support"]["stable_target_bracket_count"],0)
            self.assertEqual(scan["rotating_target_support"]["nearest_above_target_mass_msun"],None)
            self.assertEqual(scan["rotating_target_support"]["failed_points"],1)
            self.assertEqual(scan["static_target_support"]["stable_target_bracket_count"],1)
            self.assertAlmostEqual(result["models"]["MS1"]["delta_rotating_radius_eq_km"],0.04)
            self.assertEqual(result["EOS_Bayes"],"NOT_RUN")


if __name__ == "__main__":
    unittest.main()

