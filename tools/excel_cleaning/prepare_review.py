"""Prepare offline review from existing artifacts only; never connects to Django/SQL."""
import collections, hashlib, json, os, tempfile, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from prepare import workbook, ROOT
from apps.inventory.staging.common import digest
OUT=ROOT/"imports/cleaned"
NS="{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
ADMIN=["admin_decision","admin_category_code","admin_manufacturer_code","admin_sku_code","admin_product_name","admin_model_number","admin_part_number","admin_tracking_mode","admin_quantity","admin_warehouse_code","admin_location_code","admin_duplicate_disposition","admin_notes","administrator","decision_date"]
def load():
 m=json.loads((OUT/"import_manifest.json").read_text())
 check=dict(m);assert digest({k:v for k,v in check.items() if k!="manifest_digest"})==m["manifest_digest"],"MANIFEST_TAMPER"
 for name,sha in m["artifact_sha256"].items():
  assert hashlib.sha256((OUT/name).read_bytes()).hexdigest()==sha,"CLEANED_ARTIFACT_TAMPER"
 # Inspect every cleaned workbook row and verify exact candidate IDs and source provenance.
 with zipfile.ZipFile(OUT/"it_warehouse_cleaned.xlsx") as z:
  rows=ET.fromstring(z.read("xl/worksheets/sheet1.xml")).find(NS+"sheetData")
  vals=[[c.find(NS+"is/"+NS+"t").text or "" for c in r] for r in rows]
 candidates=[r for r in m["preview"]["rows"] if r["classification"]=="CANDIDATE"]
 assert [v[1] for v in vals[1:]]==[r["source_row_digest"] for r in candidates]
 assert all(v[0]==m["source_sha256"] for v in vals[1:])
 assert len(m["exact_duplicate_groups"])==17
 return m,candidates

