"""No fabricated battery observations. Unit tests use synthetic archives only."""
import io, unittest, zipfile
from research.battery_curve_audit.graz_paired_source_probe import (
    RECORD, DOI, FILENAME, MD5, check_metadata, inventory, preview
)

def fakezip(members):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for name,raw in members: z.writestr(name,raw)
    return b.getvalue()

class GrazOriginalTest(unittest.TestCase):
    def meta(self):
        return {"id":RECORD,"doi":DOI,
                "files":[{"key":FILENAME,"size":10000,"checksum":"md5:"+MD5}]}
    def test_publisher_identity(self):
        self.assertEqual(check_metadata(self.meta()),10000)
    def test_wrong_record(self):
        x=self.meta();x["id"]=-1
        with self.assertRaises(ValueError):check_metadata(x)
    def test_wrong_md5(self):
        x=self.meta();x["files"][0]["checksum"]="md5:"+"f"*32
        with self.assertRaises(ValueError):check_metadata(x)
    def test_wrong_file(self):
        x=self.meta();x["files"][0]["key"]="fake.zip"
        with self.assertRaises(ValueError):check_metadata(x)
    def test_oversize(self):
        x=self.meta();x["files"][0]["size"]=10**9
        with self.assertRaises(ValueError):check_metadata(x)
    def test_manifest(self):
        v=inventory(fakezip([("cell01/log.txt",b"time,current\n0,0\n"),
                             ("cell01/SP.csv",b"time,thickness\n0,1\n")]))
        self.assertEqual(v["file_count"],2)
        self.assertEqual(v["extensions"],{".csv":1,".txt":1})
        self.assertTrue(v["all_zip_crc_pass"])
    def test_path_traversal(self):
        with self.assertRaises(ValueError):
            inventory(fakezip([("../escape.csv",b"hello")]))
    def test_windows_drive(self):
        with self.assertRaises(ValueError):
            inventory(fakezip([("C:/escape.csv",b"hello")]))
    def test_ambiguous_name(self):
        with self.assertRaises(ValueError):
            inventory(fakezip([("A.txt",b"1"),("a.TXT",b"2")]))
    def test_zip_bomb(self):
        with self.assertRaises(ValueError):
            inventory(fakezip([("bad.txt",b"0"*1_000_000)]))
    def test_binary_header(self):
        self.assertFalse(preview(b"\x00\xfe")["text"])
    def test_plain_header(self):
        self.assertTrue(preview(b"a,b\n1,2")["text"])
if __name__=="__main__":unittest.main()
