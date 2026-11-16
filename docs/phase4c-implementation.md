# Phase 4C — Manual inventory operations

Implemented and validated on disposable PostgreSQL 17.11 using synthetic records. Controlled development activation remains pending. The persistent database was queried read-only; no data, schema, roles, ACLs, credentials or migration history were changed. Existing Excel artifacts were not modified or imported. No commit or push.

## Architecture and supported behavior

Existing transactions.services.post already supplies STOCK_IN, TRANSFER, STOCK_OUT and RETURN, operation UUID/fingerprint replay, explicit capability authorization, advisory lock (73921,2), asset and bucket locks, custody updates and deferred PostgreSQL integrity checks. Existing Phase 4B supplies catalog/warehouse CRUD and audited metadata correction. Phase 4C adds strict command serializers, a composing manual service, session APIs and React forms. Historical migrations, posting service and PostgreSQL functions/triggers are unchanged; no migration is needed.

Serialized registration requires an active SERIALIZED product, active category/manufacturer associations where present, a named device, explicit condition/state and active destination. Serial may be blank where allowed; it is never generated. Existing Asset default generates the unique internal tag; clients cannot supply tags. Receipt creates asset and opening movement together. Description metadata and a MANUAL_REGISTER audit entry share the same outer transaction. Duplicate normalized serials produce a warning and a distinct asset; blank serials produce a warning. Technical specifications are selected from the existing product catalog and displayed, not invented per asset.

Bulk receipt requires a BULK product and positive explicit piece quantity. Transfers preserve condition/state and move between distinct active locations; valid transfers between warehouses use the same guarded service. Serialized source location/condition/lifecycle must still match; stale requests fail. Bulk quantity must be sufficient. No balance-edit endpoint exists.

Issue and return are serialized custody operations: active recipient selection, available asset, issue assignment and required movement; return identifies the open assignment and its original issue movement. Invalid/double returns and terminal/invalid lifecycle transitions fail. Existing bulk issue/return primitives lack this serialized custody contract; the new issue endpoint rejects bulk explicitly and no bulk return endpoint is exposed.

Registration/receipt timestamps come from server posting. Historical dates, acquisition cost/vendor details and arbitrary asset-specific specifications are not accepted by the manual command schema. Catalog specifications can be maintained using the existing permitted product-model workflow. Recipient creation remains the existing authorized administration workflow; the new page selects actual active recipients only.

## API contracts

All paths are under /api/. Unsafe methods require authenticated Django sessions and CSRF. Only JSON command fields declared by the serializers are accepted; actor, tags, ledger IDs, timestamps, approval/review linkage and arbitrary fields cannot be supplied.

| Method/path | Behavior |
|---|---|
| POST transactions/manual/register/ | Single serialized receipt and description metadata |
| POST transactions/manual/receive/ | Positive BULK piece receipt |
| POST transactions/manual/transfer/ | Serialized or bulk transfer, preserving state/condition |
| POST transactions/manual/issue/ | Serialized issue to an active recipient |
| POST transactions/manual/return/ | Serialized return referencing current assignment |
| GET transactions/movements/ | Paginated read-only history including operator/time/endpoints |
| GET transactions/recipients/ | Active recipients, no contact details |
| GET transactions/assignments/ | Open assignment identifiers |
| GET transactions/balances/ | Read-only balance buckets |

Read list/detail routes use existing view permissions, bounded pagination and validated filters. Movement filters: asset/product_model; assignment filter: asset; balance filters: product_model/location. No review evidence is queried by these endpoints.

Every command supplies operation_key UUID, nonblank reason <=500 and optional external_reference <=160. Register supplies product_model_id, destination_location_id, device_name <=200, serial_raw <=200 (blank permitted), optional description <=4000, condition and state. Bulk receipt substitutes explicit positive quantity for device fields. Transfer supplies exactly one asset_id/product_model_id, quantity, source_location_id/source_condition/source_state and destination_location_id/condition/state. Issue supplies serialized asset/source fields and recipient_id, optional purpose/destination_reference. Return supplies asset_id, assignment_id, destination_location_id, condition and state. The serializer is the definitive field contract.

