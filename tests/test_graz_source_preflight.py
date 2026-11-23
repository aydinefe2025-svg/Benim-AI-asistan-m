import hashlib, io, unittest, zipfile
from research.battery_curve_audit import graz_source_preflight as m

class TestGrazSourcePreflight(unittest.TestCase):
    @staticmethod
    def archive(files=None):
        files = files or {'cell_02/log_02.csv':'Time;Current\n0;1\n1;1\n',
                          'cell_02/SP_02.csv':'Time;Thickness\n0;1\n',
                          'cell_03/log_03.csv':'Time;Current\n0;2\n',
                          'cell_03/SP_03.csv':'Time;Thickness\n0;3\n'}
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
            for path,txt in files.items():z.writestr(path,txt)
        return b.getvalue()
    def test_cell_two_three_distinct_inventory_not_phase_certification(self):
        b=self.archive(); old=m.OFFICIAL_MD5
        try:
            m.OFFICIAL_MD5=hashlib.md5(b).hexdigest()
            r=m.inspect_archive(b,len(b),m.OFFICIAL_MD5)
        finally:m.OFFICIAL_MD5=old
        self.assertEqual(r['cells']['02']['source_members'],2)
        self.assertEqual(r['cells']['03']['source_members'],2)
        self.assertTrue(r['zip_crc_verified'])
        self.assertIsNone(r['measured_cell_to_cell_mismatch_rate'])
        self.assertFalse(r['experiment_phase_join_verified'])
    def test_md5_fail_closed(self):
        b=self.archive()
        with self.assertRaisesRegex(ValueError,'MD5'):
            m.inspect_archive(b,len(b),m.OFFICIAL_MD5)
    def test_byte_count_fail_closed(self):
        b=self.archive()
        with self.assertRaisesRegex(ValueError,'byte count'):
            m.inspect_archive(b,len(b)+1)
    def test_path_traversal_fail_closed(self):
        b=self.archive({'../escape.csv':'bad'})
        old=m.OFFICIAL_MD5
        try:
            m.OFFICIAL_MD5=hashlib.md5(b).hexdigest()
            with self.assertRaisesRegex(ValueError,'unsafe'):
                m.inspect_archive(b,len(b),m.OFFICIAL_MD5)
        finally: m.OFFICIAL_MD5=old
    def test_no_false_id_from_date(self):
        self.assertIsNone(m.explicit_cell_in_path('2026-03-02/log.csv'))
        self.assertEqual(m.explicit_cell_in_path('specimen03/log.csv'),'03')
        self.assertIsNone(m.explicit_cell_in_path('cell02/cell03/log.csv'))
    def test_static_not_impact(self):
        self.assertEqual(m.CELL_PRELOAD_KN['02'],1.5)
        self.assertEqual(m.CELL_PRELOAD_KN['03'],3)

if __name__ == '__main__':unittest.main()