# Phase 3B controlled import contract (proposed)

Design version: phase3a1-v1. Reference date: 2026-11-13, Asia/Tokyo. Documentation only; no schema, transaction engine, inventory or workbook changes. Source findings are confirmed from Phase 3A and a read-only XML recheck; policy choices below are proposals awaiting approval. No database state or installed migrations were queried.

## Current boundary

No import posting is implemented or authorized here. transactions.0004 itw_movement_guard rejects non-null import_row_id and audit_line_id. StockMovement already has one-to-one import_row, but current Line cannot supply it. Phase 0005 changes serialized reclassification checks, not this import prohibition. Bypassing provenance by submitting ordinary unlinked STOCK_IN is not an acceptable import. Keep all existing guards and engine behavior unchanged in this phase.

## Inputs and preconditions

A future promotion takes an authenticated actor, sealed snapshot identity/digest and stable operation identity. It loads source and exact approved bytes from controlled storage, rather than accepting client-supplied target IDs/quantities as authoritative. Require current import and transaction permissions, independent valid approval, source hash match, unsuperseded revision and nonempty selected set. Selected rows must be approved, not merely READY_FOR_REVIEW; every excluded/deferred candidate remains accounted for. Recheck master content/active state, warehouse/location hierarchy, audit freezes, duplicate-source claims, inventory overlap and all model constraints. Drift aborts; never silently remap an approved SKU.

## Receipt mapping and cardinality

| Accepted source proposal | Future posting request and result |
| --- | --- |
| One SERIALIZED unit | STOCK_IN; approved SERIALIZED product_model_id; quantity=1; explicit device_name/serial_raw/condition/state; active destination location; source null. Service generates immutable asset tag. Opening movement must carry this source import_row and target the created asset. |
| Counted BULK pieces | STOCK_IN; approved BULK product_model_id; positive integer quantity in PIECE; explicit condition/state/location. Opening movement links import_row; StockBalance resolved by product/location/condition/state and credited through ledger only. |
| Multiple rows sharing a bulk bucket | Distinct receipts and source links per row even if one bucket is reused; no loss of row-level quantity evidence. |
| Serialized quantity greater than one or split conditions/locations | Unsupported by first contract: one staging row has one target and one opening movement. Block until separately designed child-unit/source-allocation model with unique child identity, total conservation and parent traceability exists. Never duplicate a serial or mutate Excel row numbers to create children. |
| External custody / handover / terminal status | Deferred from initial on-hand receipt contract until a separately approved cutover workflow has truthful receipt/issue/assignment evidence. Current Line cannot reference an asset created earlier in the same new request; a future receipt-to-issue dependency design is needed. Broken stock cannot be issued through an AVAILABLE-state fiction. |
| Optional asset metadata/specification | Apply approved serial_review_state, description/remarks, legacy date and typed overrides atomically with receipt/target links using a future validated metadata path. Current Line does not carry all these fields. Never use direct metadata writes to alter position, condition or quantity outside posting. |

Every request spells out all semantic fields rather than relying on NEW/AVAILABLE/quantity defaults. UNKNOWN/BROKEN require QUARANTINED; a real physical location is still mandatory. Serial normalization remains trim+casefold and is not a merge key. For initial contract, serialized units and bulk pieces are distinct reconciliations, even if both quantities are integers. No adjustments, returns, disposal or fabricated historical custody are used to approximate an opening receipt.

## Atomicity, identity and replay

Proposed first unit of work is the whole explicitly accepted subset. Future service acquires existing engine advisory lock before batch/snapshot, source-claim and inventory locks in one documented order shared with all writers; retain current asset/bucket ordering and deferred constraints. Revalidate under lock, reserve persistent source claims, build complete ordered requests, post linked receipts and persist target/provenance/snapshot-consumption outcomes in the same transaction. Force deferred checks before reporting success and report success only after outer commit. A later failure rolls back claims, ledger, balances, assets and staging promotion together. Durable failure diagnostics must be separate sanitized events, not partially committed stock.

Use a fixed import namespace UUID and UUIDv5 name derived from contract version + immutable source-selection identity + approved semantic payload digest for operation keys. Do not derive solely from random upload batch UUID. Persist planned operation UUIDs and request fingerprint with the approved snapshot; the operation UUID derivation uses a semantic plan digest that excludes the UUID itself, avoiding a circular hash. Same operation key/payload/actor returns original committed IDs; changed payload or actor fails as Phase 2C requires. A lost network response must be resolved by committed operation/source-claim lookup, never a new receipt.

Consume each (workbook_sha256, exact worksheet_name, excel_row_number) once for stock effects across batches; claim is unique independently of operation UUID and dictionary versions. Same bytes can be previewed repeatedly, not posted repeatedly. A renamed/re-exported/edited workbook changes the byte hash and can contain the same physical stock: require owner-approved authoritative scope, cross-file overlap review, inventory identity review and a cutover register. Byte-hash uniqueness alone does not prove stock novelty. Matching serial alone neither consumes nor merges a record.

No automatic chunking: if atomic promotion is too large, stop for a separately reviewed checkpoint/claim/reconciliation design. Committed errors are corrected through approved compensating movements/events, preserving original records and claims. No delete/reset/direct balance update or trigger disablement.

## Reconciliation definitions

