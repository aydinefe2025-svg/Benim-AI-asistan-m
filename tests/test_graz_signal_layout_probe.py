import io,unittest,zipfile
from research.battery_curve_audit import graz_signal_layout_probe as p
class ProbeTests(unittest.TestCase):
    def test_electrical_csv_rows_recognized(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            z.writestr('Fresh cell 02/2024.log','Time, Device, Voltage, Current, Power\n2024-10-28_10-15-09-439927, 1, 3.3, -1, -3.3\n2024-10-28_10-15-10-439927, 1, 3.2, -1, -3.2\n')
        with zipfile.ZipFile(io.BytesIO(b.getvalue())) as z:
            m=z.infolist()[0];a=p.summarise_member(z,m,'electrical')
        self.assertEqual(a['parsed_candidate_rows'],2)
        self.assertEqual(a['first_fields'][3],'-1')
        self.assertFalse(a['signal_phase_join_verified'])
    def test_sp_tabular_candidate_rows(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            z.writestr('Fresh cell 03/SP_foo.txt','Start time : 100\n\tTime\t\tPosition X[mm]\tSensor 1[micro-m]\n0\t0\t1\n1,0\t0\t2\n')
        with zipfile.ZipFile(io.BytesIO(b.getvalue())) as z:
            a=p.summarise_member(z,z.infolist()[0],'sp')
        self.assertEqual(a['parsed_candidate_rows'],2)
        self.assertIn('2',a['last_rows'][-1])
    def test_source_missing_rejected(self):
        with self.assertRaises(Exception):p.inspect_source(b'not zip',7)
if __name__=='__main__':unittest.main()