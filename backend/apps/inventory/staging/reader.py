"""Bounded OOXML reader. Never extracts archives or evaluates formula content."""
import hashlib
import io
import posixpath
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from . import profile
from .common import StagingError, digest

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass(frozen=True)
class Limits:
    archive_bytes: int = 16 * 1024 * 1024
    expanded_bytes: int = 64 * 1024 * 1024
    member_bytes: int = 8 * 1024 * 1024
    members: int = 256
    rows: int = 10000
    columns: int = 64
    cells: int = 250000
    string: int = 32767
    xml_nodes: int = 500000
    shared_strings: int = 50000


def fail(code):
    raise StagingError(code)


def column_number(label):
    number = 0
    for char in label:
        number = number * 26 + ord(char) - 64
    return number


def column_label(number):
    out = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        out = chr(65 + remainder) + out
    return out


def coordinate(value, limits):
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", value or "")
    if not match:
        fail("INVALID_COORDINATE")
    col, row = column_number(match[1]), int(match[2])
    if col > limits.columns or row > limits.rows:
        fail("DIMENSION_LIMIT")
    return col, row


def safe_xml(data, limits):
    # Reject UTF-16, entity declarations and DTDs before the XML parser.
    if b"\0" in data or re.search(br"<!\s*(DOCTYPE|ENTITY)", data, re.I):
        fail("UNSAFE_XML")
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        fail("MALFORMED_XML")
    nodes = 0
    for node in root.iter():
        nodes += 1
        if nodes > limits.xml_nodes:
            fail("XML_NODE_LIMIT")
        if len(node.text or "") > limits.string or any(
                len(v) > limits.string for v in node.attrib.values()):
            fail("STRING_LIMIT")
    return root


def _package(blob, limits):
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
        infos = z.infolist()
        if len(infos) > limits.members:
            fail("ARCHIVE_LIMIT")
        names = [i.filename for i in infos]
        if len(names) != len(set(n.casefold() for n in names)):
            fail("DUPLICATE_MEMBER")
        if sum(i.file_size for i in infos) > limits.expanded_bytes:
            fail("EXPANDED_LIMIT")
        roots = {}
        for info in infos:
            name = info.filename
            if (not name or "\\" in name or ":" in name or
                    any(p in ("", ".", "..") for p in name.split("/")) or
                    name.startswith("/") or info.flag_bits & 1 or
                    (info.external_attr >> 16) & 0o170000 == 0o120000):
                fail("UNSAFE_ARCHIVE_PATH")
            if info.file_size > limits.member_bytes:
                fail("MEMBER_LIMIT")
            allowed = re.fullmatch(
                r"(\[Content_Types\]\.xml|_rels/\.rels|"
                r"xl/(workbook\.xml|styles\.xml|sharedStrings\.xml|"
                r"_rels/workbook\.xml\.rels|theme/theme[0-9]+\.xml|"
                r"persons/person\.xml|tables/table[0-9]+\.xml|"
                r"drawings/drawing[0-9]+\.xml|worksheets/sheet[0-9]+\.xml|"
                r"worksheets/_rels/sheet[0-9]+\.xml\.rels))", name)
            if not allowed:
                fail("UNSUPPORTED_MEMBER")
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                fail("UNSUPPORTED_COMPRESSION")
            with z.open(info) as stream:
                data = stream.read(limits.member_bytes + 1)
            if len(data) != info.file_size:
                fail("MEMBER_LIMIT")
            roots[name] = safe_xml(data, limits)
        return roots
    except StagingError:
        raise
    except (zipfile.BadZipFile, KeyError, OSError, RuntimeError, ValueError, EOFError):
        fail("INVALID_ARCHIVE")


def _relationships(roots):
    resolved = {}
    suffixes = {"worksheet", "styles", "sharedStrings", "theme", "person",
                "table", "drawing", "officeDocument"}
    for name, root in roots.items():
        if not name.endswith(".rels"):
            continue
        if root.tag != "{" + PKG + "}Relationships":
            fail("INVALID_RELATIONSHIPS")
        base = "" if name == "_rels/.rels" else name.split("/_rels/")[0]
        result = {}
        for item in root:
            rid, target = item.get("Id"), item.get("Target", "")
            kind = item.get("Type", "")
            if (item.tag != "{" + PKG + "}Relationship" or not rid or
                    rid in result or item.get("TargetMode") not in (None, "Internal") or
                    not (kind.startswith(REL + "/") or kind ==
                         "http://schemas.microsoft.com/office/2017/10/relationships/person") or
                    kind.rsplit("/", 1)[-1] not in suffixes):
                fail("UNSAFE_RELATIONSHIP")
            if (not target or "\\" in target or ":" in target or target.startswith("/") or
                    any(p in ("", ".") for p in target.split("/"))):
                fail("UNSAFE_RELATIONSHIP")
            path = posixpath.normpath(posixpath.join(base, target))
            if not (path == "xl/workbook.xml" or path.startswith("xl/")):
                fail("UNSAFE_RELATIONSHIP")
            if path not in roots:
                fail("MISSING_RELATIONSHIP_TARGET")
            result[rid] = (path, kind.rsplit("/", 1)[-1])
        resolved[name] = result
    if list(resolved.get("_rels/.rels", {}).values()) != [("xl/workbook.xml", "officeDocument")]:
        fail("INVALID_WORKBOOK_ROOT")
    return resolved


