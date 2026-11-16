"""Consolidated offline approval preparation. No database or source cleaning."""
import collections,hashlib,json,os,re,zipfile
from xml.etree import ElementTree as ET
from prepare_review import OUT,NS,load,write
DECISIONS=["approved_category","approved_manufacturer","approved_product_model","approved_sku","approved_tracking_mode","approved_quantity_interpretation","approved_warehouse","approved_location","approval_status","administrator_notes","administrator","decision_date"]
def read_review():
 m,source=load()
 with zipfile.ZipFile(OUT/"it_warehouse_import_review.xlsx") as z:
  names=[s.attrib["name"] for s in ET.fromstring(z.read("xl/workbook.xml")).find(NS+"sheets")]
  result={}
  for i,name in enumerate(names,1):
   root=ET.fromstring(z.read("xl/worksheets/sheet"+str(i)+".xml"))
   values=[[c.find(NS+"is/"+NS+"t").text or "" for c in r] for r in root.find(NS+"sheetData")]
   result[name]=[dict(zip(values[0],r)) for r in values[1:]]
 return m,source,result
def present(v):return isinstance(v,str) and bool(v.strip())
def decision_effect(row,decision,exception_decision=None):
 """Offline gate preview only; never authorizes an import or executes writes.
 Row facts are immutable inputs; group decisions cannot manufacture per-row quantities.
 """
 blockers=[]
 if decision.get("approval_status")!="APPROVED":blockers.append("GROUP_NOT_APPROVED")
 for key in ["approved_category","approved_product_model","approved_sku","approved_quantity_interpretation","approved_warehouse","approved_location","administrator","decision_date"]:
  if not present(decision.get(key)):blockers.append("MISSING_"+key.upper())
 if decision.get("approved_tracking_mode") not in ("SERIALIZED","BULK"):blockers.append("TRACKING_UNRESOLVED")
 # Optional manufacturer may remain unknown; do not fill it from an assumed default.
 if row["quantity_proposal"] in ("",None):blockers.append("ROW_QUANTITY_UNRESOLVED")
 if not row["source_location"].strip():blockers.append("SOURCE_LOCATION_MISSING")
 if row["row_exception_codes"]:
  if not exception_decision or exception_decision.get("status")!="RESOLVED" or not present(exception_decision.get("administrator")) or not present(exception_decision.get("notes")):
   blockers.append("ROW_EXCEPTION_REQUIRES_SEPARATE_REVIEW")
 if row["duplicate_group"]:
  blockers.append("DUPLICATE_DISPOSITION_AND_EXACT_MANIFEST_REQUIRED")
 return {"source_row_id":row["source_row_id"],"source_sha256":row["source_sha256"],"worksheet":row["worksheet"],"excel_row":row["excel_row"],"group_id":row["product_group_id"],
         "mapping_preview_status":"BLOCKED" if blockers else "REQUIRES_SEPARATE_EXACT_IMPORT_AUTHORIZATION","blockers":blockers}
