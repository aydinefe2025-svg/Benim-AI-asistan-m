import io
import zipfile
import unittest
from research.battery_curve_audit import graz_five_sp_full_row_profile as m


def test_zip(body):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        z.writestr('x/Fresh cell 01/test_logfile.txt',body)
    return zipfile.ZipFile(io.BytesIO(b.getvalue()))

class TestGrazRealSpSchema(unittest.TestCase):
    def test_six_column_valid_parser_and_time(self):
        text='Test : X\nStart time : 1730107830.1234\nTime\tPosition X[mm]\tPositionZ[mm]\tSensor 1[micro-m]\tSensor 2[micro-m]\tSensor 3[micro-m]\n0.0 1 2 3 4 5\n0.5 1.5 2.5 3.5 4.5 5.5\n'
        with test_zip(text) as z:
            x=m.profile_sp(z,z.namelist()[0])
        self.assertEqual(x['row_count_checks']['valid_six_numeric_rows'],2)
        self.assertEqual(x['numeric_column_minmax']['1'],[1.,1.5])
        self.assertEqual(x['time_nonincreasing_step_count'],0)
        self.assertTrue(x['original_time_column_unit_unverified'])
    def test_malformed_row_safely_counted(self):
        text='Start time: 1234567890\nTime Position X[mm] PositionZ[mm] Sensor 1[micro-m] Sensor 2[micro-m] Sensor 3[micro-m]\n0 1 2 3 4 5\n1 NA 2 3 4 5\n2 1 2\n'
        with test_zip(text) as z: x=m.profile_sp(z,z.namelist()[0])
        self.assertEqual(x['row_count_checks']['valid_six_numeric_rows'],1)
        self.assertEqual(x['row_count_checks']['rows_invalid_numeric'],1)
        self.assertEqual(x['row_count_checks']['rows_wrong_token_count'],1)
    def test_missing_epoch_fails(self):
        with test_zip('Time Position X[mm] PositionZ[mm]\n1 2 3 4 5 6\n') as z:
            with self.assertRaisesRegex(ValueError,'missing epoch'):m.profile_sp(z,z.namelist()[0])
    def test_no_nan_or_overflow_accepted(self):
        self.assertIsNone(m.isnum('NaN'))
        self.assertIsNone(m.isnum('Infinity'))
        self.assertIsNone(m.isnum('1e99'))
    def test_nonmonotone_flagged(self):
        text='Start time: 1\nTime Position X[mm] PositionZ[mm]\n3 0 0 0 0 0\n2 0 0 0 0 0\n'
        with test_zip(text) as z: x=m.profile_sp(z,z.namelist()[0])
        self.assertEqual(x['time_nonincreasing_step_count'],1)