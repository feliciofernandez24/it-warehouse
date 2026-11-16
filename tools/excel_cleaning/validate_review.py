"""Validate the pristine offline review; never accepts edits as import authorization."""
import collections, hashlib, json, unittest, zipfile
from xml.etree import ElementTree as ET
from prepare_review import OUT,NS,ADMIN,load,tables
class ReviewValidation(unittest.TestCase):
 def setUp(self):
  self.expected,self.counts=tables()
  self.z=zipfile.ZipFile(OUT/"it_warehouse_import_review.xlsx")
  self.addCleanup(self.z.close)
 def values(self,index):
  root=ET.fromstring(self.z.read("xl/worksheets/sheet"+str(index)+".xml"))
  return [[(c.find(NS+"is/"+NS+"t").text or "") for c in r] for r in root.find(NS+"sheetData")]
 def test_input_hashes_and_cleaned_traceability(self):
  m,rows=load();self.assertEqual(len(rows),897);self.assertEqual(len(m["exact_duplicate_groups"]),17)
 def test_all_sheets_exactly_match_pristine_proposals(self):
  wb=ET.fromstring(self.z.read("xl/workbook.xml"))
  self.assertEqual([x.attrib["name"] for x in wb.find(NS+"sheets")],list(self.expected))
  for index,(name,rows) in enumerate(self.expected.items(),1):
   with self.subTest(sheet=name):
    self.assertEqual(self.values(index),[["" if v is None else str(v) for v in row] for row in rows])
 def test_no_formulas_external_links_or_corrupt_xml(self):
  self.assertIsNone(self.z.testzip())
  for name in self.z.namelist():
   root=ET.fromstring(self.z.read(name))
   self.assertFalse(root.findall(".//"+NS+"f"))
   self.assertFalse(root.findall(".//"+NS+"hyperlink"))
   self.assertNotIn("externalLink",name)
   self.assertNotIn(b'TargetMode="External"',self.z.read(name))
 def test_all_records_once_and_groups_reconcile(self):
  rows=self.values(2);headers=rows[0];rows=rows[1:]
  self.assertEqual(len(rows),897)
  self.assertEqual(len({r[0] for r in rows}),897)
  counts=collections.Counter(r[headers.index("product_group_id")] for r in rows)
  groups=self.values(3)[1:]
  self.assertEqual(dict(counts),{g[0]:int(g[6]) for g in groups})
 def test_duplicates_never_merged(self):
  m,_=load();actual=collections.defaultdict(set)
  for d,ident,*_ in self.values(4)[1:]:actual[d].add(ident)
  self.assertEqual(list(sorted(sorted(v) for v in actual.values())),list(sorted(sorted(v) for v in m["exact_duplicate_groups"])))
 def test_no_fabricated_model_or_administrator_approval(self):
  rows=self.values(2);head=rows[0]
  for row in rows[1:]:
   for name in ["model_number_proposal","part_number_proposal"]+ADMIN:
    self.assertEqual(row[head.index(name)],"")
   self.assertIn(row[head.index("tracking_proposal")],["SERIALIZED","BULK","UNRESOLVED"])
   self.assertEqual(row[head.index("product_mapping_confidence")],"UNRESOLVED")
 def test_report_binds_workbook(self):
  actual=hashlib.sha256((OUT/"it_warehouse_import_review.xlsx").read_bytes()).hexdigest()
  self.assertIn(actual,(OUT/"import_mapping_report.md").read_text())
if __name__=="__main__":unittest.main(verbosity=2)
