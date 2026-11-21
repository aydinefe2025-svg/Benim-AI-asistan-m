import unittest
from rns_surface_boundary_probe import patch_source,PATCH

C="star->e_surface=7.8*C*C*KSCALE;\np_surface=1.01e8*KSCALE;\nstar->enthalpy_min=1.0/(C*C);\n"

class PinnedBoundaries(unittest.TestCase):
 def test_hmin_only(self):
  x=patch_source(C,"hmin")
  self.assertIn("pow(10.0,eos->log_h_tab[1])",x)
  self.assertIn("p_surface=1.01e8*KSCALE;",x)
 def test_source_surface_and_hmin(self):
  x=patch_source(C,"hmin_surface")
  for n in ("log_h_tab[1]","log_p_tab[1]","log_e_tab[1]"):
   self.assertIn(n,x)
 def test_missing_anchor(self):
  with self.assertRaises(ValueError):patch_source(C.replace("1.0/(C*C)","1.0"),"hmin")
 def test_reject_already_patched(self):
  with self.assertRaises(ValueError):patch_source(patch_source(C,"hmin"),"hmin")
 def test_invalid_variant(self):
  with self.assertRaises(ValueError):patch_source(C,"none")
 def test_exact_variants(self):
  self.assertEqual(set(PATCH),{"hmin","hmin_surface"})

if __name__=="__main__":unittest.main()
