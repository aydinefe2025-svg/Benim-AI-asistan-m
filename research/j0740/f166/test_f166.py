import unittest,copy,json,math,hashlib
from split import prefix_matches
from audit import verify
class Checks(unittest.TestCase):
 def setUp(self):
  self.p=dict(model='WFF1',seed=352001,curve_sha256='curve',curve_zip_sha='zip',mass_fraction=.8,support=.24947354926879406,rows=[dict(index=i,mass=2.,radius=11.,mass_u=.5,logq_mass=0.,logq_nuisance=0.,phase_positive=True,u=[.6]*13) for i in range(4096)])
 def test_exact_prefix(self):
  new=copy.deepcopy(self.p);new['rows']+= [dict(new['rows'][0],index=i) for i in range(4096,8192)]
  prefix_matches(self.p,new)
  new['rows'][100]['u'][1]=.7
  with self.assertRaises(AssertionError):prefix_matches(self.p,new)
 def test_native_binding(self):
  p=json.dumps(self.p).encode();d=copy.deepcopy(self.p)
  d.update(status='COMPLETE',proposal_sha256=hashlib.sha256(p).hexdigest(),reference_start=-21863.348610369474,reference_end=-21863.348610369474)
  for r in d['rows']:r.update(status='FINITE',p=[2.,11.]+[0.]*13,detectors=[-5.]*4,logL=-20.,logweight=-20.-math.log(d['support']))
  w,phase=verify(p,json.dumps(d).encode());self.assertEqual(len(w),4096)
  d['rows'][99]['logq_mass']=.01
  with self.assertRaises(AssertionError):verify(p,json.dumps(d).encode())
 def test_unresolved_not_zero(self):
  p=json.dumps(self.p).encode();d=copy.deepcopy(self.p)
  d.update(status='COMPLETE',proposal_sha256=hashlib.sha256(p).hexdigest(),reference_start=-21863.348610369474,reference_end=-21863.348610369474)
  for r in d['rows']:r.update(status='PRIOR_REJECTED',logL=None,logweight=None)
  self.assertEqual(len(verify(p,json.dumps(d).encode())[0]),4096)
  d['rows'][8]['status']='UNRESOLVED_NATIVE'
  with self.assertRaises(AssertionError):verify(p,json.dumps(d).encode())
if __name__=='__main__':unittest.main()
