#!/usr/bin/env python3
"""Physical source numerical law verification, uses ORIGINAL verified immutable 1933 nodes."""
import os,sys,unittest,hashlib,json,math
from pathlib import Path
import numpy as np
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
F98=BASE.parent/'f98'
sys.path.insert(0,str(F98))
import f99_physical_firstlaw_source_no_go_derived_eos as f99
import f98_rns_source_interpolation_repair as f98
SRC=Path(os.getenv('F99_SOURCE_EOS',str(BASE/'F88_m_original.rns')))
EOS=Path(os.getenv('F99_DERIVED_EOS',str(BASE/'F99_DERIVED_1981_node_causal_cold_affine_EOS.rns')))
REC=Path(os.getenv('F99_RECEIPT',str(BASE/'F99_1933_exact_source_no_go_and_1981_model_receipt_20261122.json')))
CENTERS=[1533320557069400.,1585592848787675.,1637865140505950.,1690137432224225.,1742409723942500.,1785969967041062.2,1803394064280487.2,1812106112900200.,1820860880772815.2]
class AuthenticSourceNumericalPhysics(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.a=np.loadtxt(SRC,skiprows=1)
  cls.d=np.loadtxt(EOS,skiprows=1)
  cls.r=json.loads(REC.read_text())
 def test_01_original_source_sha_unchanged(self):
  self.assertEqual(hashlib.sha256(SRC.read_bytes()).hexdigest(),f99.SHA_SOURCE)
  self.assertEqual(self.a.shape,(1933,4))
 def test_02_no_go_three_immutable_original_thermodynamic_causal_intervals(self):
  no=f99.no_go(self.a)
  self.assertEqual([e['source_interval_0based'] for e in no['exact_endpoints_no_go_intervals']],[1831,1907,1908])
  for x in no['exact_endpoints_no_go_intervals']:
   self.assertGreater(abs(x['signed_log_ratio_excess']),1e-6)
 def test_03_derived_model_original_kept_read_only_separate_sha(self):
  self.assertEqual(hashlib.sha256(EOS.read_bytes()).hexdigest(),self.r['derived_model']['output_SHA256'])
  self.assertEqual(self.d.shape,(1981,4))
  self.assertNotEqual(self.r['derived_model']['output_SHA256'],f99.SHA_SOURCE)
  self.assertFalse(self.r['derived_model']['original_source_h_n_preserved'])
 def test_04_causal_in_analytic_reference_all_source_pressures(self):
  v=np.diff(self.d[:,1])/(np.diff(self.d[:,0])*f99.C*f99.C)
  self.assertGreater(float(v.min()),0)
  self.assertLessEqual(float(v.max()),1.0)
 def test_05_exact_first_law_baryon_knots_from_integrated_p_e(self):
  e=self.d[:,0]*f99.C*f99.C;p=self.d[:,1];n=self.d[:,3]
  err=[abs(math.log(n[i+1]/n[i])-f99.log_integral(e[i],p[i],e[i+1],p[i+1])) for i in range(len(e)-1)]
  self.assertLess(max(err),1e-11)
 def test_06_exact_first_law_enthalpy_knots_from_integrated_p_e(self):
  e=self.d[:,0]*f99.C*f99.C;p=self.d[:,1];h=self.d[:,2]
  err=[]
  for i in range(len(e)-1):
   slope=(p[i+1]-p[i])/(e[i+1]-e[i]);target=slope*f99.log_integral(e[i],p[i],e[i+1],p[i+1])
   err.append(abs((h[i+1]-h[i])/(f99.C*f99.C)-target))
  self.assertLess(max(err),1e-11)
 def test_07_independent_source_C_fourpoint_Lagrange_causality_all_nine(self):
  got=f98.audit_grid_fast(self.d,CENTERS)
  self.assertEqual(len(got),9)
  self.assertTrue(all(x['passes_local_positive_causal_interpolated_P_e'] for x in got))
  self.assertLess(max(x['max_cs2'] for x in got),1)
 def test_08_source_derived_not_falsely_orig_seven_EOS(self):
  self.assertEqual(self.r['source_native_seven_EOS_Bayes'],'NOT_RUN')
  self.assertEqual(self.r['rotating_axisymmetric_dynamical_eigenmodes'],'NOT_RUN')
  self.assertIn('DISTINCT_DERIVED',self.r['derived_model']['status'])
 def test_09_original_finite_precision_not_claimed_measurement_impossibility(self):
  self.assertIn('rounding',self.r['original_source_no_go']['claim'])
 def test_10_no_silent_source_epsilon_pressure_change_before_causal_boundary(self):
  for i in [0,20,1830,1831,1907,1908,1909]:
   row=self.a[i];found=np.where(self.d[:,0]==row[0])[0]
   self.assertEqual(len(found),1)
   self.assertEqual(self.d[found[0],0],row[0]);self.assertEqual(self.d[found[0],1],row[1])
if __name__=='__main__':unittest.main()
