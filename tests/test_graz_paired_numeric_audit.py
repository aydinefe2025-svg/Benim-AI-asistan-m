import io, unittest
from datetime import datetime, timedelta
from research.battery_curve_audit.graz_paired_numeric_audit import (
   log_rows,sp_rows,align,integrate_signs,file_groups,finite
)

class GrazRealPairedTest(unittest.TestCase):
    def electrical(self):
        return io.BytesIO(
            b"Time, Device, Voltage, Current, Power\n"
            b"2024-01-01_00-00-00-000000, COM3,3.0, 75.0,225.0\n"
            b"2024-01-01_00-00-02-000000, COM3,2.9, 75.0,217.5\n"
            b"2024-01-01_00-00-04-000000, COM3,3.0, 0.0,0.0\n")
    def mechanical(self):
        return io.BytesIO(
            b"Test: Original\nTime\tPositionX\tSensor 1[micro-m]\tSensor 2[micro-m]\n"
            b"01/01/2024 00:00:01\t114\t66\t1700\t1200\t3000\n"
            b"01/01/2024 00:00:03\t114\t66\t1699\t1199\t3000\n")
    def test_real_logger_schema_and_units(self):
        rows=log_rows(self.electrical())
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[0][2],75)
    def test_time_integral(self):
        d=integrate_signs(log_rows(self.electrical()))
        self.assertAlmostEqual(d["positive_current_throughput_Ah"],0.0625,places=7)
    def test_mechanical_channel_schema(self):
        rows=sp_rows(self.mechanical())
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0][1],1700)
    def test_same_clock_alignment(self):
        r=align(log_rows(self.electrical()),sp_rows(self.mechanical()))
        self.assertEqual(r["time_aligned_measurements"],2)
        self.assertEqual(r["sensor1_aligned_range_um"],[1699.0,1700.0])
    def test_shifted_time_refused(self):
        shifted=io.BytesIO(self.mechanical().getvalue().replace(b"00:00:01",b"01:00:01").replace(b"00:00:03",b"01:00:03"))
        self.assertEqual(align(log_rows(self.electrical()),sp_rows(shifted))["time_aligned_measurements"],0)
    def test_wrong_logger_header(self):
        with self.assertRaises(ValueError):log_rows(io.BytesIO(b"bad,x\n1,2\n"))
    def test_nonfinite_numeric_fails(self):
        with self.assertRaises(ValueError):finite("nan")
    def test_missing_cell_group_fails(self):
        with self.assertRaises(ValueError):file_groups(["Fresh cell 01/example.log"])
    def test_nonmonotonic_mechanical_fails(self):
        bad=self.mechanical().getvalue()+b"01/01/2024 00:00:02\t114\t66\t1698\t1198\t3000\n"
        with self.assertRaises(ValueError):sp_rows(io.BytesIO(bad))
    def test_current_sign_separation(self):
        t=datetime(2024,1,1)
        x=[(t,3.,10.,30.),(t+timedelta(seconds=2),3.,-10.,-30.)]
        r=integrate_signs(x)
        self.assertAlmostEqual(r["positive_current_throughput_Ah"],10/3600,places=7)
        self.assertAlmostEqual(r["negative_current_throughput_Ah"],10/3600,places=7)

if __name__=="__main__": unittest.main()
