import hashlib,io,tarfile,tempfile,unittest
from pathlib import Path
import numpy as np
from full_salmi_mr_source_audit import audit,summarize, SOURCE_MEMBER,SOURCE_ARCHIVE

class FullSalmiMRTests(unittest.TestCase):
    def test_original_columns_mass_radius_and_quantiles(self):
        m=np.array([1.9,2.,2.1,2.2]);r=np.array([11.,12.,13.,14.])
        x=summarize(m,r,4)
        self.assertEqual(x['rows'],4)
        self.assertEqual(x['radius_tail_counts']['R>14.0km'],0)
        self.assertAlmostEqual(x['R_quantiles_km']['0.5'],12.5)
    def test_wrong_count_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'Unexpected'):
            summarize([2.,2.], [12.,13.],4)
    def test_nonfinite_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'Unexpected'):
            summarize([2.,float('nan')],[12.,13.],2)
    def make_tar(self,base,rows=4,name=SOURCE_MEMBER):
        p=base/SOURCE_ARCHIVE
        raw='\n'.join(f'{2+i*.01:.7f} {12+i*.01:.7f}' for i in range(rows)).encode()
        with tarfile.open(p,'w:gz') as t:
            inf=tarfile.TarInfo(name); inf.size=len(raw);t.addfile(inf,io.BytesIO(raw))
        h=hashlib.md5(p.read_bytes()).hexdigest()
        return p,h
    def test_hash_then_bounded_tar_member(self):
        with tempfile.TemporaryDirectory() as td:
            p,h=self.make_tar(Path(td))
            r=audit(p,expected_md5=h,expected_rows=4)
            self.assertEqual(r['rows'],4)
            self.assertEqual(r['original_member'],SOURCE_MEMBER)
    def test_wrong_archive_digest_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p,_=self.make_tar(Path(td))
            with self.assertRaisesRegex(ValueError,'MD5 mismatch'):
                audit(p,expected_md5='0'*32,expected_rows=4)
    def test_malicious_archive_member_not_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            p,h=self.make_tar(Path(td),name='../evildoer.txt')
            with self.assertRaises(KeyError):audit(p,expected_md5=h,expected_rows=4)
    def test_reject_missing_filename_even_identical_contents(self):
        with tempfile.TemporaryDirectory() as td:
            p,h=self.make_tar(Path(td))
            p2=p.with_name('psr_J0740+6620_with_3p6_Years_of_NICER_Data.tar.gz');p.rename(p2)
            with self.assertRaisesRegex(ValueError,'expected Salmi small'):
                audit(p2,expected_md5=h,expected_rows=4)

if __name__=='__main__':unittest.main()
