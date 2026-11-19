import copy
import hashlib
import json
import tempfile
from pathlib import Path
import unittest
import saved_lineage_proof as p

SOURCE = Path(__file__).parent / 'saved_lineage_receipts'

class ProofTests(unittest.TestCase):
    def test_archival_exact_real_sources(self):
        x=p.verify_saved_source_lineage(SOURCE)
        self.assertTrue(x['source_prior_run_match'].startswith('SUPPORTED'))
        self.assertFalse(x['original_tar_read_now'])
        self.assertEqual(x['resume_final_engine_version'],'UNRESOLVED')
        self.assertEqual(x['seven_original_eos_bayes'],'NOT_RUN')
        self.assertLess(x['max_abs_moment_residual'],2e-12)
    def mutate(self, name, transform):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)
            for n in (p.F31_NAME,p.F32_NAME):
                (dest/n).write_bytes((SOURCE/n).read_bytes())
            path=dest/name
            obj=json.loads(path.read_bytes()); transform(obj)
            path.write_text(json.dumps(obj),encoding='utf-8')
            # Source digest change must be rejected even if edited fields look good.
            with self.assertRaisesRegex(p.SavedLineageError,'receipt hash mismatch'):
                p.verify_saved_source_lineage(dest)
    def test_reject_mutated_f31_receipt(self):
        self.mutate(p.F31_NAME,lambda obj:obj['original_archive_member_scan']['members']['prior'].update(sha256='0'*64))
    def test_reject_mutated_f32_receipt(self):
        self.mutate(p.F32_NAME,lambda obj:obj['weighted_posterior_moments'].update(mean_mass_msun=9.0))
    def test_reject_missing_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/p.F31_NAME).write_bytes((SOURCE/p.F31_NAME).read_bytes())
            with self.assertRaisesRegex(p.SavedLineageError,'missing archived'):
                p.verify_saved_source_lineage(d)
    def test_reject_fabricated_pin_bypass_attempt(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)
            for n in (p.F31_NAME,p.F32_NAME): (dest/n).write_bytes((SOURCE/n).read_bytes())
            old=p.F31_SHA
            try:
                p.F31_SHA='0'*64
                with self.assertRaisesRegex(p.SavedLineageError,'receipt hash mismatch'):p.verify_saved_source_lineage(dest)
            finally:p.F31_SHA=old
    def test_reject_source_claim_in_F31(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)
            for n in (p.F31_NAME,p.F32_NAME): (dest/n).write_bytes((SOURCE/n).read_bytes())
            obj=json.loads((dest/p.F31_NAME).read_text())
            obj['original_archive_member_scan']['status']='FAIL'
            raw=json.dumps(obj).encode();(dest/p.F31_NAME).write_bytes(raw)
            old=p.F31_SHA
            try:
                p.F31_SHA=hashlib.sha256(raw).hexdigest()
                with self.assertRaisesRegex(p.SavedLineageError,'original byte scan'):p.verify_saved_source_lineage(dest)
            finally:p.F31_SHA=old
    def test_reject_moment_claim_even_when_json_rehashed(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)
            for n in (p.F31_NAME,p.F32_NAME): (dest/n).write_bytes((SOURCE/n).read_bytes())
            obj=json.loads((dest/p.F32_NAME).read_text());obj['weighted_posterior_moments']['std_radius_km']=7.0
            raw=json.dumps(obj).encode();(dest/p.F32_NAME).write_bytes(raw)
            old=p.F32_SHA
            try:
                p.F32_SHA=hashlib.sha256(raw).hexdigest()
                with self.assertRaisesRegex(p.SavedLineageError,'std_radius_km mismatch'):p.verify_saved_source_lineage(dest)
            finally:p.F32_SHA=old
    def test_reject_ambiguity_when_extra_matching_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)
            for n in (p.F31_NAME,p.F32_NAME): (dest/n).write_bytes((SOURCE/n).read_bytes())
            obj=json.loads((dest/p.F32_NAME).read_text());obj['comparison_candidates'][0]['delta_mass_mean_vs_published_weighted']=0
            obj['comparison_candidates'][0]['delta_radius_mean_km_vs_published_weighted']=0
            raw=json.dumps(obj).encode();(dest/p.F32_NAME).write_bytes(raw)
            old=p.F32_SHA
            try:
                p.F32_SHA=hashlib.sha256(raw).hexdigest()
                with self.assertRaisesRegex(p.SavedLineageError,'unique identity'):p.verify_saved_source_lineage(dest)
            finally:p.F32_SHA=old

if __name__=='__main__':unittest.main()
