"""Bounded authentic Zenodo 18213931 10-cell EIS XLSX source schema audit.

This is a published-data integrity and raw workbook structure screen, NOT
physical calibration, per-specimen force proof, usable capacity or field safety.
Only Python standard library; inspect OOXML without mutating original workbook.
"""
from __future__ import annotations
import hashlib, io, json, math, re, sys, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, BadZipFile

RECORD=18213931
DOI='10.5281/zenodo.18213931'
PINS={
'EIS_C02.xlsx':'c391ad1b0d894e5f2b1a9a5c73c2a2ed',
'EIS_C03.xlsx':'8e1331250ab7ae9b00399c759a7c3048',
'EIS_C04.xlsx':'6701abafa4eb59e663978206d4ddf4a2',
'EIS_C05.xlsx':'9f1f5c2a5485061b5029ccca1b433698',
'EIS_C06.xlsx':'77a9d3fe9a08cb39f275f1fcb9932339',
'EIS_C09.xlsx':'ff437700bfd64ad845c6d306379f1ead',
'EIS_C10.xlsx':'595b56155cfd4e2eb806d9da8e7f916d',
'EIS_C11.xlsx':'2eb3a4555c27e40e6aff17de904f81f3',
'EIS_C12.xlsx':'29478b024bcb737502b407d56d383073',
'EIS_C13.xlsx':'36768c41b089ea76262a303f29607d05',
}
X='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PKG='{http://schemas.openxmlformats.org/package/2006/relationships}'
MAX_FILE_BYTES=110_000
MAX_XML_BYTES=2_000_000
MAX_UNCOMPRESSED=5_000_000

def fetch(url:str,limit:int)->bytes:
    req=urllib.request.Request(url,headers={'User-Agent':'CANO independent scientific public-source verifier/1.0','Accept':'application/octet-stream,application/json'})
    with urllib.request.urlopen(req,timeout=45) as response:
        if response.status != 200:raise ValueError('PUBLIC_SOURCE_NOT_AVAILABLE: HTTP status')
        d=response.read(limit+1)
    if not (0<len(d)<=limit):raise ValueError('SOURCE_REVIEW_REQUIRED: bounds exceeded')
    return d

def _xml(z:ZipFile,name:str):
    if name not in z.namelist():raise ValueError('SOURCE_REVIEW_REQUIRED: missing OOXML part '+name)
    f=z.getinfo(name)
    if f.file_size > MAX_XML_BYTES:raise ValueError('SOURCE_REVIEW_REQUIRED: unbounded OOXML XML')
    try:return ET.fromstring(z.read(name))
    except ET.ParseError as e:raise ValueError('SOURCE_REVIEW_REQUIRED: invalid OOXML part') from e

def _cell_text(c,shared:list[str])->str:
    t=c.attrib.get('t')
    v=c.find(X+'v')
    inline=c.find(X+'is')
    if t=='inlineStr' and inline is not None:
        value=''.join(node.text or '' for node in inline.iter(X+'t'))
    else:
        value=v.text if v is not None and v.text is not None else ''
    if t=='s':
        try:value=shared[int(value)]
        except (ValueError,IndexError) as e:raise ValueError('SOURCE_REVIEW_REQUIRED: invalid shared string index') from e
    if t not in ('s','inlineStr','str','b','e') and value:
        try:
            numeric=float(value)
            if not math.isfinite(numeric):raise ValueError('SOURCE_REVIEW_REQUIRED: nonfinite XLSX cell')
        except ValueError as e:
            if str(e).startswith('SOURCE_REVIEW_REQUIRED'):raise
            raise ValueError('SOURCE_REVIEW_REQUIRED: invalid numeric cell') from e
    return value[:80]

def inspect_original_workbook(raw:bytes,name:str,expected_md5:str)->dict:
    if name not in PINS or expected_md5!=PINS[name] or not isinstance(raw,bytes):
        raise ValueError('SOURCE_REVIEW_REQUIRED: unexpected original source identity')
    if not (5000<=len(raw)<=MAX_FILE_BYTES) or hashlib.md5(raw).hexdigest()!=expected_md5:
        raise ValueError('SOURCE_REVIEW_REQUIRED: original published MD5 / byte bounds conflict')
    try:
        with ZipFile(io.BytesIO(raw)) as z:
            infos=z.infolist();names=[i.filename for i in infos]
            if len(names)!=len(set(names)) or len(names)>125 or sum(i.file_size for i in infos)>MAX_UNCOMPRESSED:
                raise ValueError('SOURCE_REVIEW_REQUIRED: unsafe OOXML member inventory')
            if any(i.is_dir() or '\\' in i.filename or PurePosixPath(i.filename).is_absolute()
                   or '..' in PurePosixPath(i.filename).parts or i.flag_bits & 1 for i in infos):
                raise ValueError('SOURCE_REVIEW_REQUIRED: unsafe OOXML member')
            if z.testzip() is not None:raise ValueError('SOURCE_REVIEW_REQUIRED: ZIP CRC mismatch')
            shared=[]
            if 'xl/sharedStrings.xml' in names:
                root=_xml(z,'xl/sharedStrings.xml')
                shared=[''.join(x.text or '' for x in si.iter(X+'t')) for si in root.findall(X+'si')]
                if len(shared)>10000:raise ValueError('SOURCE_REVIEW_REQUIRED: string table too large')
            workbook=_xml(z,'xl/workbook.xml')
            rels=_xml(z,'xl/_rels/workbook.xml.rels')
            mappings={x.attrib['Id']:x.attrib['Target'] for x in rels.findall(PKG+'Relationship')}
            sheet_list=[]
            seen=set()
            for sheet in workbook.findall('.//'+X+'sheet'):
                rel=sheet.attrib.get(R+'id')
                target=mappings.get(rel,'')
                if not target:raise ValueError('SOURCE_REVIEW_REQUIRED: sheet relationship missing')
                if target.startswith('/xl/'):
                    path=target.lstrip('/')
                elif target.startswith('xl/'):
                    path=target
                else:path='xl/'+target.lstrip('/')
                if not path.startswith('xl/worksheets/') or path not in names or path in seen:
                    raise ValueError('SOURCE_REVIEW_REQUIRED: invalid/duplicate worksheet')
                seen.add(path)
                doc=_xml(z,path)
                rows=doc.findall('.//'+X+'sheetData/'+X+'row')
                if len(rows)>10000:raise ValueError('SOURCE_REVIEW_REQUIRED: excessive source rows')
                num_cells=0;populated=0;preview=[]
                for row in rows:
                    cells=row.findall(X+'c');entry=[]
                    for cell in cells:
                        value=_cell_text(cell,shared)
                        if value:
                            populated+=1
                            if cell.attrib.get('t') not in ('s','inlineStr','str','b','e'):num_cells+=1
                            if len(preview)<6 and len(entry)<10:
                                entry.append({'ref':cell.attrib.get('r','')[:10], 'value':value})
                    if entry and len(preview)<6:preview.append(entry)
                sheet_list.append({'sheet':sheet.attrib.get('name','')[:100],
                    'source_row_count':len(rows),'nonempty_cells':populated,
                    'numeric_cells':num_cells,'first_six_nonempty_row_snippets':preview})
            if not 1<=len(sheet_list)<=30:raise ValueError('SOURCE_REVIEW_REQUIRED: unexpected XLSX sheets')
            return {'publisher_filename':name,'publisher_md5_verified':True,
                'source_sha256':hashlib.sha256(raw).hexdigest(),
                'original_file_bytes':len(raw),'zip_member_count':len(infos),
                'zip_crc_pass':True,'sheets':sheet_list,'sheet_count':len(sheet_list),
                'numeric_source_cell_count':sum(s['numeric_cells'] for s in sheet_list)}
    except (BadZipFile,RuntimeError,KeyError) as e:
        raise ValueError('SOURCE_REVIEW_REQUIRED: invalid original XLSX archive') from e

def run()->dict:
    metadata=json.loads(fetch(f'https://zenodo.org/api/records/{RECORD}',600_000))
    if int(metadata.get('id',0))!=RECORD:
        raise ValueError('SOURCE_REVIEW_REQUIRED: source publication metadata ID mismatch')
    indexed={x['key']:(x.get('checksum',''),x.get('links',{}).get('self','')) for x in metadata.get('files',[])}
    if set(PINS)-set(indexed):raise ValueError('SOURCE_REVIEW_REQUIRED: original EIS workbook absent')
    examined=[]
    for name,digest in PINS.items():
        meta_pin,url=indexed[name]
        if meta_pin!='md5:'+digest or not url.startswith('https://zenodo.org/'):
            raise ValueError('SOURCE_REVIEW_REQUIRED: source metadata conflict')
        raw=fetch(url,MAX_FILE_BYTES)
        examined.append(inspect_original_workbook(raw,name,digest))
    return {'schema':'cano.impact-2026.graz-original-eis-ooxml-source-inventory.v1',
        'doi':DOI,'record_id':RECORD,'publisher_source_lab':'Graz University of Technology',
        'source_workbook_count':len(examined),'source_spreadsheet_details':examined,
        'sum_source_numeric_cells':sum(x['numeric_source_cell_count'] for x in examined),
        'all_publisher_md5_and_zip_crc_verified':len(examined)==len(PINS),
        'same_specimen_repeated_eis_levels_authenticated':False,
        'absolute_eis_calibration_verified':False,'original_physical_pre_post_capacity_measured':False,
        'EIS_is_capacity':False,'field_FPR_FNR_established':False,
        'production_release_allowed':False,
        'decision':'REAL_PUBLISHER_EIS_ORIGINAL_SOURCE_LAYOUT_ONLY_RESEARCH'}

def main(argv=None)->int:
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=1:return 2
    try:
        dest=Path(args[0]);
        if dest.exists() or not dest.parent.is_dir():raise ValueError('SOURCE_REVIEW_REQUIRED: unsafe output path')
        v=run()
        with dest.open('x',encoding='utf8') as f:json.dump(v,f,sort_keys=True,indent=2);f.write('\n')
        print('GRAZ_ORIGINAL_EIS',v['source_workbook_count'],'workbooks',v['sum_source_numeric_cells'],'numeric source cells')
        for x in v['source_spreadsheet_details']:
            print(x['publisher_filename'],'sheets',x['sheet_count'], 'numeric',x['numeric_source_cell_count'],
                'sheet_names',[s['sheet'] for s in x['sheets']])
        return 0
    except (ValueError,OSError,UnicodeError,KeyError,TypeError) as e:
        print('SOURCE_REVIEW_REQUIRED:',str(e)[:180],file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())