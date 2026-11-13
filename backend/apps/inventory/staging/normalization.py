"""Versioned preparation proposals. Unknown facts stay unresolved; no master writes."""
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from .common import StagingError, digest

VERSION = "phase3a1-rules-v1"
REFERENCE_DATE = date(2026, 11, 13)
CONDITIONS = {"new": "NEW", "used": "USED", "broken": "BROKEN"}
CATEGORIES = {
    "hdd": "DISK_HDD", "ssd": "DISK_SSD", "ram": "MEMORY", "fan": "FAN",
    "network interface controller": "NETWORK_ADAPTER", "ndc": "NETWORK_ADAPTER",
    "controller": "CONTROLLER", "power supply": "POWER_SUPPLY",
    "smart storage battery": "BATTERY", "raid controller battery": "BATTERY",
    "lan cable": "CABLE",
}
BRANDS = (
    "HP", "HPE", "Dell", "Dell EMC", "HGST", "HITACHI", "IBM", "Lenovo",
    "Seagate", "Samsung", "Intel", "EMC", "Sun Oracle", "QLogic", "SK Hynix",
    "AVC", "Nidec Ultraflow", "SANYO DENKI",
)
MANUFACTURERS = {b.casefold(): b for b in BRANDS}
MANUFACTURERS["sky hynix"] = "SK Hynix"
RULES = {
    "version": VERSION, "conditions": CONDITIONS, "categories": CATEGORIES,
    "manufacturers": MANUFACTURERS, "binding_policy": "proposals-only-no-approved-masters",
    "quantity": "positive-integral-explicit-piece-candidate",
    "locations": "unresolved-until-physical-binding",
    "specifications": "dimension-specific-proposals-no-byte-conversion",
}
LABELS = ("BLOCKED", "NEEDS_CLARIFICATION", "READY_FOR_REVIEW", "EXCLUDED_WITH_REASON")


def review_label(issues, *, exclusion_requested=False):
    # Exclusion requires a future reviewed workflow. No CLI/service accepts it here.
    if exclusion_requested:
        raise StagingError("EXCLUSION_NOT_ENABLED")
    if any(i["severity"] == "BLOCKING" for i in issues):
        return "BLOCKED"
    if any(i["severity"] == "CLARIFICATION" for i in issues):
        return "NEEDS_CLARIFICATION"
    return "READY_FOR_REVIEW"


def quantity_proposal(value):
    if value is None or not value.strip():
        return None, None, "MISSING_QUANTITY"
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?\s+(?i:box|plastic)", value.strip()):
        return None, None, "PACKAGE_UNIT"
    try:
        number = Decimal(value.strip())
    except InvalidOperation:
        return None, None, "INVALID_QUANTITY"
    if (not number.is_finite() or number <= 0 or number != number.to_integral_value()
            or number > 9223372036854775807):
        return None, None, "INVALID_QUANTITY"
    return int(number), "PIECE", None


def decimal_text(value):
    return format(Decimal(value).normalize(), "f")


def typed_specifications(fields):
    result = {}
    for field in ("Capacity", "Speed", "Size", "Type", "DDR", "Host Int", "Ports"):
        raw = fields.get(field)
        if raw is None or raw.strip().casefold() in ("", "n/a"):
            result[field] = {"value": None, "reason": "NOT_RECORDED_OR_NOT_APPLICABLE"}
            continue
        item = {"raw": raw, "value": None, "reason": "UNRESOLVED"}
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(W|Wh|[Vv])", raw.strip())
        if field == "Capacity" and match:
            item.update(value=decimal_text(match[1]), unit=match[2].upper(),
                        dimension={"W": "POWER", "WH": "ENERGY", "V": "VOLTAGE"}[match[2].upper()],
                        reason="PROPOSED_UNIT_NOT_VERIFIED")
        elif field == "DDR" and raw in ("DDR3", "DDR4", "DDR5"):
            item.update(value=raw, reason="PROPOSED_MEMORY_GENERATION")
        elif field == "Speed" and raw in ("7.2K", "10K", "15K"):
            item.update(value=decimal_text(Decimal(raw[:-1]) * 1000),
                        unit="RPM", reason="PROPOSED_ROTATIONAL_RATE")
        elif field == "Speed" and re.fullmatch(r"[0-9]+(?:\.[0-9]+)? Gbps", raw):
            item.update(value=decimal_text(raw.split()[0]), unit="Gbit/s",
                        reason="PROPOSED_LINK_RATE")
        elif field == "Size" and re.fullmatch(r"[0-9]+(?:\.[0-9]+)? Inch", raw):
            item.update(value=decimal_text(raw.split()[0]), unit="inch",
                        reason="PROPOSED_FORM_FACTOR")
        elif field == "Ports" and raw.startswith("2 xSFP+"):
            item.update(value=2, unit="port", reason="PROPOSED_CONNECTOR_COUNT")
        result[field] = item
    return result


