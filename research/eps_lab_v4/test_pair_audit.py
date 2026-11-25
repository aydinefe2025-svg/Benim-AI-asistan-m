import unittest
from pair_audit import name,curve
class Test(unittest.TestCase):
 def test_name(self):
  self.assertEqual(name('./IV/12_a_b_c.csv','IV'),'IV/12_a_b_c.csv')
 def test_bad_name(self):
  for a in ['../IV/x.csv','IV/../x.csv','RefIV/x.csv']:
   with self.assertRaises(ValueError):name(a,'IV')
 def test_power_and_duplicates(self):
  x=curve(b',V,I\n0,-1,3\n1,0,3\n2,1,2\n3,2,2\n4,2,1.5\n5,3,1\n6,4,0\n7,5,-1\n')
  self.assertEqual(x['sampled_Pmax_W'],4);self.assertEqual(x['nonincreasing_V_pairs'],1)
 def test_nonfinite(self):
  with self.assertRaises(ValueError):curve(b'V,I\n'+b'1,nan\n'*8)
if __name__=='__main__':unittest.main()