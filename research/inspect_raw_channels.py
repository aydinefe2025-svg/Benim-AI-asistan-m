import hashlib,base64,json,zipfile,collections,pathlib,posixpath
import xml.etree.ElementTree as ET
from birds_eps_constellation_qc import NS,REL,SRC,SOURCES,colname,decode_cell,shared_strings
from tsuru_agv_real_source_ci import get,GIT_SHA
pins={"TSURU":{"sha1":GIT_SHA,"bytes":6059029},**SOURCES}
for sat,pin in pins.items():
    file=pathlib.Path(sat+"_original.xlsx")
    if not file.exists():
        doc=json.loads(get(SRC+pin["sha1"],github=True))
        raw=base64.b64decode(doc["content"])
        if len(raw)!=pin["bytes"] or hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()!=pin["sha1"]:raise ValueError(sat)
        file.write_bytes(raw)
    raw=file.read_bytes()
    assert hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()==pin["sha1"]
    with zipfile.ZipFile(file) as z:
        assert z.testzip() is None
        ss=shared_strings(z)
        sh=ET.fromstring(z.read("xl/workbook.xml")).findall(NS+"sheets/"+NS+"sheet")
        links={e.get("Id"):e.get("Target") for e in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        target=links[sh[0].get(REL+"id")]
        path=target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl",target))
        rows=ET.fromstring(z.read(path)).findall(NS+"sheetData/"+NS+"row")
        sample=[{colname(c.get("r")):decode_cell(c,ss) for c in rr.findall(NS+"c")} for rr in rows[:4]]
        print(sat,sh[0].get("name"),json.dumps(sample,ensure_ascii=True))