201 means newly committed posting; 200 means an identical replay. Responses contain original operation/movement/asset IDs and warnings. Errors: 400 validation, 401 authentication, 403 capability/CSRF, 409 rejected state/idempotency conflict, 503 disabled deployment or database/audit failure. Database exception text is never returned.

Example registration request:
~~~json
{
  "operation_key": "81378620-bde1-4e49-8da9-d1a0c3bd88e1",
  "reason": "Physical equipment received",
  "external_reference": "Operator-provided reference",
  "product_model_id": 1,
  "destination_location_id": 1,
  "device_name": "Operator-provided device name",
  "serial_raw": "",
  "description": "",
  "condition": "USED",
  "state": "AVAILABLE"
}
~~~
IDs are examples, not existing development records or approved inventory facts.

## Atomicity, audit and replay

The manual service takes the existing global lock first, freshly loads actor permissions, rejects inappropriate tracking/source facts, then invokes post inside the same atomic transaction. Asset identity/position and stock quantities are created/changed exclusively through post. The only extra asset write is description metadata after a successful serialized receipt. An AssetChangeLog entry identifies the first immutable movement and operation UUID, actor, action, resulting identifiers and a SHA-256 fingerprint of the full validated manual request, including description. Raw serial/description are not copied into the audit snapshot. An audit insertion failure rolls back asset, movement, operation, balances and custody.

A UUID already used by another actor, action or changed payload conflicts. A posted operation without the matching manual audit conflicts rather than being retroactively adopted. Replay checks current permissions and original fingerprint and returns immutable result IDs without checking mutable present-day source positions or creating another audit. This preserves retries after transfers or returns. There is no stock retry via a new UUID following an uncertain response.

The React confirmation keeps the exact pending payload/key for retry after errors and disables edits while pending. Cancel requires explicit acknowledgement to inspect activity before creating a new operation if an earlier response was lost. Pending payloads are in memory only: after a reload/navigation, inspect history and recover the original key before retrying; browser persistence/recovery is not implemented.

## Permissions

No parallel role model or automatically assigned groups. Existing Django groups may be configured by an authorized administrator:

| Logical capability | Existing grants |
|---|---|
| Inventory viewer | Relevant inventory/warehouse view permissions |
| Catalog manager | Phase 4B view/add/change category, manufacturer, product and warehouse/location as required |
| Warehouse operator | Explicit transactions.receive_stock / transfer_stock / issue_stock / return_stock for assigned duties, plus relevant view permissions |
| Inventory administrator | Approved catalog and operator permissions; inventory.add_asset for registration |
| Auditor | transactions.view_stockmovement and separately approved read permissions; no posting capability |

All manual commands require product/warehouse/location view permissions. Registration also requires inventory.view_asset and inventory.add_asset. Transfer/issue/return require inventory.view_asset. Issue/return also require accounts.view_assetrecipient and transactions.view_assetassignment. Stock capability checks query explicit permission/group grants: an ungranted Django superuser cannot post. The UI reports existing grants; it never grants them. Data visibility is permission-global, following existing architecture, not per-warehouse tenancy.

## Restricted database proof and grant boundary

New runtime_probe.py creates itw_phase4c_runtime only in a new disposable phase4c_runtime_test database, with no ownership/membership or privileged flags. It tests actual API writes through that LOGIN role. No SECURITY DEFINER functions or owner memberships were added. Service authorization is the application boundary; the SQL credential is not an independently authenticated human actor.

The proof grants only the following stock-specific SQL operations, plus established session/authorization reads:

| Object | Proof privileges |
|---|---|
| auth and permission join tables, content type | SELECT |
| django_session | SELECT/INSERT/UPDATE(session_data,expire_date)/DELETE |
| auth_user | SELECT and UPDATE(last_login) |
| inventory categories/manufacturers/products, warehouse/location, recipients | SELECT |
| inventory_productmodel | UPDATE(version) solely to permit SELECT FOR UPDATE |
| inventory_asset | SELECT/INSERT; UPDATE(condition,lifecycle_status,current_location_id,version,updated_at,description) |
| inventory_stockbalance | SELECT/INSERT; UPDATE(quantity,version,updated_at) |
| transactions_stockoperation | SELECT/INSERT; UPDATE(posted_at) |
| transactions_stockmovement | SELECT/INSERT; UPDATE(id) solely for original-movement row locking on return |
| transactions_assetassignment | SELECT/INSERT; UPDATE(returned_at,returned_by_id,return_movement_id,updated_at) |
| audits_physicalinventoryaudit/auditline | SELECT for existing guard validation |
| audits_assetchangelog | INSERT; SELECT(id,operation_key,after,actor_id) for request replay |
| Required serial sequences | USAGE only |
| Review evidence, migration history, schema ownership | No additional privileges |

PostgreSQL SELECT FOR UPDATE requires some UPDATE privilege, even if no field is changed. The single-column movement UPDATE(id) grant is not a ledger mutation capability: the unchanged immutable trigger rejects an actual UPDATE id=id. The proof tests it, as well as denied ledger reason UPDATE/DELETE, review SELECT, CREATE/ALTER/TRUNCATE and owner assumption. No ledger DELETE grant or full-table UPDATE is supplied. Existing Phase 4B grants may be combined only after reviewing actual effective ACLs; this proof is not a production grant script.

Previous read-only observations of itwarehouse_backend showed excess review SELECT and ledger UPDATE grants. This task does not fix persistent ACLs. Deployment must review/reduce them under separate authorization, and must account for the limited audit replay column reads. A permission failure returns sanitized 503 and rolls back, not a request to grant ALL.

## Frontend operation

The Inventory Operations page offers Register New Asset, Receive Bulk Stock, Transfer Stock, Issue Equipment and Return Equipment according to reported capabilities. Category/manufacturer filters narrow catalog selection; product details display existing technical specifications. Missing models link to Phase 4B product management. Destination location choices filter by selected active warehouse. Bulk quantities use pieces; serialized quantity is fixed to one by the server.

Review transaction displays an explicit confirmation payload before posting. Success displays actual committed identifiers and warnings. Errors remain visible and do not claim success. Activity shows actual immutable server history, operator, timestamp, action, endpoints and asset/product/quantity. Other user's unrelated review evidence is never presented. The page loads paginated permitted lookup/history lists to completion; server-side windowed activity browsing is a future scaling improvement.

## Validation and evidence

Final passing suites (counts are separate suites, not rerun totals):

| Suite | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| Phase 4C API / real PostgreSQL concurrency | 22 | 0 | 0 | 0 |
| Phase 4C real nonowner LOGIN | 6 | 0 | 0 | 0 |
| Phase 4B API | 29 | 0 | 0 | 0 |
| Phase 4A API | 29 | 0 | 0 | 0 |
| Current staging/review/stock regression | 205 | 0 | 0 | 0 |
| Historical regression | 45 | 0 | 0 | 0 |
| Phase 4B restricted writer | 6 | 0 | 0 | 0 |
| Phase 4A restricted reader | 6 | 0 | 0 | 0 |
| Review read gateway proof | 20 | 0 | 0 | 0 |
| Runtime/stock security regression | 16 | 0 | 0 | 0 |
| Frontend entire suite | 48 | 0 | 0 | 0 |

The frontend 48 include 9 new Phase 4C tests; do not add 9 again. Frontend tests cover confirmation, exact retry payload/key, actual response rendering, read-only actors, bulk filtering/quantity, transfer selection, recipient/assignment selection, error visibility and deployment-gated navigation. API tests cover serialized receipt/opening ledger/audit, real duplicate tag rejection, audit rollback, duplicate serial warnings, replay conflict and revoked permissions, quantities/tracking, lifecycle/custody, bulk conservation, inactive locations, CSRF and simultaneous same-key requests.

Initial development failures (serializer error shape and missing row-lock privileges) were corrected and affected suites rerun. Counts above describe final results. No real warehouse fixtures or historical workbook imports were used.

