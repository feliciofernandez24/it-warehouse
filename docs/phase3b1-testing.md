# Phase 3B.1 validation evidence

Date: 2026-11-13 (Asia/Tokyo).

| Executed check | Result |
| --- | --- |
| Original suite before new tests | 105 passed, 19.826 seconds |
| First focused staging run | 36 tests; two failures/errors found and corrected |
| Focused rerun | 36 passed, 0.084 seconds |
| Final full suite with integrity test added | 142 passed, 21.200 seconds; no failures/errors/skips |
| Migration drift | makemigrations --check --dry-run: No changes detected |
| Real offline command | Exact 15/920/897/21/2 reconciliation |
| Repeated private capture | Existing canonical artifact verified without overwrite |
| Workbook SHA-256 | Matches reviewed source |
| Models/engine/historical migrations | Unchanged |

The initial failures were container repository-root detection and shell encoding of a synthetic Unicode test literal. Both were corrected. No source data was altered.

Tests use the existing backend image (Python 3.13/Django 5.2) with a dedicated PostgreSQL 17 tmpfs container. No persistent development volume is attached. Django creates/destroys test_phase3b1_test. Historical schema-test migrations and transaction fixtures operate only there; they never touch development inventory.

## New coverage

37 tests cover deterministic parsing/canonical bytes; exact coordinates/sections; lexical serials and leading zeros; shared strings; formulas/caches; missing caches; digest sensitivity; manifest/layout tampering; duplicate coordinates/members; reconciliation mismatch; malformed ZIP/XML; DTD/entity restrictions; unsafe paths/external relationships/macros; unsupported types/formulas; resource limits; hidden rows; duplicates without merging; unknown mappings; condition/quantity proposals; typed dimensions; null quantities/masters; label precedence/exclusion refusal; idempotent preview; sanitized summaries; storage modes/symlinks/tampering; publication failure; and zero-query command execution.

CommandBoundaryTests invokes preview plus capture and asserts exactly zero Django database queries. Pure SimpleTestCase tests disallow database access. Production staging imports no ORM/posting code. No real workbook is a unit-test fixture; real integration validation uses the offline command.

## Observed initial exceptions

Counts overlap; their union is 105 candidate rows.

| Blocking code | Rows |
| --- | ---: |
| SERIAL_DUPLICATE | 23 |
| PART_LIKE_ID | 11 |
| HANDOVER | 27 |
| FUTURE_AUDIT_DATE | 7 |
| PACKAGE_UNIT | 8 |
| LOCATION_CONFLICT | 28 |
| SPEC_CONFLICT | 9 |

| Additional clarification code | Rows |
| --- | ---: |
| FORMULA_CACHE_UNVERIFIED | 117 |
| MISSING_DEVICE_NAME | 27 |
| MISSING_QUANTITY | 867 |
| SERIAL_IDENTITY_PENDING | 54 |
| UNKNOWN_CATEGORY | 166 |
| UNKNOWN_CONDITION | 296 |
| UNKNOWN_MANUFACTURER | 37 |
| UNKNOWN_STATUS | 1 |
| PRODUCT_MAPPING_PENDING | 897 |
| TRACKING_MAPPING_PENDING | 897 |
| LOCATION_MAPPING_PENDING | 897 |
| MAPPING_POLICY_PENDING | 897 |

Source accounting: 920 = 897 candidates + 21 headers + 2 sequence-only rows on 15 worksheets. Review accounting: 897 = 105 BLOCKED + 792 NEEDS_CLARIFICATION; ready/excluded/approved/posting outcomes are zero. Missing identity remains tracking-sensitive clarification, not automatically a defective serialized unit.

Unknown-manufacturer count includes absent, placeholder and non-brand labels. Location/spec conflict rules are reviewed source-profile scopes, not a universal inference engine.

Exact reproduction commands are in the operations runbook. Development was not started, mounted or contacted. Unchanged development inventory is established by isolation/non-access, not an invented before/after database query.
