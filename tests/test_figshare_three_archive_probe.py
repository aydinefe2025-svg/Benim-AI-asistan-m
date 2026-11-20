"""Synthetic three-archive source security checks. Do not substitute tests for real cells."""
import io
from hashlib import md5
from zipfile import ZipFile, ZIP_DEFLATED
import unittest
from research.battery_curve_audit.figshare_three_archive_probe import (
    PINNED, inspect_zip, validate_source_meta)


def fakezip(name='TP_k01_05_01_ET_T23.csv',meta=True):
    buf=io.BytesIO()
    with ZipFile(buf,'w',compression=ZIP_DEFLATED) as z:
        z.writestr(name,'time,c_vol,c_cur\n0,4.2,0\n1,4.1,-1\n')
        if meta:z.writestr('TP_k01_05_01_ET_T23_meta.txt','Laboratory: DEMO\n')
    raw=buf.getvalue()
    return raw,{'id':1,'name':'example.zip','size':len(raw),'md5':md5(raw).hexdigest()}


class SourceArchiveGuards(unittest.TestCase):
    def test_original_small_csv_header_and_meta_reported_not_certified(self):
        raw,p=fakezip();d=inspect_zip(raw,p)
        self.assertTrue(d['zip_crc_passed'])
        self.assertEqual(d['csv_count'],1)
        self.assertEqual(d['metadata_txt_count'],1)
        self.assertTrue(d['contains_csv_and_meta'])
        self.assertTrue(d['csv_header_examples'][0]['time_alias_present'])
        self.assertTrue(d['csv_header_examples'][0]['voltage_alias_present'])
    def test_missing_meta_does_not_falsely_bind_physical_cell(self):
        raw,p=fakezip(meta=False);d=inspect_zip(raw,p)
        self.assertFalse(d['contains_csv_and_meta'])
    def test_publisher_md5_changed_rejected(self):
        raw,p=fakezip();p['md5']='0'*32
        with self.assertRaisesRegex(ValueError,'MD5'):inspect_zip(raw,p)
    def test_unsafe_parent_zip_path_rejected(self):
        raw,p=fakezip('../escape.csv')
        with self.assertRaisesRegex(ValueError,'unsafe'):inspect_zip(raw,p)
    def test_duplicated_zip_path_rejected(self):
        buf=io.BytesIO()
        with ZipFile(buf,'w') as z:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                z.writestr('same.csv','time,c_vol\n0,1\n')
                z.writestr('same.csv','time,c_vol\n0,1\n')
        raw=buf.getvalue();p={'size':len(raw),'md5':md5(raw).hexdigest(),'id':9,'name':'fake.zip'}
        with self.assertRaisesRegex(ValueError,'unsafe'):inspect_zip(raw,p)
    def test_stated_source_identity_must_match_explicit_pins(self):
        files=[{'id':fid,'name':name,'size':size,'computed_md5':digest}
               for fid,name,size,digest in PINNED]
        meta={'id':25975315,'doi':'10.6084/m9.figshare.25975315.v1',
              'license':{'name':'CC BY 4.0','url':'https://creativecommons.org/licenses/by/4.0/'},
              'files':files}
        self.assertEqual(len(validate_source_meta(meta)),3)
        meta['files'][0]['size']+=1
        with self.assertRaisesRegex(ValueError,'ID/name/size'):validate_source_meta(meta)

if __name__=='__main__':unittest.main()