def preview(manifest):
    """Pure function: returns preparation artifact, never accepts review/approval inputs."""
    if digest(manifest["layout"]) != manifest["layout_digest"]:
        raise StagingError("MANIFEST_INTEGRITY_FAILURE")
    seen = set()
    for row in manifest["rows"]:
        payload = {k: row[k] for k in ("domain", "workbook_sha256", "worksheet_name",
                   "excel_row_number", "section_header", "raw_cells")}
        key = (row["worksheet_name"], row["excel_row_number"])
        if (key in seen or row["workbook_sha256"] != manifest["workbook_sha256"] or
                digest(payload) != row["source_row_digest"]):
            raise StagingError("MANIFEST_INTEGRITY_FAILURE")
        seen.add(key)
    groups = defaultdict(list)
    for row in manifest["rows"]:
        if row["classification"] == "CANDIDATE":
            fields = {c["header"]: c["value"] for c in row["raw_cells"] if c["header"]}
            key = (fields.get("Serial Number") or "").strip().casefold()
            if key and key not in ("no sn", "n/a"):
                groups[key].append(row["source_row_digest"])
    duplicate_ids = {d for ids in groups.values() if len(ids) > 1 for d in ids}
    prepared = []
    for row in manifest["rows"]:
        if row["classification"] != "CANDIDATE":
            prepared.append({**row, "preparation": {"label": None, "issues": [],
                              "reason": row["classification"]}})
            continue
        fields = {c["header"]: c["value"] for c in row["raw_cells"] if c["header"]}
        coords = {c["header"]: c["coordinate"] for c in row["raw_cells"] if c["header"]}
        issues = []
        def issue(code, field, severity="BLOCKING"):
            item = {"code": code, "field": field, "coordinate": coords.get(field),
                    "worksheet_name": row["worksheet_name"],
                    "excel_row_number": row["excel_row_number"], "severity": severity}
            if item not in issues:
                issues.append(item)
        name = fields.get("Device Name") or fields.get("Column 1")
        role = name or fields.get("Device Category")
        brand = fields.get("Manufacturer") or fields.get("Manufacture")
        category = CATEGORIES.get((role or "").strip().casefold())
        manufacturer = MANUFACTURERS.get((brand or "").strip().casefold())
        condition = CONDITIONS.get((fields.get("Condition") or "").strip().casefold())
        quantity, unit, qcode = quantity_proposal(fields.get("Qty"))
        if qcode:
            issue(qcode, "Qty", "BLOCKING" if qcode != "MISSING_QUANTITY" else "CLARIFICATION")
        if row["source_row_digest"] in duplicate_ids:
            issue("SERIAL_DUPLICATE", "Serial Number")
        serial = fields.get("Serial Number")
        if re.match(r"(p/?n|dp/n)[: ]", serial or "", re.I):
            issue("PART_LIKE_ID", "Serial Number")
        if not serial or serial.strip().casefold() in ("no sn", "n/a"):
            issue("SERIAL_IDENTITY_PENDING", "Serial Number", "CLARIFICATION")
        status = fields.get("Status")
        if status == "Hand Over":
            issue("HANDOVER", "Status")
        if status not in ("In Stock", "Hand Over"):
            issue("UNKNOWN_STATUS", "Status", "CLARIFICATION")
        audit_date = None
        if fields.get("Last Audit Date"):
            try:
                number = Decimal(fields["Last Audit Date"])
                if not number.is_finite() or number != number.to_integral_value() or number <= 0 or number == 60:
                    raise ValueError
                days = int(number)
                # Excel 1900 leap-year bug affects serials below 60.
                audit_date = date(1899, 12, 30) + timedelta(days=days + (1 if days < 60 else 0))
                if audit_date > REFERENCE_DATE:
                    issue("FUTURE_AUDIT_DATE", "Last Audit Date")
            except (InvalidOperation, ValueError, OverflowError):
                issue("INVALID_AUDIT_DATE", "Last Audit Date")
        sheet, n = row["worksheet_name"], row["excel_row_number"]
        if (sheet == "Power Supply" or sheet == "Rack 856" and 56 <= n <= 75 or
                sheet == "Rack 7" and n == 3):
            issue("LOCATION_CONFLICT", "Location")
        if (sheet == "Rack 845" and n == 2 or fields.get("Capacity") in ("6GB", "6G")):
            issue("SPEC_CONFLICT", "Capacity")
        if not name:
            issue("MISSING_DEVICE_NAME", "Device Name", "CLARIFICATION")
        if not category:
            issue("UNKNOWN_CATEGORY", "Device Category", "CLARIFICATION")
        if not manufacturer:
            issue("UNKNOWN_MANUFACTURER", "Manufacturer", "CLARIFICATION")
        if not condition:
            issue("UNKNOWN_CONDITION", "Condition", "CLARIFICATION")
        # No physical location, SKU, catalog or tracking binding has been approved.
        for code, field in (
                ("PRODUCT_MAPPING_PENDING", "Device Name"),
                ("TRACKING_MAPPING_PENDING", "Device Category"),
                ("LOCATION_MAPPING_PENDING", "Location"),
                ("MAPPING_POLICY_PENDING", "Device Category")):
            issue(code, field, "CLARIFICATION")
        for c in row["raw_cells"]:
            if (c["xml_type"] in ("e", "b", "d") or
                    c["xml_type"] == "n" and c["value"] is not None and
                    not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?", c["value"])):
                issue("UNSUPPORTED_FIELD_TYPE", c["header"])
            if c["formula"]:
                if c["value"] is None:
                    issue("FORMULA_CACHE_MISSING", c["header"])
                issue("FORMULA_CACHE_UNVERIFIED", c["header"], "CLARIFICATION")
        issues.sort(key=lambda i: (i["code"], i["coordinate"] or "", i["field"] or ""))
        tracking = ("SERIALIZED" if category in (
            "DISK_HDD", "DISK_SSD", "MEMORY", "NETWORK_ADAPTER", "CONTROLLER",
            "POWER_SUPPLY", "BATTERY") else None)
        state = ("QUARANTINED" if condition in ("UNKNOWN", "BROKEN")
                 else "AVAILABLE" if condition and status == "In Stock" else None)
        proposal = {
            "manufacturer": manufacturer, "category": category,
            "product_model": None, "sku": None, "tracking_mode": tracking,
            "condition": condition, "lifecycle_state": state,
            "quantity": quantity, "quantity_unit": unit,
            "warehouse": None, "location": None,
            "legacy_audit_date": audit_date.isoformat() if audit_date else None,
            "serial_raw": serial, "specifications": typed_specifications(fields),
            "binding_status": "UNRESOLVED_PROPOSALS_ONLY", "rule_version": VERSION,
        }
        prepared.append({**row, "preparation": {"label": review_label(issues),
                          "issues": issues, "proposal": proposal}})
    result = {
        "domain": "itw.preparation-preview.v1", "manifest": manifest,
        "manifest_digest": digest(manifest), "normalization_version": VERSION,
        "dictionary_digest": digest(RULES), "validation_reference_date": REFERENCE_DATE.isoformat(),
        "runtime": {"python": list(sys.version_info[:2]), "unicode": unicodedata.unidata_version},
        "rows": prepared, "approval_enabled": False, "posting_enabled": False,
    }
    result["preview_digest"] = digest(result)
    return result


def aggregate(result):
    rows = [r for r in result["rows"] if r["classification"] == "CANDIDATE"]
    labels = Counter(r["preparation"]["label"] for r in rows)
    codes = Counter(i["code"] for r in rows for i in r["preparation"]["issues"])
    return {"source_counts": result["manifest"]["counts"],
            "review_labels": {label: labels[label] for label in LABELS},
            "exception_counts": dict(sorted(codes.items())),
            "approved_rows": 0, "posting_outcomes": 0}