def build():
 m,source,review=read_review()
 records=review["Equipment review"];original={r["source_row_digest"]:r for r in source}
 groups=collections.defaultdict(list)
 generic={"PRODUCT_MAPPING_PENDING","TRACKING_MAPPING_PENDING","LOCATION_MAPPING_PENDING","MAPPING_POLICY_PENDING"}
 for r in records:
  assert r["source_row_id"] in original
  r["row_exception_codes"]="; ".join(c for c in r["source_issue_codes"].split("; ") if c and c not in generic)
  groups[r["product_group_id"]].append(r)
 assert len(groups)==245 and len(records)==897
 groupheader=["product_group_id","record_count","source_coordinates_json","representative_description","source_device_label","manufacturer_proposal","canonical_category_proposal","product_name_proposal","proposal_reason","model_number_evidence","technical_specifications","serial_evidence_json","source_locations_json","quantity_evidence_json","consistency_status","conflict_flags","individual_exception_count","duplicate_groups","unresolved_evidence"]+DECISIONS
 groupdata=[groupheader];reconciliation=[["source_row_id","source_sha256","worksheet","excel_row","product_group_id","source_device_label","source_manufacturer","raw_serial","source_quantity","quantity_proposal","source_location","duplicate_group","row_exception_codes","group_fields_would_apply","row_exception_status","preview_status","blockers","row_admin_status","row_admin_notes","row_administrator"]]
 exceptions=[["source_row_id","product_group_id","worksheet","excel_row","row_exception_codes","duplicate_group","resolution_status","administrator_notes","administrator"]]
 stats=collections.Counter();rowmap={}
 for gid,rs in sorted(groups.items()):
  raw=[{c["header"]:c["value"] for c in original[r["source_row_id"]]["raw_cells"] if c["header"]} for r in rs]
  flags=[]
  for field in ("Device Category","Manufacturer","Manufacture","Condition","Status","Qty"):
   values={(f.get(field) or "").strip().casefold() for f in raw}
   if len(values)>1:flags.append("MIXED_"+field.upper().replace(" ","_"))
  descriptions=sorted({(f.get("Description") or "").strip() for f in raw if (f.get("Description") or "").strip()})
  if len(descriptions)>1:flags.append("DESCRIPTION_VARIATION_POSSIBLE_MIXED_EQUIPMENT")
  codes={c for r in rs for c in r["source_issue_codes"].split("; ")}
  for code in ("SPEC_CONFLICT","LOCATION_CONFLICT","HANDOVER","PART_LIKE_ID"):
   if code in codes:flags.append(code)
  status="CONFLICT_OR_MIXED_EVIDENCE" if flags else "INTERNALLY_CONSISTENT_OBSERVED_FIELDS"
  stats["groups_with_conflicts" if flags else "internally_consistent_groups"]+=1
  needs=sum(bool(r["row_exception_codes"] or r["duplicate_group"]) for r in rs)
  stats["groups_requiring_individual_review"]+=bool(needs)
  stats["individual_exception_rows"]+=needs
  first=rs[0];category=first["category_proposal"];brand=first["manufacturer_proposal"];name=first["source_device_name"]
  label=" ".join(x for x in (brand,name) if x)
  # Preserve the exact evidence label when it already begins with the manufacturer.
  if brand and name.casefold().startswith(brand.casefold()):label=name
  if len(label)>200:label="" # Never silently truncate a proposed identity.
  reason="Canonical category inherited from reviewed dictionary; name combines known manufacturer and device label only. Not a verified manufacturer model. Technical details remain separate; approve a SKU and exact model identity or explicit generic-model policy."
  unresolved=["SKU/model identity not approved","tracking policy not approved","warehouse/location binding not approved","exact import authorization absent"]
  if not category:unresolved.append("category unknown")
  if not brand:unresolved.append("manufacturer unknown (optional FK)")
  if any(not r["quantity_proposal"] for r in rs):unresolved.append("one or more piece quantities unknown/unusable")
  if not label:unresolved.append("product name absent or exceeds 200 characters")
  serials=[{"source_row_id":r["source_row_id"],"raw_serial":r["raw_serial"]} for r in rs]
  coords=[{"source_row_id":r["source_row_id"],"worksheet":r["worksheet"],"excel_row":r["excel_row"]} for r in rs]
  # Long evidence lists are split across the reconciliation sheet, never truncated there.
  def evidence(v):
   text=json.dumps(v,ensure_ascii=False)
   return text if len(text)<=32000 else "Full per-row evidence in Row reconciliation (exceeds cell limit)"
  groupdata.append([gid,len(rs),evidence(coords),evidence(descriptions[:3]),name,brand,category,label,reason,"",first["technical_specs_proposal"],evidence(serials),evidence(sorted({r["source_location"] for r in rs})),evidence([{"raw":r["source_quantity"],"proposal":r["quantity_proposal"]} for r in rs]),status,"; ".join(flags),needs,"; ".join(sorted({r["duplicate_group"] for r in rs if r["duplicate_group"]})),"; ".join(unresolved)]+[""]*len(DECISIONS))
  for r in rs:
   effect=decision_effect(r,{})
   rowmap[r["source_row_id"]]=r
   reconciliation.append([r["source_row_id"],r["source_sha256"],r["worksheet"],r["excel_row"],gid,r["source_device_name"],r["manufacturer_proposal"],r["raw_serial"],r["source_quantity"],r["quantity_proposal"],r["source_location"],r["duplicate_group"],r["row_exception_codes"],"category/manufacturer/product/SKU/tracking/quantity-policy/location only after explicit group approval; row facts remain unchanged","UNRESOLVED" if r["row_exception_codes"] or r["duplicate_group"] else "NONE_IDENTIFIED",effect["mapping_preview_status"],"; ".join(effect["blockers"]),"","",""])
   if r["row_exception_codes"] or r["duplicate_group"]:exceptions.append([r["source_row_id"],gid,r["worksheet"],r["excel_row"],r["row_exception_codes"],r["duplicate_group"],"","",""])
 duplicate=[["duplicate_group","source_row_id","worksheet","excel_row","disposition","administrator_notes"]]
 for r in review["Duplicate groups"]:duplicate.append([r["duplicate_group"],r["source_row_id"],r["worksheet"],r["excel_row"],"",""])
 stats.update(equipment_records=897,evidence_groups=245,preserved_duplicate_groups=17,approved_groups=0,approved_rows=0)
 summary=[["metric","value"]]+[[k,v] for k,v in sorted(stats.items())]+[["input_manifest_digest",m["manifest_digest"]],["input_review_sha256",hashlib.sha256((OUT/"it_warehouse_import_review.xlsx").read_bytes()).hexdigest()],["instructions","Group decisions are proposals only; separately resolve row exceptions and duplicate dispositions. No quantity inferred from row count. Location labels are not approved FKs. Blank decisions are never approval. This workbook is a static snapshot; rerun reviewed reconciliation logic after edits, not spreadsheet formulas."],["consistency_definition","No detected variation in selected raw category/manufacturer/condition/status/quantity fields, description variation or known conflict codes. Consistency is not completeness or import readiness."]]
 return {"Summary":summary,"Group approval":groupdata,"Row reconciliation":reconciliation,"Individual exceptions":exceptions,"Duplicate preservation":duplicate},dict(stats),rowmap
