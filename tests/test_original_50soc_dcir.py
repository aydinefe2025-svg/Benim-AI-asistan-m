"""No external-network unit tests. Publisher data are exercised separately in CI."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from research.battery_curve_audit.original_50soc_dcir import (
    parse_seconds,lerp,integral_capacity,pseudo_ocv_v,pulse_metrics,
    thermal_secant,source_archive
)


def fake_ocv(st=1):
    # Monotone source-like 3.6 Ah low-current pseudo-OCV traces
    # Charge rising / discharge falling by 1.2 V across about 4.0Ah.
    data=[]
    for n in range(601):
        t=n*100
        f=n/600
        v=(2.8+1.3*f) if st>0 else (4.1-1.3*f)
        data.append((t,v,st*0.245,22.0))
    return data


def fake_pulse():
    # 10-second 1C pulse after 4 earlier idle samples, with 30s stable 1C.
    idle=[(950,3.72,0,22),(960,3.72,0,22),(970,3.72,0,22),(980,3.72,0,22),(990,3.72,0,22)]
    pulse=[(1000,3.72,0,22)]
    pulse.extend((1000.1+n*.02,3.59-0.002*(n*.02),-4.9,22) for n in range(1500))
    return pulse,idle


class UnitOriginalPulseTests(unittest.TestCase):
    def test_time_hours_exceed_24(self):
        self.assertAlmostEqual(parse_seconds(' 75:01:30.25'),270090.25)
        for x in ['00:99:00', '0:00:nan', '-1:02:30','01:03']:
            with self.subTest(x=x),self.assertRaises(ValueError):parse_seconds(x)

    def test_interpolate_no_extrapolate(self):
        self.assertAlmostEqual(lerp([0,10,20],[1,5,9],5),3)
        for p in (-1,21):
            with self.assertRaises(ValueError):lerp([0,10,20],[1,5,9],p)

    def test_pseudo_ocv_curve_orientation(self):
        ch,dc=fake_ocv(1),fake_ocv(-1)
        self.assertLess(pseudo_ocv_v(ch,dc,.49),pseudo_ocv_v(ch,dc,.50))

    def test_pulse_raw_and_ocv_corrected(self):
        pulse,idle=fake_pulse()
        x=pulse_metrics(pulse,idle,fake_ocv(1),fake_ocv(-1))
        self.assertGreater(x['dcir_raw_milliohm'],x['dcir_pseudoOCV_corrected_milliohm'])
        self.assertLess(x['ocv_correction_mV'],0)
        self.assertGreater(x['dcir_pseudoOCV_corrected_milliohm'],15)
        self.assertAlmostEqual(x['pulse_current_A'],-4.9)

    def test_missing_rest_rejected(self):
        pulse,idle=fake_pulse()
        with self.assertRaisesRegex(ValueError,'rest'):
            pulse_metrics(pulse,idle[:1],fake_ocv(1),fake_ocv(-1))

    def test_wrong_or_no_1C_pulse_rejected(self):
        pulse,idle=fake_pulse()
        wrong=[(t,v,-1.0 if i<0 else i,T) for t,v,i,T in pulse]
        with self.assertRaisesRegex(ValueError,'negative pulse'):
            pulse_metrics(wrong,idle,fake_ocv(1),fake_ocv(-1))

    def test_pulse_clock_reverse_rejected(self):
        pulse,idle=fake_pulse()
        pulse[200]=(pulse[199][0],pulse[200][1],pulse[200][2],22)
        with self.assertRaisesRegex(ValueError,'non-monotonic'):
            pulse_metrics(pulse,idle,fake_ocv(1),fake_ocv(-1))

    def test_malformed_publisher_source_rejected(self):
        with TemporaryDirectory() as temp:
            path=Path(temp)/'x.zip'
            with ZipFile(path,'w') as z:z.writestr('fake.csv','abc')
            with self.assertRaisesRegex(ValueError,'MD5/size'):
                source_archive(path,'x',path.stat().st_size,'00000000000000000000000000000000')

    def test_normalization_not_instrument_calibration(self):
        lo={'pre_pulse_surface_C':10,'dcir_pseudoOCV_corrected_milliohm':33.}
        hi={'pre_pulse_surface_C':23,'dcir_pseudoOCV_corrected_milliohm':23.}
        slope=thermal_secant(lo,hi)
        self.assertAlmostEqual(slope,-10/13)
        self.assertAlmostEqual(.20-slope*(-.3),-.03076923076923077)

    def test_slope_needs_distinct_temperatures(self):
        lo={'pre_pulse_surface_C':10,'dcir_pseudoOCV_corrected_milliohm':33.}
        hi={'pre_pulse_surface_C':12,'dcir_pseudoOCV_corrected_milliohm':23.}
        with self.assertRaises(ValueError):thermal_secant(lo,hi)

if __name__=='__main__':unittest.main()