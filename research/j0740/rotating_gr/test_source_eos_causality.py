import unittest
import numpy as np
from source_eos_causality import profile
class SourceEOSCausalityTests(unittest.TestCase):
    def test_causal_native_cs2(self):
        e=np.geomspace(1e-13,1e-8,300);p=np.geomspace(1e-16,1e-11,300)
        a=profile(e,p,np.full(300,.75))
        self.assertEqual(a["status"],"SOURCE_NATIVE_CS2_SCREEN_PASS")
        self.assertEqual(a["native_superluminal_node_count"],0)
    def test_acausal_source_onset_not_suppressed(self):
        e=np.geomspace(1e-13,1e-8,300);p=np.geomspace(1e-16,1e-11,300)
        cs2=np.full(300,.75);cs2[240:]=1.14
        a=profile(e,p,cs2)
        self.assertEqual(a["status"],"SOURCE_NATIVE_CS2_SUPERLUMINAL")
        self.assertEqual(a["first_superluminal_index"],240)
    def test_low_energy_turnback_retained_as_source_diagnostic(self):
        e=np.geomspace(1e-13,1e-8,300);p=np.geomspace(1e-16,1e-11,300)
        e[2]=e[1]*.95
        a=profile(e,p,np.full(300,.75))
        self.assertEqual(a["raw_energy_nonincreasing_segments"],1)
    def test_nonmonotonic_pressure_refused(self):
        e=np.geomspace(1e-13,1e-8,300);p=np.geomspace(1e-16,1e-11,300)
        p[29]=p[28]
        with self.assertRaisesRegex(ValueError,"invalid"):
            profile(e,p,np.full(300,.75))
if __name__=="__main__":unittest.main()