def read_workbook(path, *, expected_sha256=profile.SHA256, headers=None,
                  expected_counts=None, sequence_rows=None, limits=Limits()):
    """Internal profile injection is for synthetic tests; CLI always pins production profile."""
    headers = profile.HEADERS if headers is None else headers
    expected_counts = profile.COUNTS if expected_counts is None else expected_counts
    sequence_rows = profile.SEQUENCE_ROWS if sequence_rows is None else sequence_rows
    try:
        with Path(path).open("rb") as stream:
            blob = stream.read(limits.archive_bytes + 1)
    except OSError:
        fail("SOURCE_UNREADABLE")
    if len(blob) > limits.archive_bytes:
        fail("ARCHIVE_LIMIT")
    actual = hashlib.sha256(blob).hexdigest()
    if not re.fullmatch("[0-9a-f]{64}", expected_sha256 or "") or actual != expected_sha256:
        fail("HASH_MISMATCH")
    roots = _package(blob, limits)
    relationships = _relationships(roots)
    workbook = roots.get("xl/workbook.xml")
    types = roots.get("[Content_Types].xml")
    if workbook is None or types is None or workbook.tag != "{" + NS + "}workbook":
        fail("INVALID_WORKBOOK")
    for item in types:
        kind = item.get("ContentType", "").lower()
        if any(token in kind for token in ("macro", "vba", "ole", "external", "binary")):
            fail("UNSAFE_CONTENT_TYPE")
    if any(n.tag.rsplit("}", 1)[-1] in (
            "externalReferences", "pivotCaches", "connections")
           for n in workbook):
        fail("UNSUPPORTED_WORKBOOK")
    defined = workbook.find("{" + NS + "}definedNames")
    if defined is not None and any(n.get("name") != "_xlnm._FilterDatabase" for n in defined):
        fail("UNSUPPORTED_DEFINED_NAME")
    props = workbook.find("{" + NS + "}workbookPr")
    epoch = "1904" if props is not None and props.get("date1904") in ("1", "true") else "1900"
    if epoch != "1900":
        fail("UNSUPPORTED_DATE_SYSTEM")
    shared = []
    if "xl/sharedStrings.xml" in roots:
        for item in roots["xl/sharedStrings.xml"]:
            value = "".join(t.text or "" for t in item.iter("{" + NS + "}t"))
            if len(value) > limits.string:
                fail("STRING_LIMIT")
            shared.append(value)
            if len(shared) > limits.shared_strings:
                fail("SHARED_STRING_LIMIT")
    sheet_container = workbook.find("{" + NS + "}sheets")
    if sheet_container is None:
        fail("UNKNOWN_WORKSHEETS")
    sheets = list(sheet_container)
    if [s.get("name") for s in sheets] != list(headers):
        fail("UNKNOWN_WORKSHEETS")
    records, layouts, used_paths = [], [], set()
    cell_count = 0
    for ordinal, sheet in enumerate(sheets):
        name = sheet.get("name")
        if sheet.get("state", "visible") != "visible":
            fail("UNSUPPORTED_HIDDEN_SHEET")
        rid = sheet.get("{" + REL + "}id")
        path, kind = relationships.get("xl/_rels/workbook.xml.rels", {}).get(rid, ("", ""))
        if kind != "worksheet" or path in used_paths:
            fail("INVALID_SHEET_RELATIONSHIP")
        used_paths.add(path)
        root = roots[path]
        if root.tag != "{" + NS + "}worksheet":
            fail("INVALID_WORKSHEET")
        if any(n.tag.rsplit("}", 1)[-1] in ("extLst", "oleObjects", "controls")
               for n in root):
            fail("UNSUPPORTED_WORKSHEET")
        dim = root.find("{" + NS + "}dimension")
        if dim is not None:
            for end in dim.get("ref", "").split(":"):
                coordinate(end, limits)
        merged = [m.get("ref", "") for m in root.findall(
            "{" + NS + "}mergeCells/{" + NS + "}mergeCell")]
        for ref in merged:
            for end in ref.split(":"):
                coordinate(end, limits)
        layout = {"worksheet_name": name, "ordinal": ordinal,
                  "merged_ranges": merged, "blank_intervals": [], "hidden_rows": []}
        data = root.find("{" + NS + "}sheetData")
        if data is None:
            fail("MISSING_SHEET_DATA")
        previous = 0
        current = None
        seen_headers = set()
        for row in data:
            try:
                number = int(row.get("r", "0"))
            except ValueError:
                fail("INVALID_COORDINATE")
            if number <= previous or number > limits.rows:
                fail("INVALID_ROW_ORDER")
            if row.get("hidden") in ("1", "true"):
                layout["hidden_rows"].append(number)
            if number > previous + 1:
                layout["blank_intervals"].append([previous + 1, number - 1])
            previous = number
            cells = {}
            last_col = 0
            for c in row:
                if c.tag != "{" + NS + "}c":
                    fail("UNSUPPORTED_ROW")
                col, cell_row = coordinate(c.get("r"), limits)
                if cell_row != number or col <= last_col:
                    fail("INVALID_CELL_ORDER")
                last_col = col
                cell_count += 1
                if cell_count > limits.cells:
                    fail("CELL_LIMIT")
                typ = c.get("t", "n")
                if typ not in ("n", "s", "inlineStr", "str", "b", "e", "d"):
                    fail("UNSUPPORTED_CELL_TYPE")
                v = c.find("{" + NS + "}v")
                f = c.find("{" + NS + "}f")
                inline = c.find("{" + NS + "}is")
                lexical = v.text if v is not None else None
                value = lexical
                if typ == "s":
                    if not re.fullmatch(r"[0-9]+", lexical or "") or int(lexical) >= len(shared):
                        fail("INVALID_SHARED_STRING")
                    value = shared[int(lexical)]
                elif typ == "inlineStr":
                    value = "".join(t.text or "" for t in inline.iter("{" + NS + "}t")) if inline is not None else ""
                if len(value or "") > limits.string:
                    fail("STRING_LIMIT")
                if f is not None and (f.attrib or not f.text):
                    fail("UNSUPPORTED_FORMULA")
                if any(child.tag.rsplit("}", 1)[-1] not in ("v", "f", "is") for child in c):
                    fail("UNSUPPORTED_CELL_STRUCTURE")
                cells[col] = {"coordinate": c.get("r"), "xml_type": typ,
                              "style": c.get("s"), "raw_lexical": lexical,
                              "value": value, "formula": f.text if f is not None else None,
                              "cached_value": lexical if f is not None else None,
                              "cached_type": typ if f is not None else None}
            populated = {column_label(k): c["value"] for k, c in cells.items()
                         if c["value"] is not None and c["value"].strip()}
            if not populated and not any(c["formula"] for c in cells.values()):
                continue
            if number in headers[name]:
                if populated != headers[name][number] or any(c["formula"] for c in cells.values()):
                    fail("UNKNOWN_SECTION")
                current = number
                seen_headers.add(number)
                classification = "HEADER"
            else:
                if current is None or any(v in ("Device Name", "Device Category") for v in populated.values()):
                    fail("UNKNOWN_SECTION")
                if any(column_number(k) > len(headers[name][current]) for k in populated):
                    fail("UNEXPECTED_COLUMN")
                classification = "SEQUENCE_ONLY" if (name, number) in sequence_rows else "CANDIDATE"
                if classification == "SEQUENCE_ONLY" and (
                        len(populated) != 1 or headers[name][current].get(next(iter(populated))) != "No"):
                    fail("CLASSIFICATION_MISMATCH")
                if classification == "CANDIDATE" and not any(
                        headers[name][current].get(k) in ("Device Name", "Column 1", "Device Category")
                        for k in populated):
                    fail("CLASSIFICATION_MISMATCH")
            header = headers[name][current]
            width = max(len(header), max(cells, default=0))
            raw_cells = []
            for col in range(1, width + 1):
                cell = cells.get(col, {"coordinate": column_label(col) + str(number),
                                     "xml_type": None, "style": None, "raw_lexical": None,
                                     "value": None, "formula": None, "cached_value": None,
                                     "cached_type": None})
                raw_cells.append({**cell, "header": header.get(column_label(col))})
            section = {"excel_row_number": current, "headers": header}
            payload = {"domain": "itw.source-row.v1", "workbook_sha256": actual,
                       "worksheet_name": name, "excel_row_number": number,
                       "section_header": section, "raw_cells": raw_cells}
            records.append({**payload, "source_row_digest": digest(payload),
                            "classification": classification})
        if seen_headers != set(headers[name]):
            fail("MISSING_SECTION")
        layouts.append(layout)
    worksheet_parts = {p for p in roots if re.fullmatch(r"xl/worksheets/sheet[0-9]+\.xml", p)}
    if used_paths != worksheet_parts:
        fail("ORPHAN_WORKSHEET")
    counts = dict(Counter(r["classification"] for r in records))
    counts.update(worksheets=len(sheets), populated=len(records))
    if counts != expected_counts:
        fail("RECONCILIATION_MISMATCH")
    return {"domain": "itw.source-manifest.v1", "workbook_sha256": actual,
            "layout_version": profile.VERSION, "date_system": epoch,
            "source_timezone": "Asia/Tokyo", "layout": layouts,
            "layout_digest": digest(layouts), "counts": counts, "rows": records}
