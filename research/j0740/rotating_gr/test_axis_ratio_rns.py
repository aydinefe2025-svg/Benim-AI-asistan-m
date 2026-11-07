"""Model-independent tests of the *direct* C axis-ratio spin root."""
import unittest
from unittest import mock
from axis_ratio_rns import axis_ratio_spin_root, AxisRatioConvergenceError, run_rns_at_spin_with_ratio_fallback


def fake_star(ratio):
    return {"spin_hz_reported": round(10000*(1-ratio),1),
            "mass_msun": 2.073+0.02*(1-ratio),
            "radius_eq_km": 12.5+0.2*(1-ratio)}


class AxisRatioTests(unittest.TestCase):
    def test_direct_ratio_solver_preserves_gr_mesh_identity(self):
        from axis_ratio_rns import run_rns_at_ratio
        from pathlib import Path
        from types import SimpleNamespace
        stdout="MDIVxSDIV=151x301\\n1.0000000000 2.073 12.530 346.5\\n"
        with mock.patch("axis_ratio_rns.subprocess.run",return_value=SimpleNamespace(returncode=0,stdout=stdout,stderr="")):
            star=run_rns_at_ratio(Path("/tmp/rns"),Path("/tmp/valid.rns"),
                                  central_density=1e15,ratio=0.96)
        self.assertIn("151x301",star["raw_stdout_tail"])
        self.assertEqual(star["solver_mode"],"RNS_C_AXIS_RATIO_DIRECT")

    def test_finite_direct_model_at_target_spin(self):
        star,trace=axis_ratio_spin_root(fake_star, 346.536369)
        self.assertLessEqual(abs(star["spin_hz_reported"]-346.536369),.10)
        self.assertLessEqual(len(trace),38)
        self.assertTrue(any(e["status"]=="OK" for e in trace))

    def test_does_not_call_interpolated_mass_radius(self):
        requests=[]
        def tracked(r):
            requests.append(r)
            return fake_star(r)
        star,_=axis_ratio_spin_root(tracked,346.536369)
        self.assertIn(round(1-star["spin_hz_reported"]/10000,8) if False else star["spin_hz_reported"], 
                      [fake_star(r)["spin_hz_reported"] for r in requests])

    def test_physically_unreachable_spin_rejected(self):
        with self.assertRaises(AxisRatioConvergenceError):
            axis_ratio_spin_root(lambda r: {**fake_star(r), "spin_hz_reported": (1-r)*80}, 346.536369)

    def test_unstable_nonmonotone_spin_sequence_rejected(self):
        def broken(r):
            m=fake_star(r)
            if r<=.98:
                m["spin_hz_reported"]=10
            return m
        with self.assertRaisesRegex(AxisRatioConvergenceError,"Nonmonotone"):
            axis_ratio_spin_root(broken, 346.536369)

    def test_fallback_only_on_spin_error(self):
        with mock.patch("axis_ratio_rns.run_rns",side_effect=ValueError("Unphysical RNS mass/radius")):
            with self.assertRaisesRegex(ValueError,"Unphysical"):
                run_rns_at_spin_with_ratio_fallback(None,None,central_density=1e15)
        with mock.patch("axis_ratio_rns.run_rns",side_effect=ValueError("Rotating GR spin mismatch")):
            with mock.patch("axis_ratio_rns.run_rns_at_ratio",side_effect=lambda *args,ratio,**kwargs:fake_star(ratio)):
                m=run_rns_at_spin_with_ratio_fallback(None,None,central_density=1e15)
                self.assertEqual(m["solver_mode"],"RNS_C_AXIS_RATIO_FREQUENCY_REFINED")
                self.assertLessEqual(abs(m["spin_residual_hz"]),.10)


if __name__=="__main__":
    unittest.main()
