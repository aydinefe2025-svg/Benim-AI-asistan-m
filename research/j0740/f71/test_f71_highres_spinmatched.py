import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f71_highres_spinmatched import compare,EOS_SHA,TARGET_HZ
class SequenceTests(unittest.TestCase):
 def doc(self,grid,r1,r2):
  d={'grid':grid,'rns_eos_sha256':EOS_SHA,'stars':{}}
  if grid in ('301x601','401x801'):d['source_F70_EOS_sha256']=d.pop('rns_eos_sha256')
  key='direct_C' if grid in ('301x601','401x801') else 'actual_direct_RNS_C_model'
  for m,r in [('2.073',r1),('2.250',r2)]:d['stars'][m]={key:{'mass_msun':float(m),'spin_hz_reported':TARGET_HZ,'radius_eq_km':r}}
  return d
 def pack(self):return [self.doc('201x401',12.535,12.350),self.doc('251x501',12.5348,12.349),self.doc('301x601',12.5347,12.3486),self.doc('401x801',12.53465,12.34843)]
 def test_numeric_sequence(self):
  s=compare(*self.pack());self.assertEqual(s['status'],'EMPIRICAL_0p25m_LAST_GRID_STEP_PASS_NOT_PROOF_OF_CONTINUUM_LIMIT')
 def test_source_failure(self):
  p=self.pack();p[-1]['source_F70_EOS_sha256']='wrong'
  with self.assertRaises(ValueError):compare(*p)
 def test_spin_failure(self):
  p=self.pack();p[0]['stars']['2.250']['actual_direct_RNS_C_model']['spin_hz_reported']=346.8
  with self.assertRaises(ValueError):compare(*p)
 def test_mass_failure(self):
  p=self.pack();p[-1]['stars']['2.073']['direct_C']['mass_msun']=2.07
  with self.assertRaises(ValueError):compare(*p)
 def test_false_convergence_not_promoted(self):
  p=self.pack();p[-1]['stars']['2.250']['direct_C']['radius_eq_km']=12.3498
  s=compare(*p);self.assertIn('NOT_CERTIFIED',s['status'])
if __name__=='__main__':unittest.main()
