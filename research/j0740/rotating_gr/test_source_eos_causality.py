import tempfile,unittest
from pathlib import Path
import numpy as np
from source_eos_causality import diagnose

class SourceEOSCausalityTests(unittest.TestCase):
    def write(self,p,e,pressure):
        np.savez(p,e=e,p=pressure)
    def test_causal_linear_eos(self):
        e=np.geomspace(.001,.1,300)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"t.npz";self.write(p,e,e*.5)
            s=diagnose(p)
            self.assertEqual(s["global_causality_status"],"SCREEN_PASS")
    def test_superluminal_onset(self):
        e=np.linspace(.001,.1,300)
        pressure=np.where(e<.04,.5*e,.02+1.2*(e-.04))
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"t.npz";self.write(p,e,pressure)
            s=diagnose(p)
            self.assertEqual(s["global_causality_status"],"SOURCE_TABLE_SUPERLUMINAL_SEGMENTS_PRESENT")
            self.assertLess(s["first_superluminal_interval_rho_low_g_cm3"],s["source_rho_max_g_cm3"])
    def test_nonmonotonic_e_refused(self):
        e=np.linspace(.001,.1,300);e[80]=e[79]
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"t.npz";self.write(p,e,e*.5)
            with self.assertRaisesRegex(ValueError,"nonmonotone"):
                diagnose(p)
if __name__=="__main__":unittest.main()
