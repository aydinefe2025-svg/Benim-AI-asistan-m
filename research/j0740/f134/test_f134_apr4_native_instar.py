import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import f134_apr4_native_instar as f


class FakeLAL:
    @staticmethod
    def SimNeutronStarEOSByName(name):
        assert name == "APR4_EPP"
        return name

    @staticmethod
    def SimNeutronStarEOSEnergyDensityOfPressureGeometrized(p, eos):
        return 10*p

    @staticmethod
    def SimNeutronStarEOSEnergyDensityDerivOfPressureGeometrized(p, eos):
        return 2.0


class HiddenBad(FakeLAL):
    @staticmethod
    def SimNeutronStarEOSEnergyDensityDerivOfPressureGeometrized(p, eos):
        return 0.5 if 1.8e-10 < p < 1.9e-10 else 2.0


class LegacySpelling:
    SimNeutronStarEOSByName = FakeLAL.SimNeutronStarEOSByName
    SimNeutronStarEOSEnergyDensityOfPressureGeometerized = FakeLAL.SimNeutronStarEOSEnergyDensityOfPressureGeometrized
    SimNeutronStarEOSEnergyDensityDerivOfPressureGeometerized = FakeLAL.SimNeutronStarEOSEnergyDensityDerivOfPressureGeometrized


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/"APR4_EPP.npz"
        p = np.geomspace(1e-17, 1e-9, 801)
        np.savez(self.path,p=p,e=10*p)
        self.sha = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_causal_and_pinned(self):
        with patch.object(f,"SOURCE_SHA",self.sha):
            result,rows=f.audit(self.path,FakeLAL)
        self.assertEqual(result["native_noncausal_sample_count"],0)
        self.assertEqual(result["native_calls"],len(rows))
        self.assertEqual(result["min_cs2"],0.5)
        self.assertGreater(len(rows),10000)

    def test_between_nodes_failure_is_detected(self):
        with patch.object(f,"SOURCE_SHA",self.sha):
            result,_=f.audit(self.path,HiddenBad,65)
        self.assertGreater(result["native_noncausal_sample_count"],0)
        self.assertGreater(result["max_cs2"],1)

    def test_tampered_source_rejected(self):
        with self.assertRaisesRegex(ValueError,"SHA_MISMATCH"):
            f.audit(self.path,FakeLAL)

    def test_lal_legacy_api_spelling(self):
        with patch.object(f,"SOURCE_SHA",self.sha):
            result,_=f.audit(self.path,LegacySpelling)
        self.assertEqual(result["native_noncausal_sample_count"],0)


if __name__ == "__main__":
    unittest.main()
