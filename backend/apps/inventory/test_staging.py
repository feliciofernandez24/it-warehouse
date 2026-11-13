"""Synthetic fixtures only. Real inventory never enters tests or Git."""
import copy
import hashlib
import io
import json
import os
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from apps.inventory.staging.common import StagingError, canonical, digest
from apps.inventory.staging.normalization import (
    aggregate, preview, quantity_proposal, review_label, typed_specifications,
)
from apps.inventory.staging.reader import Limits, NS, REL, PKG, read_workbook
from apps.inventory.staging.storage import capture

HEADER = {
    "A": "Device Name", "B": "Device Category", "C": "Manufacturer",
    "D": "Serial Number", "E": "Status", "F": "Condition", "G": "Qty",
    "H": "Location", "I": "Last Audit Date", "J": "Capacity",
}
COUNTS = {"worksheets": 1, "populated": 3, "HEADER": 1, "CANDIDATE": 2}
SOURCE_ROW = {
    "A": "RAM", "B": "Server", "C": "HP", "D": "000123",
    "E": "In Stock", "F": "New", "G": "1.0", "H": "SYNTHETIC-AREA",
    "I": "46171", "J": "16GB",
}


def cells(number, values, overrides=None):
    result = []
    for col, value in values.items():
        body = '<is><t>' + escape(value) + '</t></is>'
        typ = "inlineStr"
        if overrides and col in overrides:
            typ, body = overrides[col]
        result.append(f'<c r="{col}{number}" t="{typ}">{body}</c>')
    return '<row r="' + str(number) + '">' + "".join(result) + "</row>"


def package(*, second=None, overrides=None):
    second = SOURCE_ROW if second is None else second
    sheet = (f'<worksheet xmlns="{NS}"><dimension ref="A1:J3"/><sheetData>' +
             cells(1, HEADER) + cells(2, SOURCE_ROW, overrides) +
             cells(3, second) + '</sheetData></worksheet>')
    return {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        "_rels/.rels": f'<Relationships xmlns="{PKG}"><Relationship Id="root" Type="{REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<workbook xmlns="{NS}" xmlns:r="{REL}"><sheets><sheet name="Synthetic" sheetId="1" r:id="s1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<Relationships xmlns="{PKG}"><Relationship Id="s1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": sheet,
    }


def zipped(parts):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return stream.getvalue()


def parse_blob(blob, **kwargs):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "synthetic.xlsx"
        path.write_bytes(blob)
        return read_workbook(path, expected_sha256=hashlib.sha256(blob).hexdigest(),
                             headers={"Synthetic": {1: HEADER}}, expected_counts=COUNTS,
                             sequence_rows=set(), **kwargs)


def manifest(**kwargs):
    return parse_blob(zipped(package(**kwargs)))


