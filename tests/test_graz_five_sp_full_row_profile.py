import datetime as dt, io, zipfile, unittest
from research.battery_curve_audit import graz_five_sp_full_row_profile as m

def test_zip(body):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr('x/Fresh cell 01/test_logfile.txt',body)
    return zipfile.ZipFile(io.BytesIO(b.getvalue()))

def standard_fixture(n=105, reverse=False):
    lines=['Test : X','Start time : 1730107830.123456',
           'Time\tPosition X[mm]\tPositionZ[mm]\tSensor 1[micro-m]\tSensor 2[micro-m]\tSensor 3[micro-m]']
    for i in range(n):
        sec=(i if not reverse else n-i)%60
        minute=(i if not reverse else n-i)//60
        t=(dt.datetime(2024,10,28,10,30,30)+dt.timedelta(minutes=minute,seconds=sec)).strftime('%d/%m/%Y %H:%M:%S')
        lines.append(f'{t}\t1.0\t2.0\t{3+i/10:.2f}\t4\t5')
    return '\n'.join(lines)+'\n'

class TestOriginalSpSchema(unittest.TestCase):
    def test_true_two_token_sp_time_and_valid_five_numeric_columns(self):
        with test_zip(standard_fixture()) as z: p=m.profile_sp(z,z.namelist()[0])
        self.assertEqual(p['counts']['valid_six_field_rows'],105)
        self.assertEqual(p['first_original_timestamp_unzoned'],'2024-10-28T10:30:30')
        self.assertEqual(p['numeric_column_ranges_in_source_reported_units']['Position X[mm]'],[1.,1.])
        self.assertIn('Sensor 3[micro-m]',p['exact_constant_original_numeric_channels'])
    def test_true_source_date_day_first_and_unparseable_rejected(self):
        self.assertEqual(m.parse_sp_timestamp('12/06/2024','15:31:37').month,6)
        with self.assertRaises(ValueError):m.parse_sp_timestamp('31/13/2024','15:31:37')
    def test_in_global_electrical_window_counts_not_sensor_sync(self):
        lo=dt.datetime(2024,10,28,10,30,40);hi=dt.datetime(2024,10,28,10,31,00)
        with test_zip(standard_fixture()) as z:p=m.profile_sp(z,z.namelist()[0],lo,hi)
        self.assertEqual(p['counts']['rows_inside_electrical_recording_window_candidate'],21)
        self.assertFalse(p['electrical_and_SP_instrument_clocks_independently_synchronized'])
    def test_minimum_numeric_source_rows_fail_closed(self):
        with test_zip(standard_fixture(n=3)) as z:
            with self.assertRaisesRegex(ValueError,'<100'):m.profile_sp(z,z.namelist()[0])
    def test_malformed_finite_test(self):
        self.assertIsNone(m.isnum('nan'))
        self.assertIsNone(m.isnum('1e100'))
        self.assertIsNone(m.isnum('abc'))
    def test_reverse_source_timestamps_flagged_not_silently_reordered(self):
        with test_zip(standard_fixture(reverse=True)) as z:p=m.profile_sp(z,z.namelist()[0])
        self.assertGreater(p['counts'].get('nonincreasing_time_steps',0),0)