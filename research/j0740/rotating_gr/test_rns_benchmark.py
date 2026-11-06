"""Independent numerical-format + safety checks (full RNS integration in CI)."""
from pathlib import Path
import tempfile
import os
import unittest
from rns_benchmark import parse_rns_output, run_rns, OBSERVED_SPIN_HZ

SAMPLE = '''spin=300\nspin=300\n../eos/eosAPR,  MDIVxSDIV=151x301\ne_c Mass Radius Spin\ne15 Msun km Hz\n1 1.453 11.48 300.0\n'''

class TestRNSOutput(unittest.TestCase):
    def test_published_source_example(self):
        o=parse_rns_output(SAMPLE,central_density=1e15,requested_spin_hz=300)
        self.assertEqual(o["mass_msun"],1.453)
        self.assertEqual(o["radius_eq_km"],11.48)
    def test_spin_rounding_is_accepted(self):
        o=parse_rns_output('1 1.454 11.49 346.5\n',central_density=1e15,requested_spin_hz=OBSERVED_SPIN_HZ)
        self.assertEqual(o["requested_spin_hz"],OBSERVED_SPIN_HZ)
    def test_no_model_result_preserves_solver_diagnostic(self):
        message="RNS: fatal EOS lookup warning, no finite stellar model"
        with self.assertRaises(ValueError) as context:
            parse_rns_output(message,central_density=1e15,requested_spin_hz=346.536369)
        self.assertIn("fatal EOS lookup",str(context.exception))
    def test_source_density_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"central energy density"):
            parse_rns_output(SAMPLE,central_density=2e15,requested_spin_hz=300)
    def test_wrong_spin_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"spin mismatch"):
            parse_rns_output(SAMPLE,central_density=1e15,requested_spin_hz=346.536369)
    def test_unphysical_or_nan_is_rejected(self):
        for text in ('1 0.1 11.48 300.0', '1 nan 11.48 300.0','1 1.453 29 300.0'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_rns_output(text,central_density=1e15,requested_spin_hz=300)
    def test_two_numeric_rows_rejected(self):
        with self.assertRaisesRegex(ValueError,"exactly one"):
            parse_rns_output('1 1.453 11.48 300.0\n1 1.453 11.48 300.0', central_density=1e15,requested_spin_hz=300)
    def test_long_eos_path_is_passed_as_short_relative_name(self):
        # The upstream RNS C code uses char eos_file[80]. A long absolute
        # -f path corrupts adjacent stack variables (eos_type), silently
        # causing a spurious polytrope branch and NaN model outputs.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/('long_path_segment_'*6)
            root.mkdir()
            eos=root/'eosMPA1_source_matched'
            eos.write_text('example table',encoding='utf-8')
            binary=Path(td)/'fake_rns.sh'
            binary.write_text("""#!/bin/sh
if [ ${#2} -ge 80 ]; then echo path_overflow; exit 13; fi
if [ ! -f "$2" ]; then echo source_missing; exit 12; fi
printf "1 1.453 11.48 300.0\n"
""",encoding='utf-8')
            binary.chmod(0o755)
            out=run_rns(binary,eos,central_density=1e15,spin_hz=300)
            self.assertEqual(out['radius_eq_km'],11.48)
    def test_bad_model_request_without_binary(self):
        with self.assertRaises(ValueError):
            run_rns(Path('/not/an/executable'),Path('/not/an/eos'),central_density=0,spin_hz=300)
        with self.assertRaises(ValueError):
            run_rns(Path('/not/an/executable'),Path('/not/an/eos'),central_density=1e15,spin_hz=-1)

if __name__ == '__main__':unittest.main()