All metrics are tied to snapshot digest, selected scope and execution attempt. Row counts, physical units and movement lines are different dimensions.

| Metric | Definition / equality |
| --- | --- |
| Source accounting | 920 populated = 897 candidates + 21 headers + 2 sequence-only. Layout-only blank/merged cells do not enter this equation. |
| Exclusive candidate decisions | 897 = ready_for_review + needs_clarification + blocked + excluded_with_reason. Initial v1: 0 + 792 + 105 + 0. Issue flag totals overlap. |
| Review approval | accepted_rows <= READY_FOR_REVIEW rows at sealing; accepted + deferred_nonexcluded + excluded = 897. Approved rows are a subset with separate approval evidence, not a fifth review label. Initial accepted=0; none approved in this phase. |
| Serialized units | For accepted SERIALIZED source rows in first contract, S = count(rows), each contributes exactly one; on commit created assets = S and serialized opening receipts = S. Unknown tracking/quantity contributes to unresolved count, never zero units. |
| Bulk by SKU/unit | B[sku,PIECE] = sum(accepted verified positive quantities). Also break down by location/condition/state for bucket comparison. Unresolved quantities remain null and counted separately. Never add packages to pieces or add different SKUs as a meaningful stock measure. |
| Accepted receipt rows | A = S + count(accepted BULK rows), not S + sum(bulk quantities). Opening movement count = A; every accepted row has exactly one opening movement and one matching target under first contract. |
| Source quantities | Numeric Qty subtotal of 117 across 22 rows; eight package Qty cells; 867 absent Qty cells. Source subtotals are comparison evidence, not the approved inventory total. Conversions/verified implicit ones need a separate reconciliation bridge with evidence. |
| Posting outcomes | Before commit: A pending. Success: A promoted, 0 pending; failure: 0 newly promoted, A unpromoted for that attempt. Replay: zero new stock effects and same committed result IDs. Initial actual Phase 3A.1 outcomes=0. |
| Bucket conservation | At cutover under lock, ending bucket quantity = baseline + sum(committed receipts into that bucket), with receipt sum equal to accepted source quantity; existing ledger conservation still governs all history. |
| Position/custody | Serialized targets have latest-ledger-consistent location/state; initial contract creates no assignments. Future custody extension reconciles receipt/issue pairs and exactly one open assignment where applicable. |
| Partial source selection | Every deferred/excluded source row has explicit reason; approved source claims and posted rows equal accepted subset only. File is not described as fully imported while any required candidate remains deferred. |
| Audit result | Persist per-row source digest, target ID, opening movement ID, operation UUID, committed time and snapshot digest privately. Aggregate counts alone cannot prove provenance. |

## Future changes requiring separate implementation approval

| Area | Proposed future change; not implemented |
| --- | --- |
| DB capture and review | Add immutable ImportPreviewSnapshot/revision entity with canonical payload/digest and protected source/approval references; append-only preparation/decision evidence. Enforce raw capture/coordinate immutability and sealed revision/approval immutability in DB, not merely UI. Reuse existing staging JSON and enums; no triage enum migration required initially. |
| DB independent identities | Persist preparer/editor membership and enforce distinct reviewer from uploader/all preparers; authenticated transitions and evidence timestamps. Existing reviewer != uploader constraint remains. |
| DB source consumption | Unique committed source claim across batches; bind selected snapshot/row digest/target/opening movement and operation. Enforce target/cardinality/coherence and no deletion or reuse. Snapshot supersession/revocation must fail closed during promotion. |
| DB guards | New reviewed forward migration after 0005 may replace only the import branch with verified approved-snapshot/source-link checks. Keep audit correction disabled, request matching, permission checks, freezes, tracking, immutable history and deferred ledger/custody conservation intact. Never edit historical migrations. |
| Services | Restricted read-only capture/normalize/preview/review operations; approval/invalidation; full payload provenance binding; future import-aware receipt adapter/Line version and atomic promotion wrapper; metadata validation and complete source-result mapping. No live write endpoint in design phase. |
| Permissions/deployment | Separate capture/preparation/review/promotion grants, authenticated identities, least-privilege runtime role and protected evidence storage. Review existing deployment security limits; no schema-owner bypass claims. |
| Units / child rows / custody | Keep unsupported initially. Owner-approved packaging/base-unit schema, child allocation model and dependent receipt-to-issue cutover workflow require separate designs and tests before use. |

## Future validation gate

Before Phase 3B implementation/promotion, resolve the decisions in [exception policy](phase3a1-exception-policy.md), review the proposed schema/API contract, inspect live masters/installed guards read-only, and approve an isolated rehearsal/cutover plan. Future tests must cover canonical digest golden vectors (Unicode, decimals, dates, formulas and order), exact 897-row classification coverage, revision tampering/self-review, source replay across batches/concurrency, master drift, guard rejection, rollback after late failure, per-row/bucket reconciliation and lost-response retry. Preserve and rerun the supplied 105-test baseline in an isolated test database during that implementation phase.

Phase 3A.1 changes only four design documents. Existing backend, migrations, transaction engine and tests remain byte-identical; no tests were run because this is documentation-only and no test database was needed. No workbook cells or PostgreSQL data changed; no private manifest was written, staged or uploaded. These documents do not authorize stock posting.
