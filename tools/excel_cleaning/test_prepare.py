import hashlib,json,tempfile,unittest,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from prepare import ROOT,workbook
from apps.inventory.staging.common import digest
class ExportTests(unittest.TestCase):
 def setUp(self):
  self.out=ROOT/"imports/cleaned";self.m=json.loads((self.out/"import_manifest.json").read_text())
 def test_manifest_integrity(self):
  m=dict(self.m);actual=m.pop("manifest_digest");self.assertEqual(digest(m),actual)
 def test_original_and_copy_unchanged(self):
  for p in [ROOT/"imports"/self.m["source_file"],ROOT/self.m["original_copy"]]:
   self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),self.m["source_sha256"])
 def test_artifacts_and_xml(self):
  for name,sha in self.m["artifact_sha256"].items():
   p=self.out/name;self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),sha)
   with zipfile.ZipFile(p) as z:
    self.assertIsNone(z.testzip())
    for n in z.namelist():ET.fromstring(z.read(n))
 def test_traceability_and_no_loss(self):
  rows=self.m["preview"]["rows"];self.assertEqual(len(rows),920)
  self.assertEqual(len({r["source_row_digest"] for r in rows}),len(rows))
  self.assertEqual(sum(self.m["classifications"].values()),len(rows))
  for n,expected in [("it_warehouse_cleaned.xlsx",898),("it_warehouse_rejected.xlsx",24)]:
   with zipfile.ZipFile(self.out/n) as z:
    root=ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    self.assertEqual(len(root.find("{*}sheetData")),expected)
 def test_no_approval_or_posting(self):
  self.assertIsNone(self.m["approval"]);self.assertFalse(self.m["posting_enabled"])
  self.assertEqual(self.m["mapping"]["persistent_imports"],0)
  self.assertEqual(self.m["mapping"]["deferred_stock_rows"],897)
 def test_formula_and_serial_safety(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"test.xlsx";workbook(p,[["=HYPERLINK(\"x\")","00123","+1","@foo"]])
   with zipfile.ZipFile(p) as z:
    r=ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    self.assertFalse(r.findall(".//{*}f"))
    self.assertEqual([c.find("{*}is/{*}t").text for c in r.findall(".//{*}c")],["=HYPERLINK(\"x\")","00123","+1","@foo"])
   with self.assertRaises(FileExistsError):workbook(p,[])
if __name__=="__main__":unittest.main()