class ReaderTests(SimpleTestCase):
    def test_deterministic_manifest_and_original_unchanged(self):
        data = zipped(package())
        self.assertEqual(canonical(parse_blob(data)), canonical(parse_blob(data)))

    def test_exact_classification_coordinates_and_header(self):
        result = manifest()
        self.assertEqual(result["counts"], COUNTS)
        self.assertEqual([r["classification"] for r in result["rows"]],
                         ["HEADER", "CANDIDATE", "CANDIDATE"])
        row = result["rows"][1]
        self.assertEqual(row["excel_row_number"], 2)
        self.assertEqual(row["raw_cells"][3]["coordinate"], "D2")
        self.assertEqual(row["section_header"]["excel_row_number"], 1)

    def test_leading_zero_and_numeric_lexical_preservation(self):
        result = manifest(overrides={"D": ("n", "<v>000123</v>")})
        cell = result["rows"][1]["raw_cells"][3]
        self.assertEqual(cell["value"], "000123")
        self.assertEqual(cell["raw_lexical"], "000123")
        self.assertEqual(cell["xml_type"], "n")

    def test_formula_and_cache_preserved_without_execution(self):
        result = manifest(overrides={"H": ("str", "<f>UNTRUSTED()</f><v>SYNTHETIC-CACHE</v>")})
        cell = result["rows"][1]["raw_cells"][7]
        self.assertEqual(cell["formula"], "UNTRUSTED()")
        self.assertEqual(cell["cached_value"], "SYNTHETIC-CACHE")
        self.assertIn("FORMULA_CACHE_UNVERIFIED", aggregate(preview(result))["exception_counts"])

    def test_missing_formula_cache_blocks(self):
        result = manifest(overrides={"H": ("str", "<f>UNTRUSTED()</f>")})
        self.assertIn("FORMULA_CACHE_MISSING", aggregate(preview(result))["exception_counts"])

    def test_shared_string_identity(self):
        parts = package(overrides={"D": ("s", "<v>0</v>")})
        parts["xl/sharedStrings.xml"] = f'<sst xmlns="{NS}"><si><t>000123</t></si></sst>'
        row = parse_blob(zipped(parts))["rows"][1]
        self.assertEqual(row["raw_cells"][3]["value"], "000123")
        self.assertEqual(row["raw_cells"][3]["raw_lexical"], "0")

    def test_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "source.xlsx"
            path.write_bytes(zipped(package()))
            with self.assertRaisesRegex(StagingError, "^HASH_MISMATCH$"):
                read_workbook(path)

    def test_unknown_sheet_header_and_missing_section(self):
        for before, after, code in (
            ('name="Synthetic"', 'name="Other"', "UNKNOWN_WORKSHEETS"),
            ("Device Name", "Unexpected Header", "UNKNOWN_SECTION"),
        ):
            parts = {k: v.replace(before, after) for k, v in package().items()}
            with self.assertRaisesRegex(StagingError, "^" + code + "$"):
                parse_blob(zipped(parts))

    def test_reconciliation_mismatch(self):
        parts = package()
        parts["xl/worksheets/sheet1.xml"] = parts["xl/worksheets/sheet1.xml"].replace(
            cells(3, SOURCE_ROW), "")
        with self.assertRaisesRegex(StagingError, "RECONCILIATION_MISMATCH"):
            parse_blob(zipped(parts))

    def test_duplicate_cell_coordinate_rejected(self):
        parts = package()
        parts["xl/worksheets/sheet1.xml"] = parts["xl/worksheets/sheet1.xml"].replace(
            'r="B2"', 'r="A2"')
        with self.assertRaisesRegex(StagingError, "INVALID_CELL_ORDER"):
            parse_blob(zipped(parts))

    def test_digest_binds_coordinates_raw_and_formula(self):
        original = manifest()
        changed = manifest(overrides={"D": ("n", "<v>000123</v>")})
        self.assertNotEqual(original["rows"][1]["source_row_digest"],
                            changed["rows"][1]["source_row_digest"])
        payload = {k: v for k, v in original["rows"][1].items()
                   if k not in ("source_row_digest", "classification")}
        self.assertEqual(digest(payload), original["rows"][1]["source_row_digest"])
        payload["excel_row_number"] = 99
        self.assertNotEqual(digest(payload), original["rows"][1]["source_row_digest"])

    def test_resource_limits(self):
        blob = zipped(package())
        for limits, code in (
            (replace(Limits(), archive_bytes=10), "ARCHIVE_LIMIT"),
            (replace(Limits(), expanded_bytes=10), "EXPANDED_LIMIT"),
            (replace(Limits(), member_bytes=10), "MEMBER_LIMIT"),
            (replace(Limits(), members=1), "ARCHIVE_LIMIT"),
            (replace(Limits(), columns=2), "DIMENSION_LIMIT"),
            (replace(Limits(), rows=2), "DIMENSION_LIMIT"),
            (replace(Limits(), cells=2), "CELL_LIMIT"),
            (replace(Limits(), string=3), "STRING_LIMIT"),
            (replace(Limits(), xml_nodes=2), "XML_NODE_LIMIT"),
        ):
            with self.subTest(code=code):
                with self.assertRaisesRegex(StagingError, "^" + code + "$"):
                    parse_blob(blob, limits=limits)

    def test_unsafe_members_and_macros(self):
        for name in ("../escape.xml", "/absolute.xml", "xl\\bad.xml", "xl/vbaProject.bin",
                     "xl/externalLinks/externalLink1.xml", "xl/embeddings/object.bin"):
            parts = package()
            parts[name] = "<x/>"
            with self.subTest(name=name), self.assertRaises(StagingError):
                parse_blob(zipped(parts))

    def test_external_and_escape_relationship(self):
        for target, mode in (("https://example.invalid/data", ' TargetMode="External"'),
                             ("../../outside.xml", "")):
            parts = package()
            parts["xl/_rels/workbook.xml.rels"] = (
                f'<Relationships xmlns="{PKG}"><Relationship Id="s1" Type="{REL}/worksheet" '
                f'Target="{target}"{mode}/></Relationships>')
            with self.assertRaises(StagingError):
                parse_blob(zipped(parts))

    def test_xml_entities_and_malformed_archive(self):
        parts = package()
        parts["xl/styles.xml"] = '<!DOCTYPE x [<!ENTITY a "x">]><x>&a;</x>'
        with self.assertRaisesRegex(StagingError, "UNSAFE_XML"):
            parse_blob(zipped(parts))
        with self.assertRaisesRegex(StagingError, "INVALID_ARCHIVE"):
            parse_blob(b"not a zip")
        parts["xl/styles.xml"] = "<broken>"
        with self.assertRaisesRegex(StagingError, "MALFORMED_XML"):
            parse_blob(zipped(parts))

    def test_duplicate_members_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for name, body in package().items():
                archive.writestr(name, body)
            archive.writestr("XL/WORKBOOK.XML", "<x/>")
        with self.assertRaisesRegex(StagingError, "DUPLICATE_MEMBER"):
            parse_blob(stream.getvalue())

    def test_unsupported_type_and_shared_formula(self):
        for typ, body in (("unknown", "<v>x</v>"), ("str", '<f t="shared">x</f><v>x</v>')):
            with self.assertRaises(StagingError):
                manifest(overrides={"D": (typ, body)})

    def test_error_type_becomes_coordinate_exception(self):
        result = preview(manifest(overrides={"D": ("e", "<v>#VALUE!</v>")}))
        issues = result["rows"][1]["preparation"]["issues"]
        self.assertTrue(any(i["code"] == "UNSUPPORTED_FIELD_TYPE" and i["coordinate"] == "D2"
                            for i in issues))

    def test_hidden_rows_preserved_and_not_skipped(self):
        parts = package()
        parts["xl/worksheets/sheet1.xml"] = parts["xl/worksheets/sheet1.xml"].replace(
            '<row r="2">', '<row r="2" hidden="1">')
        result = parse_blob(zipped(parts))
        self.assertEqual(result["counts"], COUNTS)
        self.assertEqual(result["layout"][0]["hidden_rows"], [2])


