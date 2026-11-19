"""F72 strict source and mesh/EOS two-axis validation tests."""
import copy
import hashlib
import json
import math
import os
import pathlib
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
import sys
sys.path.insert(0,str(HERE))
from f72_eos_grid_separation import (generate_tables, compare_eos_spacetime, SOURCE_SHA,
    SHA_196, SOURCE_SHA, MODEL, TARGET_HZ, TARGETS)

F67 = pathlib.Path(os.environ.get('F72_F67_SOURCE','/mnt/data/f72_inputs/F67_MPA1_PCHIP_COLD_relative_thermo_20261119.dat'))
F68 = pathlib.Path(os.environ.get('F72_F68_SOURCE','/mnt/data/f72_inputs/F68_ALT196_identical_RNS_source_EOS_20261119.rns'))


def fake(grid, eos_points, eos_sha, baseline_m=12.5346):
    return {'grid':grid,'eos_points':eos_points,'eos_sha256':eos_sha,'source_parent_SHA256':SOURCE_SHA,'source_model':MODEL,
      'not_original_MPA1':True,'not_F69_Fe56':True,'seven_original_EOS_Bayes':'NOT_RUN',
      'stars':{k:{'direct_C':{'mass_msun':float(k),'spin_hz_reported':TARGET_HZ,
      'radius_eq_km':baseline_m+.001*math.log(eos_points/196)+.00001*(401-int(grid.split('x')[0])),
      'solver_mode':'RNS_C_AXIS_RATIO_DIRECT'}} for k in TARGETS}}

class F72Tests(unittest.TestCase):
    def test_exact_F68_source_baseline_and_ulp_diagnostics(self):
        with tempfile.TemporaryDirectory() as d:
            o=generate_tables(F67,d,points=(196,392,784),reference_196=F68)
            self.assertEqual(o[196]['sha256'],SHA_196)
            self.assertEqual(pathlib.Path(o[196]['path']).read_bytes(),F68.read_bytes())
            self.assertLess(o[196]['regenerated_196_max_relative_ulp_difference'],1e-14)
            for n in (392,784):
                self.assertEqual(o[n]['rows'],n)
                self.assertNotEqual(o[n]['sha256'],SHA_196)

    def test_source_sha_enforced(self):
        with tempfile.TemporaryDirectory() as d:
            bad=pathlib.Path(d)/'bad.dat';bad.write_bytes(F67.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'SOURCE_SHA'):generate_tables(bad,d,reference_196=F68)

    def test_overflow_guard(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'EOS_POINTS_UNSAFE'):generate_tables(F67,d,(2001,),reference_196=F68)

    def test_comparison_rejects_faked_physics(self):
        with tempfile.TemporaryDirectory() as d:
            o=generate_tables(F67,d,reference_196=F68)
            records={f'{g}_{n}':fake(g,n,o[n]['sha256']) for g in ('301x601','401x801') for n in (196,392,784)}
            raw={f'{g}_{n}':o[n]['path'] for g in ('301x601','401x801') for n in (392,784)}
            ans=compare_eos_spacetime(records,o,raw)
            self.assertEqual(len(ans['separately_computed_stars']),2)
            self.assertEqual(ans['total_separate_direct_stars'],12)
            self.assertEqual(ans['scientific_status'],'EOS_AND_GRID_AXIS_NUMERICAL_DIAGNOSTIC_ONLY')
            broken=copy.deepcopy(records);broken['401x801_784']['stars']['2.073']['direct_C']['solver_mode']='INTERPOLATED'
            with self.assertRaisesRegex(ValueError,'DIRECT_C'):compare_eos_spacetime(broken,o,raw)

    def test_cross_platform_one_ulp_sha_change_accepts_only_if_table_verified(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            o=generate_tables(F67,root,reference_196=F68)
            rs={f'{g}_{n}':fake(g,n,o[n]['sha256']) for g in ('301x601','401x801') for n in (196,392,784)}
            raw={f'{g}_{n}':o[n]['path'] for g in ('301x601','401x801') for n in (392,784)}
            source=pathlib.Path(o[392]['path'])
            modified=root/'one_ulp_392.rns'
            lines=source.read_text().splitlines()
            cells=lines[1].split()
            old=cells[1]
            last_digit=int(old.split('e')[0][-1]);replaced=str((last_digit+1)%10)
            cells[1]=old.split('e')[0][:-1]+replaced+'e'+old.split('e')[1]
            lines[1]=' '.join(cells)
            modified.write_text('\n'.join(lines)+'\n')
            self.assertNotEqual(hashlib.sha256(modified.read_bytes()).hexdigest(),o[392]['sha256'])
            rs['301x601_392']['eos_sha256']=hashlib.sha256(modified.read_bytes()).hexdigest()
            raw['301x601_392']=str(modified)
            ok=compare_eos_spacetime(rs,o,raw)
            self.assertFalse(ok['per_grid_original_C_EOS_file_source_validation']['301x601_392']['exact_table_byte_identity'])
            # Manipulating actual raw C data cannot be hidden by matching its hash.
            cells=lines[1].split();cells[1]='%.15e'%(float(cells[1])*1.02)
            lines[1]=' '.join(cells);modified.write_text('\n'.join(lines)+'\n')
            rs['301x601_392']['eos_sha256']=hashlib.sha256(modified.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'NON_EQUIVALENT'):
                compare_eos_spacetime(rs,o,raw)

    def test_comparison_rejects_spin_and_mass_failures(self):
        with tempfile.TemporaryDirectory() as d:
            o=generate_tables(F67,d,reference_196=F68)
            rs={f'{g}_{n}':fake(g,n,o[n]['sha256']) for g in ('301x601','401x801') for n in (196,392,784)}
            raw={f'{g}_{n}':o[n]['path'] for g in ('301x601','401x801') for n in (392,784)}
            rs['301x601_392']['stars']['2.250']['direct_C']['spin_hz_reported']+=.1
            with self.assertRaisesRegex(ValueError,'MASS_OR_SPIN'):compare_eos_spacetime(rs,o,raw)
            rs['301x601_392']['stars']['2.250']['direct_C']['spin_hz_reported']=TARGET_HZ
            rs['301x601_392']['stars']['2.250']['direct_C']['mass_msun']+=.005
            with self.assertRaisesRegex(ValueError,'MASS_OR_SPIN'):compare_eos_spacetime(rs,o,raw)

    def test_no_original_physics_or_bayes_relabel(self):
        with tempfile.TemporaryDirectory() as d:
            o=generate_tables(F67,d,reference_196=F68)
            rs={f'{g}_{n}':fake(g,n,o[n]['sha256']) for g in ('301x601','401x801') for n in (196,392,784)}
            raw={f'{g}_{n}':o[n]['path'] for g in ('301x601','401x801') for n in (392,784)}
            rs['301x601_196']['seven_original_EOS_Bayes']='COMPLETE'
            with self.assertRaisesRegex(ValueError,'ORIGINAL_OR_BAYES'):compare_eos_spacetime(rs,o,raw)

if __name__=='__main__':unittest.main()
