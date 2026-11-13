# Phase 3A import readiness

Analysis date: 2026-11-13 (Asia/Tokyo). Source: local confidential workbook; no source upload, database connection, Django execution, importer, commit or push. Confirmed findings come from all worksheet XML and cached cell values, interpreted against repository models and migrations on develop. Proposed mappings and physical interpretations require owner approval.

## Decision

**Not ready for Phase 3B controlled live import.** Read-only analysis is complete; a restricted staging/preview design may follow after review, but no importer is implemented here. No candidate is declared approved for stock promotion.

## Blocking issues

| Blocker | Evidence / acceptance requirement |
| --- | --- |
| Import posting disabled | transactions/migrations/0004_posting_guards.py lines 180-181 explicitly reject non-null import_row_id. Current Line has no import_row field. A future separately reviewed guard/service change must support immutable provenance; omitting import_row to evade the guard is unacceptable. |
| Promotion contract incomplete | ImportBatch and ImportStagingRecord support review and targets, but current posting lacks batch digest validation, immutable approved capture/promotion, duplicate-source prevention and atomic staging-to-opening movement linkage. |
| Quantity/unit and tracking decisions | 117 numeric units across 22 rows plus eight package quantities; no authoritative complete unit total or serialized/bulk allocation. |
| Serial identity conflicts | 11 repeated non-placeholder groups; missing/placeholder/part-like IDs require review, without merging assets. |
| Master data and classification | Approve SKU/category/manufacturer/specification mappings; no live master matches were queried. |
| Physical location and custody | Two location labels plus worksheet/prose locations need reconciliation. Assigned To is not sufficient issue evidence; handover status is ambiguous. |
| Condition and date cleanup | 296 non-enum condition values, 28 ambiguous statuses and future audit dates require review. |
| Runtime state unverified | No database connection was made. Installed migration versions, active masters, inventory overlap, audit freezes and runtime-role grants must be inspected read-only in Phase 3B preparation. |

## Phase 2C compatibility

Bulk quantities must be positive integers; buckets are unique by product/location/condition/state, nonnegative and BULK-only. Direct opening balances violate ledger conservation. Serialized receipts require SERIALIZED product, quantity one, device_name and active warehouse/location; internal tags are generated, serials need not be unique. Missing specifications are nullable, not permission to fabricate them.

BROKEN and UNKNOWN must be quarantined. AVAILABLE/QUARANTINED serialized assets require a location; ASSIGNED/LOST/DISPOSED require no current location. Broken handover cannot be blindly issued: STOCK_OUT requires AVAILABLE and an active recipient, plus custody/ledger agreement. Future cutover must use truthful approved receipt/issue evidence, never invented historical locations or timestamps. Audit COUNTING/SUBMITTED scopes freeze posting. Adjustments/disposals require independent durable approval and current explicit permissions.

Every future accepted source row must retain its unique batch/sheet/row, target and opening movement. Multiple bulk source rows may contribute to one bucket only with distinct linked receipts; duplicate serials never select existing assets automatically. Complete request UUID/payload identity, advisory lock, atomic posting, immutable movements and deferred final-state checks remain mandatory. Last Audit Date is legacy evidence, not a new approved audit.

## Controlled next-phase acceptance

Require a reviewed section/row manifest, approved dictionaries and unit policies, resolved or explicitly excluded blockers, restricted preview with deterministic digest and separate reviewer, source-scope duplicate prevention, and a separately approved import-posting implementation. Rehearse on a disposable restored environment with per-source reconciliation, ledger/balance/custody checks, retry and rollback tests. Obtain explicit cutover approval before live stock changes. No database migration or importer is part of Phase 3A.

## Validation and limits

- All 15 worksheet XML parts inspected, including headers, gaps, formulas, cached values and merges. No Excel/Python third-party dependency installation was needed: Python standard-library zipfile/XML only.
- Workbook SHA-256 before analysis: d0c48893cc095696ada206fb4d61d80c2745d412b289e0ab754dc5bd023bc525. The writer also checks this digest after documentation generation. No workbook save or XML write method was used.
- No PostgreSQL connection, SQL, ORM, stock-posting service, migration command or database test ran. Therefore this work created no inventory records or movements; it does not claim an independently observed live database baseline.
- Existing migration files are hashed before and after documentation generation; final Git diff checks cover tracked files.
- Original workbook remains excluded by existing *.xlsx and imports/* rules. No git add, commit, push or upload was performed. Final status must contain only these four documentation additions.
- Source values were used only locally. Documentation contains aggregate results and redacted examples; no serial inventory, recipient label, site label or embedded host tag is reproduced. Exact source worksheet/row references remain for restricted follow-up.
- Confirmed observations are distinguished from proposed interpretation throughout. Raw Excel numeric values cannot prove original human-entered serial precision or freshness of formula caches. Physical stock existence, recipient semantics and live database compatibility remain unverified.