def tables():
 m,rows=load();groups={};records=[];counts=collections.Counter();duplicates={}
 for i,ids in enumerate(m["exact_duplicate_groups"],1):
  for ident in ids:duplicates[ident]="DUP-"+str(i).zfill(3)
 headers=["source_row_id","source_sha256","worksheet","excel_row","product_group_id","category_proposal","manufacturer_proposal","source_device_name","model_number_proposal","part_number_proposal","technical_specs_proposal","tracking_proposal","tracking_confidence","tracking_reason","product_mapping_confidence","raw_serial","source_quantity","quantity_proposal","source_location","duplicate_group","missing_information","source_issue_codes"]+ADMIN
 for r in rows:
  p=r["preparation"]["proposal"];f={c["header"]:c["value"] for c in r["raw_cells"] if c["header"]}
  name=(f.get("Device Name") or f.get("Column 1") or "").strip()
  serial=f.get("Serial Number") or ""
  realserial=bool(serial.strip() and serial.strip().casefold() not in ("no sn","n/a","na","none","-"))
  category=p["category"];brand=p["manufacturer"]
  if category in ("DISK_HDD","DISK_SSD","MEMORY","NETWORK_ADAPTER","CONTROLLER","POWER_SUPPLY","BATTERY"):
   mode="SERIALIZED";confidence="MEDIUM";reason="Category suggests per-unit tracking; administrator must approve product-level tracking policy."
  elif category in ("FAN","CABLE"):
   mode="BULK";confidence="LOW";reason="Category may use quantity tracking; not established by the source. Serial-bearing rows require special review."
  elif realserial:
   mode="SERIALIZED";confidence="LOW";reason="Non-placeholder serial suggests per-unit identity, but category and identifier meaning are unresolved."
  else:
   mode="UNRESOLVED";confidence="LOW";reason="Insufficient evidence to choose SERIALIZED or BULK without inventing tracking policy."
  codes=sorted({i["code"] for i in r["preparation"]["issues"]})
  if any(c in codes for c in ("SERIAL_DUPLICATE","PART_LIKE_ID","SPEC_CONFLICT")):confidence="LOW"
  missing=["approved SKU","approved product identity/model or explicit generic-model policy","approved category FK","approved tracking policy","verified warehouse/location"]
  if not brand:missing.append("manufacturer identity (optional model FK; unresolved source fact)")
  if not category:missing.append("category identity")
  if p["quantity"] is None:missing.append("verified piece quantity")
  if not f.get("Location") or not f["Location"].strip():missing.append("source location missing")
  if not realserial:missing.append("serial identity missing/placeholder (requiredness depends on approved tracking policy)")
  if not name:missing.append("device/product display name")
  if len(name)>200:missing.append("product name exceeds 200 characters")
  key={"category":category,"manufacturer":brand,"device_name":name,"specifications":p["specifications"],"tracking_proposal":mode}
  gid="PG-"+digest(key)[:16]
  # This ID groups evidence only; it is not a SKU or proof of identical models.
  g=groups.setdefault(gid,{"key":key,"ids":[]});assert g["key"]==key
  g["ids"].append(r["source_row_digest"])
  records.append([r["source_row_digest"],m["source_sha256"],r["worksheet_name"],r["excel_row_number"],gid,category,brand,name,"","",json.dumps(p["specifications"],ensure_ascii=False,sort_keys=True),mode,confidence,reason,"UNRESOLVED",serial,f.get("Qty"),p["quantity"],f.get("Location"),duplicates.get(r["source_row_digest"],""),"; ".join(missing),"; ".join(codes)]+[""]*len(ADMIN))
  counts["tracking_"+mode]+=1;counts["tracking_confidence_"+confidence]+=1
  counts["missing_quantity"]+=p["quantity"] is None
  counts["missing_source_location"]+=not bool((f.get("Location") or "").strip())
  counts["missing_serial"]+=not realserial
 group_rows=[["product_group_id","category_proposal","manufacturer_proposal","source_device_name_not_verified_model","specifications","tracking_proposal","source_record_count","mapping_status","admin_sku_code","admin_product_name","admin_model_number","admin_part_number","admin_category_code","admin_manufacturer_code","admin_tracking_mode","admin_decision","admin_notes"]]
 for gid,g in sorted(groups.items()):
  k=g["key"];group_rows.append([gid,k["category"],k["manufacturer"],k["device_name"],json.dumps(k["specifications"],ensure_ascii=False,sort_keys=True),k["tracking_proposal"],len(g["ids"]),"UNRESOLVED: no explicit model/part column or approved SKU"]+[""]*9)
 duplicate_rows=[["duplicate_group","source_row_id","worksheet","excel_row","admin_disposition","admin_notes"]]
 byid={r["source_row_digest"]:r for r in rows}
 for ident,d in sorted(duplicates.items(),key=lambda t:(t[1],t[0])):
  r=byid[ident];duplicate_rows.append([d,ident,r["worksheet_name"],r["excel_row_number"],"",""])
 summary=[["metric","value"],["status","OFFLINE PROPOSALS ONLY; NO IMPORT AUTHORIZATION"],["source_sha256",m["source_sha256"]],["input_manifest_digest",m["manifest_digest"]],["equipment_records",len(rows)],["product_evidence_groups",len(groups)],["confident_complete_product_mappings",0],["records_requiring_administrator_decisions",len(rows)],["preserved_duplicate_groups",17],["duplicate_member_records",len(duplicates)],["missing_explicit_model_or_part_columns",len(rows)],["unresolved_location_bindings",len(rows)],["pending_exact_import_approval",len(rows)],["database_access","NONE"],["instructions","Do not merge by group ID or serial. Group ID is not a SKU. Blank decisions are not approval. UNRESOLVED tracking must be decided, not defaulted."]]
 summary += [[k,v] for k,v in sorted(counts.items())]
 return {"Summary":summary,"Equipment review":[headers]+records,"Product groups":group_rows,"Duplicate groups":duplicate_rows},counts

