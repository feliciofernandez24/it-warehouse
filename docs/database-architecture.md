# Database architecture - Phase 2B baseline and Phase 2C extension

The Phase 2C extension is documented in [transaction engine](phase2c-transaction-engine.md), [security review](phase2c-security.md), [testing evidence](phase2c-testing.md) and [runbook](phase2c-operations-runbook.md). It adds StockOperation and posting guards; deployment/runtime-role integration and full audit reconciliation remain pending. The following Phase 2B sections are a historical baseline, not a description of current service availability.

Phase 2B implements the schema approved in Phase 2A, with AssetRecipient added by request. Phase 2C posting services, APIs, imports and frontend behavior are not implemented. See the [exact generated field/constraint/index reference](phase2b-model-reference.md), [ERD](database-erd.md), [migration SQL](phase2b-migration-sql.md), [implementation plan](phase2-implementation-plan.md) and [validation report](phase2b-validation.md).

## Baseline and runtime

Inspected settings, requirements, six app packages, Compose, environment example and Phase 1/2A docs. Branch develop. Django 5.2.19, Python 3.13, PostgreSQL 17; psycopg and DRF retained. PostgreSQL is db:5432 on Docker network, no published database port. Existing auth.User, session authentication and default IsAuthenticated remain unchanged. USE_TZ=True; display timezone Asia/Tokyo. Framework migrations already existed; custom apps began with empty migrations. No workbook is present. No change to Compose, existing environment, Git settings or production infrastructure is needed.

## Model boundaries and relationships

All 18 business models use BigAutoField PKs, default Django table names and protective FKs. Master/current-state rows inherit created_at, updated_at and version; version is a future optimistic-concurrency token, not incremented or enforced automatically. Immutable event rows have recorded_at and optional business occurred_at instead. Exact lengths/defaults/nullability are in the generated model reference; named masters share code CharField(64), name CharField(200), description, is_active and timestamps.

| App / model | Primary fields and relationships |
| --- | --- |
| accounts.AssetRecipient | Unique code, name, kind PERSON/DEPARTMENT/TEAM/ORGANIZATION, optional one-to-one auth.User, external_reference, contact_details; archive with is_active |
| warehouse.Warehouse | Named master, address; owns locations |
| warehouse.StorageLocation | Warehouse, optional parent, code, name, kind AREA/RACK/SHELF/BIN, is_active |
| inventory.AssetCategory | Named category master |
| inventory.Manufacturer | Named vendor master |
| inventory.ProductModel | Unique sku_code, name, category, optional manufacturer, model/part number, tracking_mode, capacity_bytes, memory_generation, interface_type, typed speed/size with units, port_count |
| inventory.SpecificationDefinition | Named master with data_type and unit |
| inventory.AssetSpecification | Definition, exactly one product/asset owner and exactly one integer/decimal/text/boolean value |
| inventory.Asset | Unique immutable asset_tag, serialized product, device_name, raw/normalized serial and review state, condition, lifecycle, location, description, remarks, legacy audit date |
| inventory.StockBalance | Bulk product, location, condition, stock_state, nonnegative quantity; immutable bucket identity |
| inventory.StockThreshold | Bulk product, warehouse, nonnegative minimum_quantity |
| inventory.ImportBatch | Public UUID, source filename/hash/storage key, uploader/time, mapping version/timezone, status, reviewer/time/preview digest, notes |
| inventory.ImportStagingRecord | Batch, worksheet/row coordinates, raw/normalized JSON, errors/warnings, status, source digest, optional promoted asset/balance and time |
| audits.PhysicalInventoryAudit | Public UUID, location scope/descendant flag, status, planned date and workflow times, performer/approver, notes |
| audits.AuditLine | Audit, asset XOR bulk product, optional balance, expected/observed locations/counts/conditions/states, outcome, counter/time, notes |
| audits.AssetChangeLog | Public UUID, entity kind/PK, optional asset, actor/action/time, operation key, JSON before/after, reason |
| transactions.StockMovement | Public UUID, operation key/line, operation type, asset XOR bulk product, quantity, source/destination locations/balances, optional asset condition/lifecycle snapshots, actor/time/reason, reference, reversal/audit/import links |
| transactions.AssetAssignment | Asset, AssetRecipient, destination_description/reference, issuer/time/due date, optional return actor/time, unique issue/return movements, purpose |
| reports | No tables; reports will query these records |