Django system check and makemigrations --check --dry-run passed in disposable PostgreSQL. Backend and frontend Docker images built successfully. Frontend npm run build passed: 32 transformed modules. Tests use Django's actual request stack and a real PostgreSQL login; frontend interaction tests mock transport. No full browser-to-live-development-database end-to-end posting was attempted.

Reproduction from repository root:
~~~sh
docker build -t itw-phase4c-backend-validation backend
docker build -t itw-phase4c-frontend-validation frontend
PYTHONDONTWRITEBYTECODE=1 python3 backend/phase4c_validation/run_host.py
docker run --rm --network none itw-phase4c-frontend-validation npm test
docker run --rm --network none itw-phase4c-frontend-validation npm run build
~~~
The harness uses a new network-isolated tmpfs PostgreSQL 17 cluster and read-only backend bind mount, never .env or development DB connection. It requires existing container names to be free and existing regression helpers to remain available. Logs are private files under /home/itadmin/.local/share/it-warehouse-phase4c/. Run cleanup.py after collecting evidence; it verifies exact names, labels and absence of named volumes before removing only the disposable containers. No persistent volumes are deleted.

Final development read-only verification:
- Database it_warehouse; Django session itwarehouse_backend.
- MANUAL_INVENTORY_ENABLED false.
- Asset, StockBalance, StockMovement, ImportBatch and ImportStagingRecord counts remain zero.
- Disabled custom triggers on protected asset/balance/operation/movement/custody tables: zero.
- Historical migration diff: empty; git diff --check passed.
These are point-in-time checks, not a claim that concurrent independent actors were isolated.

## Controlled deployment and readiness

Manual APIs and new supporting read endpoints default off via ITW_MANUAL_INVENTORY_ENABLED=0. The identity response reports manual_inventory_enabled and React hides the operations navigation until enabled; direct requests also fail closed. This gate matters because the development backend bind-mounts repository source and can reload code during work.

Before activation, authorize a controlled application/ACL deployment, review actual effective SQL permissions and Django group assignments, verify target/container/volume and the restricted session identity, isolate writers, take a fresh private backup and independently restore-test it, record recovery responsibility, then apply only reviewed minimal grant/configuration changes. Set ITW_MANUAL_INVENTORY_ENABLED=1 for the backend using the reviewed deployment configuration and rebuild/restart backend/frontend via the existing Compose procedure. Do not run migrations as runtime. No schema migration is required for Phase 4C.

Run session/CSRF/read smoke checks, confirm capability reporting and disabled import/review workflows, and conduct any persistent manual acceptance receipt only with explicit authorized real inventory facts. Reuse original UUIDs on uncertain outcomes. Configuration rollback disables manual posting but must never delete committed stock operations or reverse immutable ledger history. Recovery of committed inventory requires an approved business reversal or the separately controlled database recovery plan.

No fresh persistent backup or restore was performed in this coding task because no persistent write/configuration/ACL deployment was executed. Runtime-role/credential changes, production rollout and real receipts remain outside this implementation rehearsal.

Readiness: manual functionality is implemented and passes isolated validation; **development activation is NO-GO until backup/recovery, least-privilege ACL review and deployment authorization are satisfied**. Workbook capture/import, review approval/revocation and import promotion remain disabled.

## Files changed by Phase 4C

New:
- backend/apps/transactions/manual_api.py
- backend/apps/transactions/manual_serializers.py
- backend/apps/transactions/manual_service.py
- backend/config/test_phase4c.py
- backend/phase4c_validation/run_host.py
- backend/phase4c_validation/runtime_probe.py
- backend/phase4c_validation/cleanup.py
- frontend/src/InventoryOperations.jsx
- frontend/src/InventoryOperations.test.jsx
- docs/phase4c-implementation.md

Extended existing working files:
- backend/apps/accounts/session_api.py (reported stock capabilities and deployment flag)
- backend/config/api_urls.py (manual command and read routes)
- backend/config/settings/base.py (default-off opt-in)
- frontend/src/App.jsx (gated operations route/navigation)
- frontend/src/styles.css (manual form/confirmation layout)

Existing uncommitted Phase 4B and offline-review changes were preserved; they are not new Phase 4C modifications.
