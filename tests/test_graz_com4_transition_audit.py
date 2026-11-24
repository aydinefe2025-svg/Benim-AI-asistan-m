import unittest
from research.battery_curve_audit.graz_com4_transition_audit import audit_rows, Row

def r(n,d,i,p,v=4.):
    return Row(n,float(n),d,v,i,p)

class Transitions(unittest.TestCase):
    def test_boundary_and_same_device(self):
        a=audit_rows([r(2,'COM3',1,4),r(3,'COM4',1,4),r(4,'COM4',2,0),r(5,'COM4',2,0),r(6,'COM3',3,12),r(7,'COM4',0,0)])
        self.assertEqual(a['flagged_rows'],2)
        e=a['episodes'][0]
        self.assertEqual(e['first_line'],4)
        self.assertEqual(e['last_line'],5)
        self.assertEqual(e['before_immediate']['line'],3)
        self.assertEqual(e['after_immediate']['device'],'COM3')
        self.assertEqual(e['after_same_device']['line'],7)
        self.assertEqual(e['after_same_device']['numeric_state'],'small_vi')
    def test_missing_boundary(self):
        e=audit_rows([r(2,'COM4',2,0)])['episodes'][0]
        self.assertIsNone(e['before_immediate'])
        self.assertIsNone(e['after_same_device'])
    def test_merge_short_gap_only(self):
        a=audit_rows([r(n,'COM4',2,0 if n in (2,6,11) else 8) for n in range(2,12)])
        self.assertEqual([x['flagged_rows'] for x in a['episodes']],[2,1])
        self.assertEqual(a['episodes'][0]['intervening_unflagged_rows'],3)
    def test_not_count_other_device_as_com4(self):
        with self.assertRaises(ValueError): audit_rows([r(2,'COM3',1,0)])
    def test_reject_nonmonotonic_or_nonfinite(self):
        for rows in ([r(3,'COM4',2,0),r(2,'COM4',2,0)],[r(2,'COM4',float('nan'),0)]):
            with self.assertRaises(ValueError): audit_rows(rows)
if __name__=='__main__':unittest.main()
