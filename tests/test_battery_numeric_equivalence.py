"""Synthetic numeric formatting-equivalence regression; not real customer measurements."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'research'/'battery_curve_audit'))
import numeric_equivalence_guard as guard
import customer_preflight as product


class NumericEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        hdr = 'Timestamp [h],Voltage [V]\n'
        sources = {
            'A':'0,3.400\n1.0,3.300\n2.000,3.20\n',
            'B':'+0e0,3.4e0\n1e0,3.3\n2,3.2000\n',
            'C':'0,4\n1,3.9\n2,3.8\n',
            'D':'0,4.1\n1,4\n2,3.9\n',
        }
        for k,v in sources.items():
            (self.root/(k+'.csv')).write_text(hdr+v,encoding='utf-8')
        self.manifest={'schema':'cano.battery.customer-files.v1',
                       'files':[{'path':k+'.csv','cell':k,'mode':'dchg'} for k in sources]}

    def test_lexically_different_same_numbers_grouped(self):
        baseline = product.audit_customer(self.manifest,self.root)
        self.assertEqual(baseline['unique_curve_count'],4)
        result = guard.build_numeric_audit(self.manifest,self.root)
        self.assertEqual(result['unique_curve_count'],3)
        self.assertEqual(result['original_text_audit_sha256'], guard.digest(baseline))
        self.assertEqual({c['cell'] for c in result['duplicate_groups'][0]}, {'A','B'})
        self.assertEqual(result['review_status'], 'REVIEW_REQUIRED')
        self.assertEqual(len(result['all_curve_identity']),4)
        for c in result['all_curve_identity']:
            self.assertIn('raw_trace_sha256', c)
            self.assertNotIn('time_voltage_pairs', c)

    def test_decimal_normalization_not_rounded_float_tolerance(self):
        self.assertEqual(guard.numeric_pair_hash([('0','-0'),('1.00','3.4000')]),
                         guard.numeric_pair_hash([('-0e0','+0.0'),('1e0','34e-1')]))
        self.assertNotEqual(guard.numeric_pair_hash([('0','0'),('1','3.4000000000000001')]),
                            guard.numeric_pair_hash([('0','0'),('1','3.4')]))

    def test_one_digit_change_is_not_masked(self):
        (self.root/'B.csv').write_text('Timestamp [h],Voltage [V]\n0,3.4\n1,3.3000000000000001\n2,3.2\n',encoding='utf-8')
        result=guard.build_numeric_audit(self.manifest,self.root)
        self.assertEqual(result['unique_curve_count'],4)
        self.assertEqual(result['duplicate_groups'],[])
        self.assertEqual(result['review_status'],'SCREEN_ONLY_NO_NUMERIC_CROSS_CELL_DUPLICATES')

    def test_original_trace_and_sources_are_preserved(self):
        base=product.audit_customer(self.manifest,self.root)
        numeric=guard.build_numeric_audit(self.manifest,self.root)
        for a,b in zip(base['all_curve_identity'],numeric['all_curve_identity']):
            self.assertEqual(a['trace_sha256'],b['raw_trace_sha256'])
            self.assertEqual(a['source_sha256'],b['source_sha256'])
            self.assertEqual(a['cell'],b['cell'])
            self.assertEqual(a['run'],b['run'])
        self.assertEqual(numeric['measured_time_voltage_pairs'],base['measured_time_voltage_pairs'])


if __name__=='__main__': unittest.main(verbosity=2)
