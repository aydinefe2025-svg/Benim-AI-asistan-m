"""Focused source-identity and numerical-sensitivity tests; no synthetic field claims."""
import csv
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile
from research.battery_curve_audit.phase_boundary_thermal_audit import (
    as_seconds,capacity_after_edge_trim_Ah,source_phase_summary,sidecar_identity,run,SOURCES,
)


def sample_zip(rows_each=56, broken=False, pause=False, missing_temp=False):
    s=io.StringIO();w=csv.writer(s)
    header=['run_time','step_type','c_cur','c_vol','c_surf_temp','amb_temp']
    if missing_temp:header.remove('c_surf_temp')
    w.writerow(header)
    def write(row):
        if missing_temp:row.pop('c_surf_temp')
        w.writerow([row[k] for k in header])
    for i in range(rows_each):
        write({'run_time':str(i*2),'step_type':21,'c_cur':2,'c_vol':3.7,
               'c_surf_temp':10+i/10,'amb_temp':float('nan')})
    write({'run_time':str(rows_each*2),'step_type':0,'c_cur':0,'c_vol':3.7,
           'c_surf_temp':12,'amb_temp':11})
    for i in range(rows_each):
        write({'run_time':str((rows_each+i)*2+1 if not broken else (rows_each-i)*2+1),
               'step_type':22,'c_cur':-3,'c_vol':3.5,
               'c_surf_temp':11+i/10,'amb_temp':10})
        if pause and i==30:
            write({'run_time':str((rows_each+i)*2+2),'step_type':0,'c_cur':0,
                   'c_vol':3.5,'c_surf_temp':13,'amb_temp':10})
    f=io.BytesIO()
    with ZipFile(f,'w') as z:z.writestr('synthetic.csv',s.getvalue())
    return f.getvalue()

class BoundaryThermalTests(unittest.TestCase):
    def test_time_parser_precise_bounded(self):
        self.assertAlmostEqual(as_seconds(' 0:00:00.0020'),.002)
        self.assertAlmostEqual(as_seconds('13:20:54.677'),48054.677)
        for s in ('-2','NaN','0:60:04','12:23:61','01:02:03.0000001'):
            with self.subTest(s=s),self.assertRaises(ValueError):as_seconds(s)

    def test_synthetic_temperature_time_and_capacity(self):
        with ZipFile(io.BytesIO(sample_zip())) as z:x=source_phase_summary(z,'synthetic.csv')
        self.assertEqual(x['all_csv_rows'],113)
        self.assertEqual(x['phases']['charge']['source_rows'],56)
        self.assertEqual(x['phases']['discharge']['source_rows'],56)
        self.assertAlmostEqual(x['phases']['discharge']['capacity_right_Ah'],330/3600,places=7)
        self.assertEqual(x['phases']['discharge']['mean_ambient_temperature_C']['mean'],10)
        self.assertIsNotNone(x['phases']['discharge']['time_weighted_surface_temp_C'])
        self.assertGreater(x['phases']['discharge']['time_fraction_surface_interval_above_15C'],0)

    def test_missing_temp_rejected(self):
        with ZipFile(io.BytesIO(sample_zip(missing_temp=True))) as z:
            with self.assertRaisesRegex(ValueError,'required source fields'):
                source_phase_summary(z,'synthetic.csv')

    def test_backwards_time_and_multiple_segments_rejected(self):
        with ZipFile(io.BytesIO(sample_zip(broken=True))) as z:
            with self.assertRaisesRegex(ValueError,'backwards'):
                source_phase_summary(z,'synthetic.csv')
        with ZipFile(io.BytesIO(sample_zip(pause=True))) as z:
            with self.assertRaisesRegex(ValueError,'multiple'):
                source_phase_summary(z,'synthetic.csv')

    def test_hypothetical_edge_trim_math(self):
        arr=[(2,0.02),(3,0.06),(1,0.03)]
        self.assertAlmostEqual(capacity_after_edge_trim_Ah(arr,0,'start'),.11)
        self.assertAlmostEqual(capacity_after_edge_trim_Ah(arr,1,'start'),.10)
        self.assertAlmostEqual(capacity_after_edge_trim_Ah(arr,2,'start'),.09)
        self.assertAlmostEqual(capacity_after_edge_trim_Ah(arr,1,'end'),.08)
        self.assertAlmostEqual(capacity_after_edge_trim_Ah(arr,100,'end'),0)
        with self.assertRaises(ValueError):capacity_after_edge_trim_Ah(arr,-1,'start')

    def test_source_sidecar_identity_instrument_stability_guard(self):
        meta=("Laboratory identifier: INT\nInternal cell serial: TEST1\nTestpoint: k04\n"
              "Measurement start date: 30.09.2021\nMeasurement device used: Basytec CTS\n"
              "Test channel: CH04/05\nClimate chamber used: Binder MK240\n"
              "Climate chamber temperature setpoint: 10°C\nPosition within climate chamber: 13\n")
        with io.BytesIO() as f:
            with ZipFile(f,'w') as z:z.writestr('original_ET_T10_meta.txt',meta)
            with ZipFile(io.BytesIO(f.getvalue())) as z:
                x=sidecar_identity(z,'original_ET_T10.csv')
                self.assertEqual(x['lab'],'INT')
                self.assertEqual(x['setpoint_C'],10)
                self.assertEqual(x['measurement_date'],'2021-09-30')
        with io.BytesIO() as f:
            with ZipFile(f,'w') as z:z.writestr('original_ET_T10_meta.txt',meta.replace('10°C','23°C'))
            with ZipFile(io.BytesIO(f.getvalue())) as z:
                with self.assertRaisesRegex(ValueError,'not 10'):
                    sidecar_identity(z,'original_ET_T10.csv')

    def test_original_archive_pins_required(self):
        with TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'source missing'):
                run(Path(folder))
            path=Path(folder)/SOURCES[0][1]
            path.write_bytes(b'fake')
            with self.assertRaisesRegex(ValueError,'source missing'):
                run(Path(folder))

if __name__=='__main__':unittest.main()