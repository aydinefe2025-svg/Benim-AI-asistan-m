"""F70 fail-closed tests (source archive values + adversarial mutations)."""
import copy, json, pathlib, sys, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from f70_mesh_spin_crosswalk import crosswalk, run, sha256, F68_SHA, F69_SHA
F68=ROOT / 'inputs' / 'F68_science_summary_20261119.json'
F69=ROOT / 'inputs' / 'F69_Fe56_conditional_surface_static_TOV_and_baryon_20261119.json'

class ScientificAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=json.loads(F68.read_text());cls.b=json.loads(F69.read_text())
    def test_real_input_sources_are_exact(self):
        self.assertEqual(sha256(F68),F68_SHA);self.assertEqual(sha256(F69),F69_SHA)
    def test_crosswalk_observations(self):
        r=crosswalk(self.a,self.b)
        self.assertAlmostEqual(r['rows'][-1]['fine_minus_coarse_frequency_hz'],-0.288126252,places=8)
        self.assertAlmostEqual(r['max_abs_static_two_grid_radius_delta_m'],3.681111,places=5)
        self.assertAlmostEqual(r['max_abs_rotating_two_grid_radius_delta_m_NOT_MESH_ONLY'],1.180454,places=5)
        self.assertLess(r['max_abs_F69_vs_F68_independent_TOV_radius_delta_m'],0.001)
        self.assertFalse(r['F68_two_grid_rotating_pure_mesh_error_certified'])
        self.assertEqual(r['number_of_mass_roots_with_two_spacetime_grids'],2)
    def test_bad_F68_identity_fails(self):
        a=copy.deepcopy(self.a);a['model']='MPA1_ORIGINAL'
        with self.assertRaisesRegex(ValueError,'MODEL_IDENTITY'):crosswalk(a,self.b)
    def test_bad_thermodynamic_parent_fails(self):
        b=copy.deepcopy(self.b);b['parent_F67_source_SHA256']='unrelated'
        with self.assertRaisesRegex(ValueError,'PARENT_OR_RNS'):crosswalk(self.a,b)
    def test_false_Bayes_acceptance_fails(self):
        b=copy.deepcopy(self.b);b['seven_original_EOS_Bayes']='COMPLETE'
        with self.assertRaisesRegex(ValueError,'FALSE_FULL'):crosswalk(self.a,b)
    def test_false_physical_acceptance_fails(self):
        b=copy.deepcopy(self.b);b['whole_original_seven_EOS_physically_accepted']='PASS'
        with self.assertRaisesRegex(ValueError,'FALSE_PHYSICAL'):crosswalk(self.a,b)
    def test_masses_must_match(self):
        b=copy.deepcopy(self.b);b['target_static_GR']['2.250']['rm']['M_msun_to_match']=2.21
        with self.assertRaisesRegex(ValueError,'MG_MISMATCH'):crosswalk(self.a,b)
    def test_exact_source_checksum_fails_on_byte_change(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'bad.json';q=pathlib.Path(d)/'result.json'
            p.write_bytes(F68.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'EXACT_SOURCE_FILE_SHA'):run(p,F69,q)
    def test_reproducible_clean_result(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'result.json';r=run(F68,F69,p)
            self.assertEqual(json.loads(p.read_text()),r)
            self.assertEqual(r['new_RNS_root_at_matched_frequency'],'NOT_RUN')
if __name__=='__main__':unittest.main()