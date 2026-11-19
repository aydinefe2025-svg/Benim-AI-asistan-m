"""Synthetic parser regressions; real checksums are checked separately in CI."""
import hashlib
from unittest.mock import patch
import unittest
from research.battery_curve_audit import pybamm_published_benchmark as b


def synthetic(delta=0.0):
    lines=["Time [s] Voltage [V]"]
    for i in range(150):
        lines.append(f"{i*9} {3.60+delta+i*0.001:.8f}")
    return ("\n".join(lines)+"\n").encode()


class PyBaMMPublishedTimeVoltageTests(unittest.TestCase):
    def test_first_column_is_seconds_and_second_is_voltage(self):
        t,v=b.parse_voltage_curve(synthetic())
        self.assertEqual(len(t),150)
        self.assertEqual((t[0],t[-1]),(0.,1341.))
        self.assertAlmostEqual(v[0],3.60)
        self.assertAlmostEqual(v[-1],3.749)

    def test_soc_or_current_mislabeled_header_rejected(self):
        for header in (b"SOC [pct] Voltage [V]",b"Voltage [V] Time [s]",b"Time [s] Current [A]"):
            raw=header+b"\n"+synthetic().split(b"\n",1)[1]
            with self.subTest(header=header),self.assertRaises(ValueError):
                b.parse_voltage_curve(raw)

    def test_nonfinite_and_repeated_measurement_time_rejected(self):
        for raw in (
            synthetic().replace(b"3.60000000",b"nan",1),
            synthetic().replace(b"9 3.60100000",b"0 3.60100000",1),
        ):
            with self.subTest(sample=raw[0:40]),self.assertRaises(ValueError):
                b.parse_voltage_curve(raw)

    def test_no_three_column_or_short_data_silent_acceptance(self):
        for raw in (b"time voltage current\n0 3.4 1.0\n",b"0 3.4\n1 3.3\n",b""):
            with self.subTest(raw=raw[:30]),self.assertRaises(ValueError):
                b.parse_voltage_curve(raw)

    def test_modified_source_hash_fails_before_curve_screen(self):
        good1,good2=synthetic(),synthetic(.09)
        fake={"0.5C":("a.txt",hashlib.sha256(good1).hexdigest()),
              "1C":("b.txt",hashlib.sha256(good2).hexdigest())}
        with patch.dict(b.SOURCE,fake,clear=True):
            with self.assertRaisesRegex(ValueError,"SHA256"):
                b.audit_published_curves({"0.5C":good1,"1C":good2+b"\n"})

    def test_two_original_shapes_get_controlled_probes_not_field_labels(self):
        a,c=synthetic(),synthetic(.08)
        fake={"0.5C":("a.txt",hashlib.sha256(a).hexdigest()),
              "1C":("b.txt",hashlib.sha256(c).hexdigest())}
        with patch.dict(b.SOURCE,fake,clear=True):
            out=b.audit_published_curves({"0.5C":a,"1C":c})
        self.assertEqual(out["decision"],"PASS_CONTROLLED_RESEARCH_SCREEN_ONLY")
        self.assertEqual(len(out["source_curves"]),2)
        self.assertTrue(all(x["controlled_1mv_detected"] and not x["controlled_10mv_detected"] for x in out["source_curves"]))
        self.assertTrue(out["no_field_certification"])
        self.assertEqual((out["time_unit"],out["voltage_unit"]),("s","V"))

    def test_missing_rate_is_not_fake_two_source_test(self):
        with self.assertRaises(ValueError):
            b.audit_published_curves({"0.5C":synthetic()})


if __name__=="__main__":
    unittest.main()
