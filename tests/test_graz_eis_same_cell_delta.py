"""Synthetic adversarial tests; no claim fake fixtures are publisher measurements."""
import hashlib,io,sys,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'/'battery_curve_audit'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import graz_eis_2026_source_audit as audit
# Import as a full package when running in GitHub, and local fallback when creating fixtures.
try:from research.battery_curve_audit import graz_eis_2026_same_cell_delta as m
except ModuleNotFoundError:
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    import graz_eis_2026_same_cell_delta as m

W='''<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{}</sheets></workbook>'''
R='''<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{}</Relationships>'''
N='http://schemas.openxmlformats.org/spreadsheetml/2006/main'

def make_source(modified='',mismatch=False):
    sheets=[];rels=[];items=[]
    for k,label in enumerate(m.LEVELS,1):
        sheets.append(f'<sheet name="{label}" sheetId="{k}" r:id="rId{k}"/>')
        rels.append(f'<Relationship Id="rId{k}" Target="worksheets/sheet{k}.xml"/>')
        rows=['<row r="1"><c r="A1" t="inlineStr"><is><t>Frequency\\Hz</t></is></c><c r="B1" t="inlineStr"><is><t>impedance\\Ohm</t></is></c><c r="C1" t="inlineStr"><is><t>Phase\\deg</t></is></c></row>']
        for j in range(2,103):
            hz=100000*(.9**(j-2))
            if mismatch and k==5 and j==10:hz*=1.01
            imp=.01*(1+.01*(k-1))
            if modified=='nan' and k==3 and j==8: imp=float('nan')
            rows.append(f'<row r="{j}"><c r="A{j}"><v>{hz}</v></c><c r="B{j}"><v>{imp}</v></c><c r="C{j}"><v>50</v></c></row>')
        items.append((f'xl/worksheets/sheet{k}.xml',f'<worksheet xmlns="{N}"><sheetData>{"".join(rows)}</sheetData></worksheet>'))
    with io.BytesIO() as buf:
        with zipfile.ZipFile(buf,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('xl/workbook.xml',W.format(''.join(sheets)))
            z.writestr('xl/_rels/workbook.xml.rels',R.format(''.join(rels)))
            for n,v in items:z.writestr(n,v)
        return buf.getvalue()

audit=m.audit

class Tests(unittest.TestCase):
    def test_baseline_and_stage_95(self):
        raw=make_source()
        self.assertEqual(len(raw)>5000,True)
        name='EIS_C02.xlsx';original=audit.PINS[name];audit.PINS[name]=hashlib.md5(raw).hexdigest()
        try:r=m.analyze_same_source(raw,name,audit.PINS[name])
        finally:audit.PINS[name]=original
        self.assertEqual(r['per_stage_source_measurement_count'],101)
        self.assertEqual(len(r['stages']),5)
        self.assertAlmostEqual(r['stages'][0]['median_impedance_magnitude_change_pct'],0)
        self.assertAlmostEqual(r['stages'][-1]['median_impedance_magnitude_change_pct'],4)
        self.assertEqual(r['stages'][-1]['positive_frequency_point_count'],101)
        self.assertEqual(len(r['stages'][-1]['sampled_frequencies']),2)
    def test_wrong_original_grid_fails(self):
        with self.assertRaisesRegex(ValueError,'different frequency grid'):
            m.tables_from_original(make_source(mismatch=True))
    def test_nonfinite_source_fails(self):
        with self.assertRaisesRegex(ValueError,'nonfinite'):
            m.tables_from_original(make_source(modified='nan'))
    def test_missing_level_fails(self):
        raw=make_source()
        # The source fixture is explicit; tamper one original worksheet label.
        with zipfile.ZipFile(io.BytesIO(raw)) as z:parts={x:z.read(x) for x in z.namelist()}
        parts['xl/workbook.xml']=parts['xl/workbook.xml'].replace(b'95% deformation',b'95% deformati0n')
        with io.BytesIO() as buf:
            with zipfile.ZipFile(buf,'w') as z:
                for name,payload in parts.items():z.writestr(name,payload)
            tampered=buf.getvalue()
        with self.assertRaisesRegex(ValueError,'unexpected deformation worksheet'):
            m.tables_from_original(tampered)

if __name__=='__main__':unittest.main()