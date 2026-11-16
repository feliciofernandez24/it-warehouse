# Excel inventory cleaning and conditional import

Result: **CLEANING COMPLETED; IMPORT BLOCKED** (2026-11-16).

Repository: feature/phase4b, HEAD 5235fe2b2f92f34d2787e15a20b1cce13074c5db. Existing uncommitted Phase 4B changes preserved. No commit, migration, persistent database write, ACL change, or application restart was performed.

## Sources and artifacts

Recursive discovery found one input: imports/IT_Warehouse_Asset_Inventory.xlsx, 566390 bytes.
SHA-256: d0c48893cc095696ada206fb4d61d80c2745d412b289e0ab754dc5bd023bc525.
It matches the existing reviewed profile exactly. No XLS or CSV inputs were found.

Private byte-identical original: imports/originals/d0c48893cc095696ada206fb4d61d80c2745d412b289e0ab754dc5bd023bc525.xlsx (0400).
Generated artifacts in imports/cleaned (0700 directory, 0600 files):

- it_warehouse_cleaned.xlsx
- it_warehouse_rejected.xlsx
- cleaning_report.md
- import_manifest.json

These inventory-bearing files are ignored by Git. Do not force-add them.
Manifest digest (canonical payload excluding its own digest field):
9f70abf0abcbac1fea5a89dd011bde3be06409db0f72c9f4dc20f54f59deb7c8.
Workbook hashes are in the manifest. Source and private copy checksums were reverified after export.

## Row reconciliation and cleaning

15 sheets; 920 populated rows: 897 equipment candidates, 21 section headers, 2 sequence-only rows.
Cleaned workbook: 897 rows requiring manual review. Rejected workbook: 23 non-equipment rows, retained with provenance. Valid: 0; valid with warnings: 0. Rejected does not mean destroyed.

| Worksheet | Equipment candidates |
|---|---:|
| Rack 1769 | 20 |
| Rack 845 | 350 |
| Rack 877 | 28 |
| Rack 871 | 13 |
| Rack 856 | 61 |
| Rack 807 | 59 |
| Rack 820 | 177 |
| Rack 669 | 15 |
| Rack 683 | 128 |
| Rack 7 | 9 |
| LAN Cable (source name has trailing space) | 2 |
| Power Supply | 7 |
| Broken RAM | 2 |
| Broken Controller | 1 |
| Broken Disk | 25 |

Every populated row carries source SHA, original sheet name, Excel row, canonical source-row digest, raw cell JSON, trimmed comparison fields, issue codes and unapproved normalization proposal. Original XML types, lexical values, serials, formula expressions and caches survive as inert text. Leading zeros are preserved where present in source values; lost digits in an originally numeric value are not invented. Styled numeric displays are not asserted to be serial identity; raw styles remain available for review.

The existing bounded OOXML reader checks the entire archive and pinned sheet/section layout. Blank intervals, merged ranges and hidden rows are recorded in the manifest and cleaning report. Repeated section headers are retained separately. No spreadsheet formulas execute; export cells use inline strings. Output formatting does not imply approval.

Rules reuse phase3a1-rules-v1: dictionary proposals for category/manufacturer/condition, explicit integral piece quantities, typed specification proposals, Excel date conversion and placeholder warnings. Trim comparison values only; retain raw serial. Unknown categories/manufacturers, ambiguous model names, missing quantities, physical location conflicts and package units remain unresolved. Missing serials are not generated. Equal serials never cause merging. Locations are not inferred from worksheet names. Legacy audit dates never become movement timestamps. Existing reviewed date reference is 2026-11-13, explicitly preserved.

17 exact raw-field duplicate groups are reported by source-row IDs; none are deleted. Serial duplicates affect 23 rows, part-like identifiers 11, missing/placeholder serials 54, cached formulas 117, future dates 7, handovers 27, location conflicts 28, specification conflicts 9, missing device names 27, missing quantities 867, package units 8, unknown categories 166, unknown conditions 296, unknown manufacturers 37, unknown status 1.
Existing preparation labels: 105 BLOCKED and 792 NEEDS_CLARIFICATION. These labels are separate from the requested four-way export classification.

## Installed schema and mapping

Read-only queries confirmed PostgreSQL 170011, database it_warehouse. Inventory 0001/0002/0003 and transactions 0001 through 0005 are installed; no 0004 inventory migration was created.
The ten requested models/tables exist. Current AssetCategory, Manufacturer, ProductModel, Asset, Warehouse, StorageLocation, StockBalance, StockMovement, ImportBatch and ImportStagingRecord counts are all zero.

Required catalog identities include category/manufacturer code and name; products require SKU, name, category and tracking mode. Warehouses require approved code/name; locations require approved warehouse and valid parent hierarchy, with warehouse/code uniqueness. Asset product/tracking bindings and location/state facts must satisfy inventory constraints. Serial identity is deliberately nonunique. Bulk stock requires the correct product/location/condition/state bucket and ledger conservation.

Preview:

| Entity | Approved creates | Unresolved proposal |
|---|---:|---|
| Categories | 0 | 8 dictionary labels; codes/actions not approved |
| Manufacturers | 0 | 18 dictionary labels; codes/actions not approved |
| Product models | 0 | SKU/product binding pending for all 897 candidates |
| Warehouses | 0 | Physical bindings unresolved |
| Locations | 0 | Physical bindings unresolved |
| Serialized assets | 0 | Tracking partition and receipt facts unresolved |
| Bulk stock records | 0 | Tracking partition, quantities and receipt facts unresolved |

The asset-versus-bulk split cannot be asserted from proposals. There are no existing master rows against which to resolve FKs. Model full_clean, exact FK validation and complete real-data import rehearsal are **blocked**, not reported passed. The manifest is an offline evidence preview, not an executable write authorization.

Controlled master mutations exist in master_service.mutate: fresh actor/permissions, validation, advisory lock (73921,2), atomic audit. Asset creation through Phase 4B remains HTTP 409. transactions.services.post provides tested stock receipt primitives, but no approved verified-source receipt orchestration or exact import plan is available. Never use direct ORM/SQL to create assets, balances, movements, ImportBatch or ImportStagingRecord as a substitute. Owner-only review write guards and immutable ledger guards remain in place.

## Actual runtime and privilege observations

The live Django session is itwarehouse_backend, not the owner or requested itw_app_runtime.
Superuser, CREATEDB, CREATEROLE, REPLICATION, BYPASSRLS and public-schema CREATE are false.
Read-only has_table_privilege checks nevertheless returned true for INSERT on categories/products/ImportBatch, UPDATE on StockMovement, and SELECT on ImportReviewEvent.
Table privileges alone do not bypass owner-only or immutable-ledger triggers; no attempted persistent write was made.
These excess grants, especially confidential review SELECT, require a separately authorized least-privilege review. Synthetic restricted-role tests do not certify the live ACL set.

## Verification performed

Each suite was rerun on a disposable PostgreSQL 17 cluster using synthetic data. No source workbook rows were loaded into PostgreSQL.

| Suite | Passed | Failed/errors | Skipped |
|---|---:|---:|---:|
| Offline export integrity | 6 | 0 | 0 |
| Phase 4B API | 29 | 0 | 0 |
| Phase 4A API | 29 | 0 | 0 |
| Current staging/review/transaction regression | 205 | 0 | 0 |
| Historical regression | 45 | 0 | 0 |
| Phase 4B restricted writer | 6 | 0 | 0 |
| Phase 4A restricted read | 6 | 0 | 0 |
| Review read proof | 20 | 0 | 0 |
| Runtime/stock regression | 16 | 0 | 0 |

Counts are separate suites, not unique security guarantees. No frontend suite was rerun for this offline change.
Django system checks and migration drift check passed in the isolated environment.
The stock suite exercises receipts, transfers, conservation, ledger immutability, audit freezes, owner-assumption denial and replay. Export tests verify canonical manifest and file hashes, original-copy preservation, all-row traceability, no posting/approval and formula/leading-zero safety.

Reproduce from repository root (Linux):
~~~sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/excel_cleaning/prepare.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/excel_cleaning -v
PYTHONDONTWRITEBYTECODE=1 python3 backend/phase4b_validation/run_host.py
~~~
Exporter refuses an existing output directory or original-copy destination; use a separately reviewed fresh workspace for regeneration. It accepts only the current single pinned input and fails closed for additional/nested source files. It does not implement arbitrary XLS/CSV ingestion. It imports no Django settings or database connector.
Regression logs: /home/itadmin/.local/share/it-warehouse-phase4b/.
Workbook XML and ZIP consistency were validated; no GUI spreadsheet rendering test was performed.

## Backup, writes and recovery

Fresh persistent backup/restore rehearsal: NOT PERFORMED, because no exact executable import manifest or operator approval exists and no persistent write is authorized. Historical deployment backups are not presented as fresh import recovery evidence.
Actual imported categories/manufacturers/models/warehouses/locations/assets/bulk/movements/batches/staging rows: **zero**. All 897 equipment candidates remain offline, not SQL-staged or imported.
No receipt reconciliation or imported audit/provenance verification is claimed. Current target tables remain empty; concurrent independent writers were not isolated, so no global unchanged-database snapshot is claimed.

Before a future import: resolve codes/SKUs/tracking/physical locations/quantities/condition/state; create exact action list with stable provenance and replay policy; validate through the controlled services on an isolated database; obtain explicit approval binding actor, exact manifest digest and actions; resolve runtime privilege concerns; isolate writers; take a fresh private backup and independently restore-test roles/ACLs/owners/history/rows; identify authorized recovery operator and verify exact target. Then execute only separately authorized actions. A later failed import must follow reviewed atomic transaction and backup recovery procedures; never disable guards or fake migration history.

Read-only verification query examples:
~~~sql
SELECT app,name FROM django_migrations
 WHERE app IN ('inventory','transactions') ORDER BY app,name;
SELECT current_database(),session_user,current_user;
SELECT count(*) FROM inventory_asset;
SELECT count(*) FROM inventory_stockbalance;
SELECT count(*) FROM transactions_stockmovement;
SELECT count(*) FROM inventory_importbatch;
SELECT count(*) FROM inventory_importstagingrecord;
~~~

The attachment explicitly requires operator approval of exact records/actions before persistent import. General import intent does not meet that gate. Additional mapping and receipt authorization are required; this report does not request or manufacture approval.