AssetRecipient represents non-login people and organizations. Only PERSON may link to auth.User; account link is optional and unique. Names do not identify recipients uniquely; reviewed code/external reference does. A destination description/reference captures hostname, department or work order without inventing a host model or requiring a login. Recipient, destination and issue identity cannot change after assignment insertion; closed episodes cannot be updated. Archive recipient identities rather than deleting history.

## Serialized versus bulk

A product has SERIALIZED or BULK mode. Asset is one individually controlled unit, even without serial. StockBalance counts indistinguishable BULK pieces by product/location/condition/state. Both cannot represent the same physical items. DB tracking triggers reject a BULK Asset or SERIALIZED balance, threshold, bulk movement or bulk audit line. Referenced product mode cannot change. Asset catalog identity and stock bucket identity are immutable; use future reviewed conversion/reclassification flows.

Asset tags default to UUID-based AST- identifiers, remain unique and immutable, and never derive from serial. serial_raw preserves text; serial_normalized is trim/case-fold without punctuation or leading-zero removal. Missing/duplicate serials are allowed. States UNREVIEWED/VERIFIED/DUPLICATE/MISSING support review; VERIFIED does not mean globally unique. No merge by serial. Normalization runs on save/clean, not bulk SQL; placeholder policy and duplicate-review workflow remain Phase 2C.

Conditions NEW/USED/REFURBISHED/BROKEN/UNKNOWN are separate from lifecycle AVAILABLE/QUARANTINED/ASSIGNED/DISPOSED/LOST. BROKEN/UNKNOWN cannot be AVAILABLE. On-hand asset states require a location; ASSIGNED/DISPOSED/LOST require NULL location. Bulk AVAILABLE excludes BROKEN/UNKNOWN; QUARANTINED retains them. Assignment/lifecycle agreement across rows is deferred.

Quantities use BigIntegerField, >=0 for balance/threshold/audit and >0 for movement. Serialized movements have quantity=1, no bucket FKs. Capacity is positive integer bytes; measurements Decimal(20,6) plus unit, never float. Nonnegative integer ports. Initial bulk quantities count pieces, including cable pieces; measured length requires another approved unit-of-measure design.

## Locations

A warehouse owns a location tree; Rack/Shelf/Bin are typed StorageLocation rows. Rack codes such as 845, 820, 683, 1769 are strings unique within a warehouse, with no 19-inch/rack-unit assumptions. Roots AREA/RACK; AREA contains any kind, RACK contains SHELF/BIN, SHELF contains BIN, BIN is a leaf. Any node can directly hold stock, including standalone and broken areas. Equipment condition is independent of area name.

DB enforces code scope, kind membership, no self-parent and allowed root kinds. clean() additionally checks same warehouse, allowed parent kind and ancestor cycles. These cross-row rules are NOT yet protected against bulk SQL or concurrent reparenting. Phase 2C must serialize hierarchy edits/check occupancy/frozen scope and add database protection before accepting operational writes.

## Specifications, custody and movements

Common fields belong on ProductModel; extra typed values use AssetSpecification. Owner XOR, single value and owner/definition uniqueness are DB-enforced. Definition data-type agreement is clean()-only until a Phase 2C trigger. Unit values override catalog defaults when reading; no reporting implementation yet.

Operations: STOCK_IN, STOCK_OUT, TRANSFER, RETURN, ADJUSTMENT_IN, ADJUSTMENT_OUT, DISPOSAL. Adjustment is split into positive magnitudes with direction. Receipts/returns/increases have only destination; issues/disposals/decreases only source; transfers both, no no-op. Bulk endpoints require corresponding bucket FKs; asset snapshots are absent for bulk. Source/destination product/location matching is clean()-only. Reversal links retain history but do not yet enforce allowable reversal quantity/state.

No separate receipt/issue header is needed now. (operation_key,line_number) is DB-unique, but complete payload idempotency, multi-line atomicity and prevention of adding a line to an old operation need Phase 2C. Movement creation alone does not debit/credit or update assets.

Open assignment uniqueness is a PostgreSQL partial unique index; due/return ordering, all-or-none return evidence and unique movement links are DB-enforced. clean() checks movement asset/type/actor/time and recipient active state. It does not synchronize lifecycle or validate live custody under concurrency. No posting interface exists.

## Counts and provenance

Audit headers enforce enum, date ordering, approval evidence and different performer/approver. Lines enforce target XOR, nonnegative/0-or-1 asset counts, uncounted-versus-observed evidence, condition/state membership and unique asset/bucket per audit. Unexpected bulk uniqueness includes observed location and NULLS NOT DISTINCT. Expected fields are snapshots; location is observed/searched location for missing or uncounted findings. Scope freezing, snapshot creation, derived outcomes, line completeness and signed-off adjustment posting remain Phase 2C.

