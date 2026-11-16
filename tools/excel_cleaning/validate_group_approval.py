"""Pristine workbook and fail-closed decision-preview validation. No SQL."""
import collections,hashlib,unittest,zipfile
from xml.etree import ElementTree as ET
from prepare_group_approval import build,decision_effect,DECISIONS,OUT,NS
class GroupApprovalTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.sheets,cls.stats,cls.rows=build()
 def test_pristine_sheets_match_all_evidence(self):
  with zipfile.ZipFile(OUT/"it_warehouse_group_approval.xlsx") as z:
   self.assertIsNone(z.testzip())
   names=[s.attrib["name"] for s in ET.fromstring(z.read("xl/workbook.xml")).find(NS+"sheets")]
   self.assertEqual(names,list(self.sheets))
   for i,(name,expected) in enumerate(self.sheets.items(),1):
    root=ET.fromstring(z.read("xl/worksheets/sheet"+str(i)+".xml"))
    actual=[[c.find(NS+"is/"+NS+"t").text or "" for c in r] for r in root.find(NS+"sheetData")]
    self.assertEqual(actual,[["" if v is None else str(v) for v in r] for r in expected],name)
   for name in z.namelist():
    root=ET.fromstring(z.read(name));self.assertFalse(root.findall(".//"+NS+"f"))
    self.assertNotIn(b'TargetMode="External"',z.read(name))
 def test_groups_and_rows_reconcile_without_loss(self):
  self.assertEqual(self.stats["internally_consistent_groups"]+self.stats["groups_with_conflicts"],245)
  rows=self.sheets["Row reconciliation"];h=rows[0];rows=rows[1:]
  self.assertEqual(len(rows),897);self.assertEqual(len({r[0] for r in rows}),897)
  for row in rows:
   self.assertTrue(all(row[h.index(k)] for k in ["source_row_id","source_sha256","worksheet","excel_row"]))
  counts=collections.Counter(r[4] for r in rows)
  self.assertEqual(dict(counts),{r[0]:r[1] for r in self.sheets["Group approval"][1:]})
 def test_all_duplicate_members_preserved(self):
  from prepare_review import load
  m,_=load();actual=collections.defaultdict(set)
  for group,ident,*_ in self.sheets["Duplicate preservation"][1:]:actual[group].add(ident)
  self.assertEqual(sorted(sorted(v) for v in actual.values()),sorted(sorted(v) for v in m["exact_duplicate_groups"]))
 def test_unknowns_and_blank_decisions_stay_unknown(self):
  header=self.sheets["Group approval"][0]
  for row in self.sheets["Group approval"][1:]:
   self.assertEqual(row[header.index("model_number_evidence")],"")
   for key in DECISIONS:self.assertEqual(row[header.index(key)],"")
  for row in self.rows.values():
   effect=decision_effect(row,{})
   self.assertEqual(effect["mapping_preview_status"],"BLOCKED")
   self.assertIn("GROUP_NOT_APPROVED",effect["blockers"])
   self.assertEqual(effect["source_row_id"],row["source_row_id"])
 def example(self):
  r={"source_row_id":"test-row","source_sha256":"test-sha","worksheet":"synthetic","excel_row":"2","product_group_id":"test-group","quantity_proposal":"2","source_location":"observed","row_exception_codes":"","duplicate_group":""}
  d=dict.fromkeys(DECISIONS,"reviewed");d.update(approval_status="APPROVED",approved_tracking_mode="BULK")
  return r,d
 def test_group_approval_cannot_override_row_exception(self):
  r,d=self.example();r["row_exception_codes"]="LOCATION_CONFLICT"
  self.assertIn("ROW_EXCEPTION_REQUIRES_SEPARATE_REVIEW",decision_effect(r,d)["blockers"])
  self.assertIn("ROW_EXCEPTION_REQUIRES_SEPARATE_REVIEW",decision_effect(r,d,{"status":"RESOLVED"})["blockers"])
 def test_quantity_and_location_remain_blockers(self):
  r,d=self.example();r["quantity_proposal"]=""
  self.assertIn("ROW_QUANTITY_UNRESOLVED",decision_effect(r,d)["blockers"])
  r,d=self.example();d["approved_location"]=" "
  self.assertIn("MISSING_APPROVED_LOCATION",decision_effect(r,d)["blockers"])
  r,d=self.example();d["approved_warehouse"]=""
  self.assertIn("MISSING_APPROVED_WAREHOUSE",decision_effect(r,d)["blockers"])
 def test_duplicates_never_inherit_import_approval(self):
  r,d=self.example();r["duplicate_group"]="DUP-test"
  self.assertIn("DUPLICATE_DISPOSITION_AND_EXACT_MANIFEST_REQUIRED",decision_effect(r,d)["blockers"])
 def test_mapping_complete_is_still_not_import_authority(self):
  r,d=self.example();result=decision_effect(r,d)
  self.assertEqual(result["mapping_preview_status"],"REQUIRES_SEPARATE_EXACT_IMPORT_AUTHORIZATION")
  self.assertEqual(result["source_sha256"],r["source_sha256"])
 def test_report_hash(self):
  sha=hashlib.sha256((OUT/"it_warehouse_group_approval.xlsx").read_bytes()).hexdigest()
  self.assertIn(sha,(OUT/"group_mapping_summary.md").read_text())
if __name__=="__main__":unittest.main(verbosity=2)
