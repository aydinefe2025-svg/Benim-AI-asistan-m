import unittest
from agv_adjacent_current_bounds import analyze, bounds

def row(n,t,q,date='2020-01-01',pack='FB-0'):
    return dict(counter=str(n),cycletime=str(t),totaldischarge=str(q),date=date,battery=pack)

class Tests(unittest.TestCase):
    def test_quantization(self):
        self.assertEqual(bounds(3,3600),(2,4))
        self.assertEqual(bounds(0,3600),(0,1))
        self.assertIsNone(bounds(1,0))
    def test_gap_and_endpoint(self):
        a=analyze([row(1,100,10),row(2,3600,13),row(4,500,30)])
        self.assertEqual(a['adjacent_count'],1)
        self.assertEqual(a['gap_count'],1)
        self.assertEqual(a['pairs'][0]['current_interval_A'],[2,4])
    def test_telescoping(self):
        a=analyze([row(1,100,10),row(2,3600,13),row(3,3600,16)])
        self.assertEqual(a['packs']['FB-0']['telescoped_current_interval_A'],[2.5,3.5])
    def test_zero_time_breaks_run(self):
        a=analyze([row(1,100,10),row(2,3600,13),row(3,0,14),row(4,3600,17)])
        self.assertEqual(a['packs']['FB-0']['valid_runs'],2)
    def test_negative_and_duplicate_fail(self):
        for rows in ([row(1,1,10),row(1,1,11)],[row(1,1,10),row(2,1,9)]):
            with self.assertRaises(ValueError):analyze(rows)
if __name__=='__main__':unittest.main()