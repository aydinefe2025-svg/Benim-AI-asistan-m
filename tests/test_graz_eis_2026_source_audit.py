import unittest, io, zipfile, hashlib, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"/"battery_curve_audit"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import graz_eis_2026_source_audit as m

WORKBOOK='''<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="EIS" sheetId="1" r:id="rId1"/></sheets></workbook>'''
RELS='''<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>'''
SHEET='''<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Frequency</t></is></c><c r="B1" t="inlineStr"><is><t>Impedance</t></is></c></row><row r="2"><c r="A2"><v>1</v></c><c r="B2"><v>0.0012</v></c></row></sheetData></worksheet>'''

def make_zip(sheet=SHEET,missing=None,duplicate=False):
    files={'xl/workbook.xml':WORKBOOK,'xl/_rels/workbook.xml.rels':RELS,'xl/worksheets/sheet1.xml':sheet}
    with io.BytesIO() as b:
        with zipfile.ZipFile(b,'w',zipfile.ZIP_STORED) as z:
            for k,v in files.items():
                if k!=missing:z.writestr(k,v.encode())
            if duplicate:z.writestr('xl/workbook.xml',WORKBOOK)
        return b.getvalue()

class Original(unittest.TestCase):
    def get(self,raw):
        name='EIS_C02.xlsx'
        original=m.PINS[name];m.PINS[name]=hashlib.md5(raw).hexdigest()
        try:
            # fixture should be passed even though tiny; threshold is deliberately verified
            if len(raw)<5000:
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    parts=[(x.filename,z.read(x)) for x in z.infolist()]
                with io.BytesIO() as f:
                    with zipfile.ZipFile(f,'w',compression=zipfile.ZIP_STORED) as z:
                        for name2,data in parts:z.writestr(name2,data+b' '*(5000//len(parts)))
                    raw=f.getvalue()
                m.PINS[name]=hashlib.md5(raw).hexdigest()
            return m.inspect_original_workbook(raw,name,m.PINS[name])
        finally:m.PINS[name]=original
    def test_valid_fixture(self):
        r=self.get(make_zip())
        self.assertEqual(r['sheet_count'],1)
        self.assertEqual(r['numeric_source_cell_count'],2)
        self.assertEqual(r['sheets'][0]['source_row_count'],2)
        self.assertFalse(r.get('physical_release_allowed',False))
    def test_duplicate_part_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'unsafe OOXML member'):self.get(make_zip(duplicate=True))
    def test_missing_sheet_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'worksheet'):self.get(make_zip(missing='xl/worksheets/sheet1.xml'))
    def test_nonfinite_rejected(self):
        with self.assertRaisesRegex(ValueError,'nonfinite'):self.get(make_zip(SHEET.replace('0.0012','NaN')))
    def test_non_numeric_rejected(self):
        with self.assertRaisesRegex(ValueError,'invalid numeric'):self.get(make_zip(SHEET.replace('0.0012','mystery')))
    def test_wrong_pub_pin(self):
        raw=make_zip()
        with self.assertRaisesRegex(ValueError,'original published MD5'):m.inspect_original_workbook(raw,'EIS_C02.xlsx',m.PINS['EIS_C02.xlsx'])
    def test_wrong_file_rejected(self):
        with self.assertRaisesRegex(ValueError,'unexpected original'):m.inspect_original_workbook(make_zip(),'EIS_unknown.xlsx','aaa')
    def test_source_size_bound(self):
        raw=b'x'*110001
        with self.assertRaisesRegex(ValueError,'original published MD5'):m.inspect_original_workbook(raw,'EIS_C02.xlsx',m.PINS['EIS_C02.xlsx'])
if __name__=='__main__':unittest.main()