import unittest

from compare_fixed_mass_spin_meshes import compare


def report(grid, offset=0.0):
    names = ("APR4_EPP", "ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2")
    eos = {}
    for name in names:
        eos[name] = {
            "status": "MATCHED_FIXED_MASS_RNS_GR_AND_STATIC_TOV_VALIDATED",
            "source_npz_sha256": name+"-source",
            "rns_rotating_at_target": {
                "mass_msun": 2.073,
                "radius_eq_km": 12.0+offset,
                "central_energy_density_g_cm3": 1e15,
                "spin_hz_reported": 346.536369+offset,
                "raw_stdout_tail": f"MDIVxSDIV={grid}",
            },
            "rns_static_at_same_gravitational_mass": {
                "mass_msun": 2.073,
                "radius_eq_km": 11.9+offset,
                "central_energy_density_g_cm3": 1e15,
                "raw_stdout_tail": f"MDIVxSDIV={grid}",
            },
        }
    return {"status":"ALL_SEVEN_VALIDATED", "validated_eos_count":7,
            "required_eos_count":7, "rns_upstream_commit":"rns-pin",
            "jester_upstream_commit":"jester-pin", "spin_hz":346.536369,
            "rotating_spin_numerical_residual_limit_hz":0.25,
            "target_gravitational_mass_msun":2.073, "eos":eos}


class FixedMassSpinMeshConvergenceTests(unittest.TestCase):
    def setUp(self):
        self.base=report("151x301")
        self.fine=report("201x401",0.01)

    def test_all_seven_converged_roots_pass_prespecified_mesh_deltas(self):
        result=compare(self.base,self.fine)
        self.assertEqual(result["status"],"PASS")
        self.assertEqual(len(result["models"]),7)
        self.assertEqual(result["EOS_Bayes"],"NOT_RUN")

    def test_mesh_drift_fails_and_is_retained(self):
        self.fine=report("201x401",0.2)
        result=compare(self.base,self.fine)
        self.assertEqual(result["status"],"FAIL")
        self.assertEqual(len(result["failures"]),7)

    def test_failed_or_missing_eos_root_is_not_dropped(self):
        self.fine["eos"]["WFF1"]["status"]="NO_VALIDATED_STABLE_CROSSING"
        result=compare(self.base,self.fine)
        self.assertEqual(result["status"],"FAIL")
        self.assertEqual([row["eos"] for row in result["failures"]],["WFF1"])

    def test_eos_source_hash_mismatch_fails(self):
        self.fine["eos"]["ENG"]["source_npz_sha256"]="different"
        result=compare(self.base,self.fine)
        self.assertEqual(result["status"],"FAIL")


if __name__ == "__main__":
    unittest.main()