Import batches/rows preserve source coordinates and target references. DB enforces source-row uniqueness, hash formats, review evidence/separate uploader-reviewer and promoted target XOR/time. Reverse one-to-one StockMovement.import_row links the opening movement without a circular FK. Multiple rows may contribute to one bulk bucket with distinct provenance. No parser/importer or preview service exists. Raw JSON immutability, approval invalidation, whole-batch duplicate prevention and promoted-row/opening-movement coherence need Phase 2C. See [Excel plan](excel-migration-plan.md); actual workbook semantics remain unverified.

## Enforcement boundaries

| Layer | Implemented guarantee |
| --- | --- |
| PostgreSQL CHECK/UNIQUE/FK | Row-local enum, XOR, quantity, direction, evidence/date rules; asset tags, bucket/source-row/open-assignment uniqueness; referential integrity |
| PostgreSQL triggers in transactions.0002 | Asset tag/catalog identity and bucket identity immutable; serialized/bulk relationship guards with parent row locks; referenced mode immutable; DELETE denied on all seven history/provenance tables; UPDATE denied on movement/change log; assignment issue identity/closed episodes protected |
| Model clean/full_clean | Helpful validation for hierarchy, active locations/recipient, typed-definition match, bucket matching and assignment movement correspondence |
| Phase 2C, not implemented | Atomic posting/conservation/reconciliation, complete custody coherence, approvals/permissions, hierarchy concurrency, audit freeze, immutable approved snapshots/raw capture, idempotent preview/import, restricted runtime roles |

Django save() does not call full_clean(). QuerySet.update, bulk_create and raw SQL bypass model validation; only DB constraints/triggers still run. The tests deliberately demonstrate selected clean()-only gaps. Existing development credentials are not restricted posting-only credentials. DB owners can disable triggers or TRUNCATE; ordinary application DELETE protection is not an adversarial owner boundary.

PROTECT masters, recipients, users and historic links; deactivate/archive instead. Movement/change-log updates/deletes are rejected even through QuerySet SQL. Audit/import records cannot be ordinarily deleted, but workflow-dependent update immutability is deferred. Assignment history retains episodes. No stock model is registered as an editable admin or exposed by a new API.

## Auth and reports

Retain auth.User. Administrator, Warehouse Operator, IT Engineer and Auditor will use Groups/Permissions, with explicit post_movement, approve_adjustment/disposal, review_import/promote_import and approve_audit permissions declared in model Meta. Group provisioning, permission enforcement and warehouse row scopes remain Phase 2C; declarations alone do not implement authorization. No custom user or authentication API.

Reports need no extra tables: category unit totals (serialized count separately from bulk sum), available/quarantined stock, broken condition, recursive rack inventory, movement history, open recipient assignments, threshold LEFT JOIN including zero stock, and audit discrepancies. Existing composite/partial indexes support these queries; measure before adding materialized views.

## Migration graph and references

accounts.0001 -> existing auth; warehouse.0001 independent; inventory.0001 -> warehouse/auth; audits.0001 -> inventory/warehouse/auth; transactions.0001 -> accounts/audits/inventory/warehouse/auth; transactions.0002 -> transaction/audit/inventory initial schemas. No reciprocal FK from staging/audits to movement, hence no circular dependency. Forward SQL creates new schema objects and adds constraints; no destructive operation or live stock DML. Reverse guard SQL is provided for controlled rollback, not executed against development.

References: [Django constraints](https://docs.djangoproject.com/en/5.2/ref/models/constraints/), [Django migrations](https://docs.djangoproject.com/en/5.2/topics/migrations/), [PostgreSQL trigger functions](https://www.postgresql.org/docs/17/plpgsql-trigger.html). Operational review decisions remaining: recipient identity matching/retention, piece versus measured units, audit freeze duration, approval staffing, posting privilege boundary and reversal/cutover policy.

## Phase 2C schema extension

transactions.0003 adds StockOperation (UUID operation_key PK, complete request JSON, fingerprint, requester/time, independent approver/time/reason and posted_at). transactions.0004 adds invoker posting/conservation/custody/hierarchy/audit guards and hardens existing function search paths. Existing stock/history or active audits fail the migration preflight pending reviewed cutover. transactions.0005 atomically replaces only movement_not_noop_transfer to permit real same-location serialized condition/state reclassification. Other Phase 2B constraints/triggers remain. Operation-key movement identity is enforced by SQL triggers without renaming existing columns. The new header is durable approval/idempotency evidence; the old statement that no header is needed is superseded.
