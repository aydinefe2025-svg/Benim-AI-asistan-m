"""F54 mock mesh-comparison tests; not a C-RNS numerical replication."""
import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import f54_wff1_constant_J_two_mesh as f54

def rows():
    r=[]
    for e in f54.MATCHED_E15:
        m=2.12-.05*(e-2.9)**2
        r.append({'ec_e15':e,'status':'MATCHED_BOTH_REAL_C_STARS',
                  'fine':{'mass_msun':m,'radius_eq_km':9.57},
                  'coarse':{'mass_msun':m-.0003,'radius_eq_km':9.59,
                            'relative_J_residual':1e-9},
                  'coarse_minus_fine_mass_Msun':-.0003,
                  'coarse_minus_fine_radius_km':.02})
    return r

class TwoMeshTests(unittest.TestCase):
    def test_genuine_bracketed_mesh_comparison_diagnostic(self):
        result=f54.summarize_pairs(rows())
        self.assertTrue(result['status'].startswith('PASS_'))
        self.assertTrue(result['coarse_peak_neighbor_bracket'])
        self.assertEqual(result['global_stability'],'NOT_ESTABLISHED')
        self.assertEqual(result['EOS_table_knot_convergence'],'NOT_TESTED')

    def test_missing_direct_coarse_star_fails(self):
        r=rows();r[3]['status']='COARSE_MESH_DIRECT_C_STAR_FAILED'
        self.assertEqual(f54.summarize_pairs(r)['status'],'INCOMPLETE_MATCHED_MESH_STARS')

    def test_insufficient_mesh_pairs_fails(self):
        self.assertEqual(f54.summarize_pairs(rows()[:-1])['status'],
                         'INCOMPLETE_MATCHED_MESH_STARS')

    def test_radius_difference_gate(self):
        r=rows();r[2]['coarse_minus_fine_radius_km']=.15
        self.assertEqual(f54.summarize_pairs(r)['status'],
                         'NOT_ACCEPTED_MESH_DIFFERENCE_OR_TURNOVER')

    def test_mass_difference_gate(self):
        r=rows();r[2]['coarse_minus_fine_mass_Msun']=.004
        self.assertEqual(f54.summarize_pairs(r)['status'],
                         'NOT_ACCEPTED_MESH_DIFFERENCE_OR_TURNOVER')

    def test_J_residual_gate(self):
        r=rows();r[3]['coarse']['relative_J_residual']=1e-3
        self.assertEqual(f54.summarize_pairs(r)['status'],
                         'NOT_ACCEPTED_MESH_DIFFERENCE_OR_TURNOVER')

    def test_missing_two_sided_turnover_fails(self):
        r=rows()
        for i,s in enumerate(r):
            s['coarse']['mass_msun']=i*.01+2.05
        self.assertEqual(f54.summarize_pairs(r)['status'],
                         'NOT_ACCEPTED_MESH_DIFFERENCE_OR_TURNOVER')

if __name__=='__main__':unittest.main()
