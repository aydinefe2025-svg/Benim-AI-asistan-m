import io,unittest,zipfile,datetime as dt
from research.battery_curve_audit import graz_signal_alignment as a
from research.battery_curve_audit.graz_source_time_gate import vienna_epoch

class LiveSignalAlignment(unittest.TestCase):
    @staticmethod
    def zfile(filename,body):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr(filename,body)
        return zipfile.ZipFile(io.BytesIO(b.getvalue()))
    def test_original_sp_local_dates_parse_full_samples(self):
        begin='Start time : '+str(vienna_epoch(dt.datetime(2024,10,28,10)))+'\n'
        rows='\tTime\t\tPosition X[mm]\tPositionZ[mm]\tSensor 1[micro-m]\tSensor 2[micro-m]\tSensor 3[micro-m]\n'
        rows+=''.join(f'28/10/2024 10:{i//12:02d}:{(i%12)*5:02d}\t1.0\t1.0\t{100+i}.0\t{200+i}.0\t400.0\n' for i in range(120))
        with self.zfile('Fresh cell 02/SP_test.txt',begin+rows) as z:
            s,start=a.sp_samples(z,z.infolist()[0])
        self.assertEqual(len(s),120)
        self.assertEqual(s[0][0],start)
        self.assertEqual(s[-1][1],219.0)
    def test_near_timestamp_sample_match_and_no_phase_claim(self):
        el=[(float(i),'COM3',3.5,50.0 if i<60 else -50.0) for i in range(100)]
        sp=[(float(i)+.3,100.+i,200.+i,500.) for i in range(0,90,5)]
        r=a.pair_samples(el,sp)
        self.assertEqual(r['matched_sp_samples'],18)
        self.assertEqual(r['sampled_current_sign_counts'],{'positive':12,'negative':6,'near_zero':0})
        self.assertAlmostEqual(r['median_abs_time_error_s'],.3)
        self.assertTrue(r['overlap_verified'])
    def test_disjoint_sp_cannot_claim_alignment(self):
        e=[(float(i),'COM3',3,0) for i in range(10)]
        sp=[(100.+5*i,1,2,3) for i in range(100)]
        d=a.pair_samples(e,sp)
        self.assertFalse(d['overlap_verified'])
        self.assertIsNone(d['sensor1_um_end_minus_start'])
    def test_ambiguous_electrical_nearest_rejected(self):
        e=[(0.,'COM3',3,1),(1.,'COM4',3,-1)]
        s=[(.5,1.,2.,3.)]
        r=a.pair_samples(e,s)
        self.assertEqual(r['ambiguous_matches'],1)
        self.assertFalse(r['overlap_verified'])
    def test_bad_numeric_fails(self):
        with self.assertRaises(ValueError):a._value('NaN')
    def test_unverified_archive_rejected(self):
        with self.assertRaises(Exception):a.inspect_alignment(b'fake',4)
if __name__=='__main__':unittest.main()