def main():
 os.umask(0o077)
 sheets,stats,_=build();target=OUT/"it_warehouse_group_approval.xlsx"
 write(target,sheets)
 report="# Consolidated group mapping review\n\nOffline only; no cleaning rerun or PostgreSQL connection. Existing review workbook and source coordinates preserved.\n\n"+json.dumps(stats,indent=2)+"\n\n"
 report+="Internally consistent and conflict groups partition the 245 groups. Groups requiring individual-row review overlap both categories. Consistency means no detected variation in the explicitly tested fields, not a verified model or approval. Description differences flag possible mixed equipment, not proven different models. Serial variation is expected and never used alone to merge or split equipment; source-location variation is shown without asserting that identical products at different locations conflict.\n\n"
 report+="One Group approval row per existing evidence group. Proposed category inherits the reviewed dictionary; product name combines only observed manufacturer/device labels. Manufacturer model numbers remain blank because none is explicitly established. Specifications remain source proposals, with no inferred capacity units, SKU, quantity, location FK or missing manufacturer. Three representative descriptions are shown; full row evidence remains in the existing review/manifest. Serial and coordinate lists too large for an Excel cell point to the full Row reconciliation sheet, preserving all records there.\n\n"
 report+="Approved category/manufacturer/product/SKU/tracking/quantity interpretation/warehouse/location, status, notes, administrator and date start blank. Optional unknown manufacturer may remain blank; this is not permission to invent one. No group currently approved. Row reconciliation is a static preview showing inherited fields and blockers, not a formula that grants approval. Group decisions cannot resolve source quantities, exceptions or duplicates by themselves. Individual exceptions need separately attributed resolution; the offline evaluator still requires exact import authorization even when all mapping checks pass. It does not validate real FK existence, authentic operator identity or receipt authorization.\n\n"
 report+="No duplicate is merged or dropped; all 17 groups and every member remain on Duplicate preservation. Every reconciliation row retains source hash, row digest, sheet and Excel row. Missing/unusable piece quantity blocks the row even if group quantity interpretation is approved; missing approved warehouse/location also blocks. Row-specific location overrides require a future exact per-row plan rather than silently replacing evidence. No default quantity of one or group-count stock quantity is created.\n\n"
 report+="Validation: PYTHONDONTWRITEBYTECODE=1 python3 tools/excel_cleaning/validate_group_approval.py\nExisting validation: python3 tools/excel_cleaning/validate_review.py; python3 -m unittest discover -s tools/excel_cleaning -v.\nThe validator verifies the pristine generated workbook and tests decision-gate behavior with synthetic in-memory cases. It deliberately does not accept edited spreadsheets as operational import approval. A later reviewed edit validator must handle administrator decisions, authenticated identity, per-row exceptions and exact manifest approval before any import.\n\n"
 report+="Workbook SHA-256: "+hashlib.sha256(target.read_bytes()).hexdigest()+"\n"
 with (OUT/"group_mapping_summary.md").open("x") as f:f.write(report)
 print(json.dumps(stats,sort_keys=True))
if __name__=="__main__":main()
