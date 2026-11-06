from pathlib import Path
import tempfile
import unittest
import numpy as np
from validate_jester_rns import stable_reference_radius_at_mass

class TestStableReference(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.source=Path(self.temp.name)/'MPA1.npz'
        np.savez(self.source,masses_EOS=np.linspace(1,2,12),radii_EOS=np.linspace(12,11,12))
    def tearDown(self):self.temp.cleanup()
    def test_interpolation(self):
        self.assertAlmostEqual(stable_reference_radius_at_mass(self.source,1.5),11.5)
    def test_outside_mass_support_rejected(self):
        with self.assertRaises(ValueError):stable_reference_radius_at_mass(self.source,2.5)
    def test_nonmonotone_reference_rejected(self):
        np.savez(self.source,masses_EOS=np.array([1.,1.1,1.05]),radii_EOS=np.array([12.,11.9,11.8]))
        with self.assertRaisesRegex(ValueError,'stable branch'):stable_reference_radius_at_mass(self.source,1.05)

if __name__=='__main__':unittest.main()