class NormalizationTests(SimpleTestCase):
    def test_tampered_manifest_and_duplicate_source_refused(self):
        for field in ("raw", "layout", "duplicate"):
            value = manifest()
            if field == "raw":
                value["rows"][1]["raw_cells"][3]["value"] = "tampered"
            elif field == "layout":
                value["layout"][0]["ordinal"] = 7
            else:
                value["rows"].append(value["rows"][1])
            with self.assertRaisesRegex(StagingError, "MANIFEST_INTEGRITY_FAILURE"):
                preview(value)

    def test_duplicate_detection_no_merging(self):
        result = preview(manifest())
        self.assertEqual(aggregate(result)["exception_counts"]["SERIAL_DUPLICATE"], 2)
        self.assertEqual(len(result["rows"]), 3)

    def test_condition_unknown_stays_null(self):
        second = {**SOURCE_ROW, "D": "SYN-OTHER", "F": "New Arrival"}
        result = preview(manifest(second=second))
        self.assertIsNone(result["rows"][2]["preparation"]["proposal"]["condition"])
        self.assertEqual(result["rows"][1]["preparation"]["proposal"]["condition"], "NEW")

    def test_quantity_validation(self):
        for raw in ("0", "-1", "1.5", "NaN", "Infinity", "1E100", "unknown"):
            self.assertEqual(quantity_proposal(raw)[2], "INVALID_QUANTITY")
        self.assertEqual(quantity_proposal("1.0"), (1, "PIECE", None))
        self.assertEqual(quantity_proposal("4 Box"), (None, None, "PACKAGE_UNIT"))
        self.assertEqual(quantity_proposal(None)[2], "MISSING_QUANTITY")

    def test_no_inferred_quantity_or_master(self):
        second = {k: v for k, v in SOURCE_ROW.items() if k != "G"}
        proposal = preview(manifest(second=second))["rows"][2]["preparation"]["proposal"]
        for field in ("quantity", "sku", "product_model", "warehouse", "location"):
            self.assertIsNone(proposal[field])

    def test_unknown_manufacturer_category_no_fuzzy_match(self):
        second = {**SOURCE_ROW, "A": "Unknown role", "B": "Unknown category",
                  "C": "Unrecorded maker", "D": "SYN-OTHER"}
        result = preview(manifest(second=second))
        proposal = result["rows"][2]["preparation"]["proposal"]
        self.assertIsNone(proposal["manufacturer"])
        self.assertIsNone(proposal["category"])

    def test_part_handover_future_package_and_spec_flags(self):
        second = {**SOURCE_ROW, "D": "P/N: SYN-PART", "E": "Hand Over",
                  "G": "4 Box", "I": "47000", "J": "6GB"}
        codes = aggregate(preview(manifest(second=second)))["exception_counts"]
        for code in ("PART_LIKE_ID", "HANDOVER", "FUTURE_AUDIT_DATE", "PACKAGE_UNIT", "SPEC_CONFLICT"):
            self.assertIn(code, codes)

    def test_typed_specs_no_capacity_bytes_guess(self):
        specs = typed_specifications({"Capacity": "12V", "DDR": "DDR4", "Speed": "7.2K"})
        self.assertEqual(specs["Capacity"]["dimension"], "VOLTAGE")
        self.assertEqual(specs["Speed"]["value"], "7200")
        self.assertIsNone(typed_specifications({"Capacity": "16GB"})["Capacity"]["value"])

    def test_review_precedence_and_no_exclusion(self):
        self.assertEqual(review_label([]), "READY_FOR_REVIEW")
        self.assertEqual(review_label([{"severity": "CLARIFICATION"}]), "NEEDS_CLARIFICATION")
        self.assertEqual(review_label([{"severity": "BLOCKING"}, {"severity": "CLARIFICATION"}]), "BLOCKED")
        with self.assertRaisesRegex(StagingError, "EXCLUSION_NOT_ENABLED"):
            review_label([], exclusion_requested=True)

    def test_preview_idempotent_and_digest_changes(self):
        first = preview(manifest())
        self.assertEqual(canonical(first), canonical(preview(manifest())))
        second = preview(manifest(second={**SOURCE_ROW, "D": "SYN-OTHER"}))
        self.assertNotEqual(first["preview_digest"], second["preview_digest"])
        self.assertFalse(first["approval_enabled"])
        self.assertFalse(first["posting_enabled"])

    def test_canonical_golden_bytes_unicode_order_and_float_rejection(self):
        self.assertEqual(canonical({"z": "16.0", "a": "\u65e5\u672c"}), b'{"a":"\xe6\x97\xa5\xe6\x9c\xac","z":"16.0"}')
        with self.assertRaisesRegex(StagingError, "NONCANONICAL_NUMBER"):
            canonical({"v": 1.0})

    def test_sanitized_summary_contains_no_identifiers(self):
        summary = json.dumps(aggregate(preview(manifest())))
        for value in ("000123", "SYNTHETIC-AREA", "Serial Number", "Synthetic"):
            self.assertNotIn(value, summary)


class StorageTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.repository = self.root / "unrelated-repository"
        self.result = preview(manifest())

    def test_atomic_capture_idempotent_mode_and_integrity(self):
        key = capture(self.result, self.root, repository=self.repository)
        self.assertEqual(key, capture(self.result, self.root, repository=self.repository))
        self.assertEqual(len(list(self.root.iterdir())), 1)
        target = self.root / (key + ".json")
        self.assertEqual(target.stat().st_mode & 0o777, 0o400)
        self.assertEqual(target.read_bytes(), canonical(self.result))
        target.chmod(0o600)
        target.write_bytes(b"tampered")
        target.chmod(0o400)
        with self.assertRaisesRegex(StagingError, "STORAGE_INTEGRITY_FAILURE"):
            capture(self.result, self.root, repository=self.repository)
        target.chmod(0o600)

    def test_insecure_root_and_repository_refused(self):
        with self.assertRaisesRegex(StagingError, "STORAGE_INSIDE_REPOSITORY"):
            capture(self.result, self.root, repository=self.root)
        self.root.chmod(0o755)
        with self.assertRaisesRegex(StagingError, "INSECURE_STORAGE_PERMISSIONS"):
            capture(self.result, self.root, repository=self.repository)

    def test_symlink_refused(self):
        link = self.root / "link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(StagingError, "UNSAFE_STORAGE_ROOT"):
            capture(self.result, link, repository=self.repository)

    def test_publication_failure_leaves_no_partial_target(self):
        with patch("apps.inventory.staging.storage.os.link", side_effect=OSError):
            with self.assertRaisesRegex(StagingError, "STORAGE_FAILURE"):
                capture(self.result, self.root, repository=self.repository)
        self.assertEqual(list(self.root.iterdir()), [])


class CommandBoundaryTests(TestCase):
    def test_command_preview_and_capture_have_zero_database_queries(self):
        result_manifest = manifest()
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            root.chmod(0o700)
            with patch("apps.inventory.management.commands.stage_inventory.read_workbook",
                       return_value=result_manifest):
                with CaptureQueriesContext(connection) as queries:
                    call_command("stage_inventory", "synthetic.xlsx", capture_root=str(root), stdout=out)
            self.assertEqual(len(queries), 0)
            summary = json.loads(out.getvalue())
            self.assertEqual(summary["approved_rows"], 0)
            self.assertEqual(summary["posting_outcomes"], 0)

    def test_command_error_is_sanitized(self):
        with patch("apps.inventory.management.commands.stage_inventory.read_workbook",
                   side_effect=StagingError("HASH_MISMATCH")):
            with self.assertRaisesMessage(CommandError, "HASH_MISMATCH"):
                call_command("stage_inventory", "private-recipient-name.xlsx", stdout=io.StringIO())