def write(path,sheets):
 # Reuse the previously tested inert inline-string writer to construct each sheet.
 with tempfile.TemporaryDirectory() as tmp:
  parts={};types=[];wb=[];rels=[]
  for i,(name,rows) in enumerate(sheets.items(),1):
   p=Path(tmp)/(str(i)+".xlsx");workbook(p,rows)
   with zipfile.ZipFile(p) as z:
    if i==1:parts={n:z.read(n) for n in z.namelist() if n not in ("xl/workbook.xml","xl/_rels/workbook.xml.rels","xl/worksheets/sheet1.xml","[Content_Types].xml")}
    parts["xl/worksheets/sheet"+str(i)+".xml"]=z.read("xl/worksheets/sheet1.xml")
   wb.append('<sheet name="'+escape(name)+'" sheetId="'+str(i)+'" r:id="rId'+str(i)+'"/>')
   rels.append('<Relationship Id="rId'+str(i)+'" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet'+str(i)+'.xml"/>')
   types.append('<Override PartName="/xl/worksheets/sheet'+str(i)+'.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
  parts["xl/workbook.xml"]='<workbook xmlns="'+NS[1:-1]+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(wb)+'</sheets></workbook>'
  parts["xl/_rels/workbook.xml.rels"]='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(rels)+'</Relationships>'
  parts["[Content_Types].xml"]='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join(types)+'</Types>'
  with zipfile.ZipFile(path,"x",compression=zipfile.ZIP_DEFLATED) as z:
   for n,v in parts.items():z.writestr(n,v)
  os.chmod(path,0o600)

def main():
 os.umask(0o077);sheets,counts=tables();target=OUT/"it_warehouse_import_review.xlsx"
 write(target,sheets)
 report="# Inventory import mapping review\n\nOffline only. No original cleaning repeated, no database connection, no import or receipt.\n\n"
 report+="Equipment records: 897. Confident complete product mappings: **0**. Administrator decisions required: **897**. Evidence groups: "+str(len(sheets["Product groups"])-1)+". Duplicate groups: **17**, all member rows preserved.\n\n"
 report+="Tracking and missing-information counts (overlapping, not additive):\n\n"+json.dumps(dict(sorted(counts.items())),indent=2)+"\n\n"
 report+="Category/manufacturer dictionary proposals are inherited unchanged from the verified cleaning manifest. Evidence grouping uses exact trimmed device labels, category/manufacturer proposals, specifications and proposed tracking. Groups are not proven identical models and must never trigger merging or SKU creation. Raw serial and original worksheet/row remain on every equipment row. Model/part numbers are blank: there are no explicit model/part columns, and free text is not sufficient to invent manufacturer model identity. Product display labels are evidence, not asserted model numbers.\n\n"
 report+="SERIALIZED is suggested for per-unit hardware categories; FAN/CABLE receive low-confidence BULK proposals requiring policy approval. Other serial-bearing rows receive low-confidence SERIALIZED suggestions; rows lacking evidence stay UNRESOLVED. Duplicate serials, part-like identifiers and conflicting specifications reduce confidence. Confidence concerns tracking only; no complete product mapping is HIGH confidence or approved. Missing serials do not automatically change tracking mode. No quantity of one is inferred for serialized rows.\n\n"
 report+="Django ProductModel requires sku_code (unique, <=64, uppercase code pattern), name (<=200), category FK and tracking_mode SERIALIZED/BULK. Manufacturer FK is optional; model/part numbers <=160. Capacity bytes must be positive; speed/size values must have corresponding units. Source technical proposals stay JSON evidence; no ambiguous GB-to-byte conversion or unsupported field assignment. Asset requires SERIALIZED and StockBalance requires BULK; stock facts and location hierarchy must be validated later using the authorized services. FK existence and uniqueness are not asserted: this offline task never queries PostgreSQL.\n\n"
 report+="Review the Equipment review sheet per source row and Product groups per evidence group; enter actual SKU/name/model/part/category/manufacturer bindings and approved tracking. Resolve quantity and physical warehouse/location, conflicts and each duplicate member's disposition. Keep unknown facts blank, with a reason. Administrator identity/date/decision columns start blank. Group decisions must be reconciled to all member rows before any future manifest is approved; this workbook is not an operational import format or authorization record.\n\n"
 report+="Summary includes unresolved bindings, duplicate counts and outstanding exact-record approval. Existing cleaning artifacts are hash-verified and unmodified. Workbook SHA-256: "+hashlib.sha256(target.read_bytes()).hexdigest()+".\n\n"
 report+="Validation: PYTHONDONTWRITEBYTECODE=1 python3 tools/excel_cleaning/validate_review.py\n\nValidator compares all generated sheets to deterministic manifest-derived proposals and checks every row, duplicate membership, blank initial decisions, formula safety and input hashes. It validates the pristine generated workbook, not administrator-edited workbooks or real database FKs. Edited decisions require a future separately reviewed validation/approval workflow. Preparation refuses to overwrite an existing review file. No Django model full_clean/database validation or import readiness is claimed.\n"
 with (OUT/"import_mapping_report.md").open("x") as f:f.write(report)
 print(json.dumps({"equipment_records":897,"product_evidence_groups":len(sheets["Product groups"])-1,"confident_product_mappings":0,"administrator_decisions_required":897,"counts":dict(counts)}))
if __name__=="__main__":main()
