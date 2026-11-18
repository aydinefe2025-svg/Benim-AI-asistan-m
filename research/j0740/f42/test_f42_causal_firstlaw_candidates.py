import unittest,sys,pathlib,tempfile,json
import numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from f42_causal_firstlaw_candidates import Candidate,causal_energy_envelope

class F42Tests(unittest.TestCase):
 def setUp(self):
  self.p=np.geomspace(1e-6,1,301)
  self.e=4*self.p**.60
  self.e[101]=self.e[100]*.99 # source local energy reversal
  self.e[240:]=self.e[240]+(self.p[240:]-self.p[240])*.15 # acausal high-pressure segment
 def test_source_is_not_edited(self):
  orig=self.e.copy();c=Candidate(self.p,self.e)
  np.testing.assert_array_equal(self.e,orig)
  self.assertTrue(np.any(c.e!=orig))
 def test_causal_all_knots(self):
  c=Candidate(self.p,self.e)
  self.assertTrue(np.all((c.cs2>0)&(c.cs2<=.99*(1+3e-11))))
 def test_analytic_enthalpy_and_n_firstlaw(self):
  c=Candidate(self.p,self.e)
  E,H,N,cs=c.values(np.geomspace(self.p[0]*1e-10,self.p[-1],1800))
  self.assertTrue(np.all(np.diff(H)>0))
  self.assertTrue(np.all(np.diff(N)>0))
  self.assertLess(np.max(cs),.99+1e-8)
  mu=(E+np.geomspace(self.p[0]*1e-10,self.p[-1],1800))*np.exp(-H)/N
  self.assertLess(max(mu)/min(mu)-1,1e-10)
 def test_first_law_interval_identity(self):
  c=Candidate(self.p,self.e)
  i=30
  E,H,N,S=c.values(np.array([self.p[i],self.p[i+1]]))
  de=E[1]-E[0];dp=self.p[i+1]-self.p[i]
  dh=(H[1]-H[0]);dlnn=np.log(N[1]/N[0]);alpha=de/dp
  self.assertAlmostEqual(dlnn,alpha*dh,places=11)
 def test_zero_pressure_gas_limit(self):
  c=Candidate(self.p,self.e)
  e,h,n,cs=c.values(np.array([self.p[0]*1e-10,self.p[0]*1e-8]))
  self.assertTrue(np.all((h>0)&(cs>0)&(cs<1)))
 def test_rns_table_positive_and_ordered(self):
  c=Candidate(self.p,self.e)
  t,meta=c.rns_table()
  self.assertEqual(t.shape,(200,4))
  self.assertTrue(np.all(np.diff(t,axis=0)>0))
  self.assertEqual(meta['physical_EOS_acceptance'],'NOT_ESTABLISHED')
 def test_missing_negative_energy_rejected(self):
  e=self.e.copy();e[2]=-1
  with self.assertRaises(ValueError):causal_energy_envelope(self.p,e)
 def test_duplicate_pressure_rejected(self):
  p=self.p.copy();p[30]=p[29]
  with self.assertRaises(ValueError):Candidate(p,self.e)
 def test_supercausal_raw_is_repaired_not_relabelled(self):
  c=Candidate(self.p,self.e)
  self.assertGreater(c.rns_table()[1]['source_perturbed_nodes'],0)
 def test_invalid_pressure_query_rejected(self):
  c=Candidate(self.p,self.e)
  with self.assertRaises(ValueError):c.values(np.array([self.p[-1]*2]))

if __name__=='__main__':unittest.main()
