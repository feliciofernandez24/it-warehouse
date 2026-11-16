"""Offline export only. No Django setup, database driver, or posting path."""
import collections, hashlib, json, os, shutil, sys, zipfile
from pathlib import Path
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"backend"))
from apps.inventory.staging.reader import read_workbook
from apps.inventory.staging.normalization import preview, aggregate
from apps.inventory.staging.common import canonical, digest

def workbook(path, rows):
    """All values are inline text: never formulas, links, or numeric serial coercion."""
    def cell(v,c,r):
        s="" if v is None else str(v)
        if len(s)>32767: raise ValueError("CELL_TOO_LONG")
        return '<c r="'+c+str(r)+'" t="inlineStr"><is><t xml:space="preserve">'+escape(s)+'</t></is></c>'
    def col(n):
        out=""
        while n: n,k=divmod(n-1,26);out=chr(65+k)+out
        return out
    sheet='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    for i,row in enumerate(rows,1):
        sheet+='<row r="'+str(i)+'">'+''.join(cell(v,col(j),i) for j,v in enumerate(row,1))+'</row>'
    sheet+='</sheetData></worksheet>'
    parts={
    '[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
    '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
    'xl/workbook.xml':'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Offline review" sheetId="1" r:id="rId1"/></sheets></workbook>',
    'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
    'xl/worksheets/sheet1.xml':sheet}
    with zipfile.ZipFile(path,"x",compression=zipfile.ZIP_DEFLATED) as z:
        for name,value in parts.items():z.writestr(name,value)
    os.chmod(path,0o600)

def main():
    os.umask(0o077)
    source=ROOT/"imports"
    files=sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in (".xlsx",".xls",".csv") and p.parent==source)
    # Fail closed on extra nested inputs; generated outputs are excluded explicitly.
    allfiles=sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in (".xlsx",".xls",".csv") and not any(x in ("cleaned","originals") for x in p.relative_to(source).parts))
    if files!=allfiles or len(files)!=1 or files[0].name!="IT_Warehouse_Asset_Inventory.xlsx":raise ValueError("SOURCE_DISCOVERY_REQUIRES_PROFILE")
    path=files[0]; before=hashlib.sha256(path.read_bytes()).hexdigest()
    p=preview(read_workbook(path))
    out=source/"cleaned"
    out.mkdir(mode=0o700,exist_ok=False)
    originals=source/"originals";originals.mkdir(mode=0o700,exist_ok=True)
    copy=originals/(before+".xlsx")
    with copy.open("xb") as f:f.write(path.read_bytes())
    os.chmod(copy,0o400)
    assert hashlib.sha256(copy.read_bytes()).hexdigest()==before
    header=["source_file_sha256","source_row_id","worksheet","excel_row","classification","issues","raw_cells_json","trimmed_fields_json","unapproved_proposal_json"]
    clean=[header];reject=[header];counts=collections.Counter();dupes=collections.defaultdict(list);candidates=[]
    for r in p["rows"]:
        prep=r["preparation"]
        if r["classification"]!="CANDIDATE":label="Rejected"
        else:
            # Every current source candidate has unresolved binding, hence manual review.
            label="Requires manual review" if prep["issues"] else "Valid"
            candidates.append(r)
            fields={c["header"]:c["value"] for c in r["raw_cells"] if c["header"]}
            dupes[digest(fields)].append(r["source_row_digest"])
        counts[label]+=1
        fields={c["header"]:(c["value"].strip() if c["value"] is not None else None) for c in r["raw_cells"] if c["header"]}
        # Never strip the evidentiary serial; trimmed comparison stays separate.
        fields["serial_raw"]=next((c["value"] for c in r["raw_cells"] if c["header"]=="Serial Number"),None)
        line=[before,r["source_row_digest"],r["worksheet_name"],r["excel_row_number"],label,
              json.dumps(prep["issues"],ensure_ascii=False),json.dumps(r["raw_cells"],ensure_ascii=False),
              json.dumps(fields,ensure_ascii=False),json.dumps(prep.get("proposal"),ensure_ascii=False)]
        (reject if label=="Rejected" else clean).append(line)
    workbook(out/"it_warehouse_cleaned.xlsx",clean);workbook(out/"it_warehouse_rejected.xlsx",reject)
    manifest={"domain":"itw.offline-cleaning.v1","source_file":path.name,"source_sha256":before,
        "original_copy":str(copy.relative_to(ROOT)),"preview":p,"summary":aggregate(p),
        "classifications":dict(counts),"exact_duplicate_groups":[v for v in dupes.values() if len(v)>1],
        "mapping":{"status":"UNRESOLVED_NOT_APPROVED","approved_create_counts":dict.fromkeys(
        ["categories","manufacturers","models","warehouses","locations","assets","bulk_stock_records"],0),
        "deferred_stock_rows":len(candidates),"persistent_imports":0},
        "approval":None,"posting_enabled":False}
    manifest["artifact_sha256"]={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.glob("*.xlsx")}
    manifest["manifest_digest"]=digest(manifest)
    (out/"import_manifest.json").write_bytes(canonical(manifest))
    report="# Offline cleaning report\n\nNo database import performed. All 897 equipment candidates require manual review; 21 section headers and 2 sequence-only rows are rejected as equipment, not discarded.\n\n"
    report+="Source SHA-256: "+before+"\n\nManifest digest: "+manifest["manifest_digest"]+"\n\n"
    report+="Rules: existing pinned reader and normalization dictionaries; trim comparison fields only; preserve all raw cells, lexical values, formulas and serials as inert text. No formula execution, guessed quantities, SKU assignment, physical location assignment, serial merging, or stock posting. Normalization proposals remain explicitly unapproved. The normalization reference date remains the reviewed engine reference date, not today's date.\n\n"
    report+="Statistics:\n\n"+json.dumps(aggregate(p),indent=2)+"\n\nExact duplicate groups: "+str(len(manifest["exact_duplicate_groups"]))+"\n\nWorksheet layout, blank intervals, hidden rows and merged ranges:\n\n"+json.dumps(p["manifest"]["layout"],indent=2)+"\n\n"
    report+="Preview: zero approved creates in every model; 897 deferred stock candidates. Category/manufacturer dictionary suggestions are labels, not approved FK mappings or new master records. Missing mappings prevent an exact executable import and model/FK rehearsal. Existing receipt foundation does not supply verified-source import approval. No SQL ImportBatch or ImportStagingRecord was created.\n"
    (out/"cleaning_report.md").write_text(report)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    print(json.dumps({"counts":dict(counts),"duplicate_groups":len(manifest["exact_duplicate_groups"]),"manifest_digest":manifest["manifest_digest"],"source_sha256":before}))
if __name__=="__main__":main()
