import unittest
from resilient_mass_root import resilient_mass_root, NumericalRootError


def model(ec):
    return {"mass_msun": 1.9 + (ec-1e15)/1e15, "radius_eq_km": 12.5}


class ResilientMassRootTests(unittest.TestCase):
    def test_regular_mass_root(self):
        r, t = resilient_mass_root(model, 2.073, 1.1e15, 1.3e15)
        self.assertLessEqual(abs(r["mass_msun"]-2.073), .0015)
        self.assertTrue(any(x["status"] == "OK" for x in t))

    def test_numeric_rejections_are_not_silently_used(self):
        def flaky(ec):
            if abs(ec/1e15 - 1.173) < 0.00001:
                raise ValueError("Rotating GR spin mismatch")
            return model(ec)
        r, t = resilient_mass_root(flaky, 2.073, 1.1e15, 1.3e15)
        self.assertLessEqual(abs(r["mass_msun"]-2.073), .0015)
        self.assertTrue(any(x["status"] == "REJECTED" for x in t))

    def test_no_root_if_all_internal_points_fail(self):
        def endpoint_only(ec):
            if ec not in (1.1e15, 1.3e15):
                raise RuntimeError("numerical nonconvergence")
            return model(ec)
        with self.assertRaises(NumericalRootError):
            resilient_mass_root(endpoint_only, 2.073, 1.1e15, 1.3e15)

    def test_no_extrapolation(self):
        with self.assertRaisesRegex(ValueError, "does not contain"):
            resilient_mass_root(model, 2.073, 1e15, 1.1e15)

    def test_nonmonotone_is_not_accepted(self):
        def weird(ec):
            if 1.1e15 < ec < 1.3e15:
                return {"mass_msun": 2.5, "radius_eq_km": 12.5}
            return model(ec)
        with self.assertRaises(NumericalRootError):
            resilient_mass_root(weird, 2.073, 1.1e15, 1.3e15)


if __name__ == "__main__":
    unittest.main()
