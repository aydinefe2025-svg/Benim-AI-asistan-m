"""Fail-closed source/native baryon-number semantics with analytical fake LAL boundary."""
import unittest
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import numpy as np

from f132_native_rest_mass_density import (
    EOS_NAMES, require_source_data, select_api, measure_one, sha,
    BARYON_MASS_AVG_MEV, J_TO_MEV,
)

class FakeLal:
    C_SI=299792458.0
    G_SI=6.67430e-11

class FakeNative:
    def SimNeutronStarEOSByName(self, name):
        assert name in EOS_NAMES
        return name
    def SimNeutronStarEOSPseudoEnthalpyOfPressureGeometrized(self, p,eos):
        return math.log1p(p)
    def SimNeutronStarEOSEnergyDensityOfPressureGeometrized(self,p,eos):
        return 10*p
    def SimNeutronStarEOSEnergyDensityDerivOfPressureGeometrized(self,p,eos):
        return 10
    def SimNeutronStarEOSRestMassDensityOfPseudoEnthalpyGeometrized(self,h,eos):
        return 9*math.expm1(h)

class F132Tests(unittest.TestCase):
    def data(self):
        p=np.linspace(1,200,180)
        geom_m=BARYON_MASS_AVG_MEV*J_TO_MEV/FakeLal.C_SI**2*FakeLal.G_SI/FakeLal.C_SI**2
        return dict(p=p,e=10*p,h=np.log1p(p),n=10*p/geom_m,cs2=np.ones(p.size)/10,dloge_dlogp=np.ones(p.size))
    def test_seven_names_are_original_provenance(self):
        self.assertEqual(set(EOS_NAMES),{"APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2"})
    def test_source_grid_integrity(self):
        out=require_source_data(self.data())
        self.assertEqual(len(out["p"]),180)
        data=self.data();data["p"][4]=data["p"][3]
        with self.assertRaisesRegex(ValueError,"GRID"):
            require_source_data(data)
    def test_source_missing_n_rejected(self):
        data=self.data();data.pop("n")
        with self.assertRaisesRegex(ValueError,"KEY_MISSING:n"):
            require_source_data(data)
    def test_native_exact_rest_mass_differs_from_approx_not_silent_override(self):
        with TemporaryDirectory() as td:
            f=Path(td)/"APR4_EPP.npz"
            np.savez(f,**self.data())
            result,rows=measure_one("APR4_EPP",f,FakeLal(),FakeNative())
            self.assertEqual(result["native_valid_points"],180)
            self.assertEqual(result["native_failed_points"],0)
            self.assertAlmostEqual(result["n_native_over_jester_approx"]["median"],.9,places=11)
            self.assertEqual(result["native_cs2_superluminal_count"],0)
            self.assertEqual(result["source_npz_sha256"],sha(f))
            self.assertEqual(len(rows),180)
    def test_negative_source_cs2_is_preserved_and_counted_not_silenced(self):
        with TemporaryDirectory() as td:
            f=Path(td)/"WFF2.npz"
            data=self.data()
            data["cs2"][0]=-0.25
            data["cs2"][1]=0.0
            data["dloge_dlogp"][2]=-2.0
            np.savez(f,**data)
            result,rows=measure_one("WFF2",f,FakeLal(),FakeNative())
            self.assertEqual(result["jester_cs2_nonpositive_count"],2)
            self.assertEqual(result["jester_dloge_nonpositive_count"],1)
            self.assertEqual(rows[0]["cs2_jester"],-0.25)
            self.assertEqual(result["native_valid_points"],180)

    def test_one_negative_native_derivative_is_recorded_not_discarded(self):
        class OneNegativeNative(FakeNative):
            def SimNeutronStarEOSEnergyDensityDerivOfPressureGeometrized(self,p,eos):
                return -10.0 if abs(p-1.0)<1e-12 else 10.0
        with TemporaryDirectory() as td:
            f=Path(td)/"ENG.npz";np.savez(f,**self.data())
            result,rows=measure_one("ENG",f,FakeLal(),OneNegativeNative())
            self.assertEqual(result["native_failed_points"],0)
            self.assertEqual(result["native_cs2_nonpositive_count"],1)
            self.assertEqual(rows[0]["cs2_lal"],-0.1)

    def test_nonfinite_native_and_API_missing_fail_closed(self):
        class BrokenNative(FakeNative):
            def SimNeutronStarEOSRestMassDensityOfPseudoEnthalpyGeometrized(self,h,eos):
                return float('nan')
        with TemporaryDirectory() as td:
            f=Path(td)/"MS1.npz";np.savez(f,**self.data())
            with self.assertRaisesRegex(RuntimeError,"INSUFFICIENT_VALID_POINTS"):
                measure_one("MS1",f,FakeLal(),BrokenNative())
        with self.assertRaisesRegex(RuntimeError,"API_MISSING"):
            select_api(SimpleNamespace(),"SimNeutronStarEOSRestMassDensityOfPseudoEnthalpyGeometrized")
    def test_legacy_spelling_and_no_source_overwrite(self):
        legacy=SimpleNamespace(SimNeutronStarEOSRestMassDensityOfPseudoEnthalpyGeometerized=lambda h,eos:7)
        self.assertEqual(select_api(legacy,"SimNeutronStarEOSRestMassDensityOfPseudoEnthalpyGeometrized")(1,None),7)

if __name__=='__main__':unittest.main()