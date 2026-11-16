# Phase 4B — Inventory master data management

Date: 2026-11-16. Work was performed exclusively on feature/phase4b, starting at 5235fe2b2f92f34d2787e15a20b1cce13074c5db. The worktree was clean at entry. No commit, push, merge or branch switch was performed.

## Result and scope

Implemented and verified:
- Category, manufacturer, product model, warehouse and storage-location registration and editing.
- Existing asset metadata editing: device name, serial number, description and remarks.
- Django session/CSRF and backend model-permission enforcement.
- Mandatory reasons, optimistic versions, coordinated locking and transactional immutable audit records.
- React permission-based controls, reusable forms, paginated relationship choices, validation/conflict messages, list filters, warehouse details and success refreshes.
- Existing Phase 4A read-only API contracts, login, dashboard, search and pagination preserved.

**Blocked operation: new asset registration.** transactions.0004_posting_guards installs a deferred asset_final_state constraint requiring every asset to match its latest stock-ledger receipt. An asset without a movement cannot commit. This phase expressly prohibits automatic stock movements, so authorized registration requests are validated and return 409 ASSET_REGISTRATION_REQUIRES_RECEIPT without inserting an asset, movement or audit event. The UI explains this before submission and offers validation, not a false success.

A reviewed receipt workflow, or a separately approved pre-registration schema/workflow, is required to make new asset registration operational. No guard was weakened and no draft model, migration or unapproved data store was invented. Therefore the unrestricted asset-registration portion of the mission remains blocked; the rest of the implemented master-management scope is functional.

## Inspection and existing model relationships

Read the Phase 4A guide, relevant Phase 3B schema documentation and the actual model/migration guards before editing. Reused:
- AssetCategory and Manufacturer: existing NamedMaster code/name/description/is_active.
- ProductModel: unique SKU, required category, optional manufacturer, tracking mode and existing model/part/description/active fields.
- Warehouse: existing code/name/description/address/active fields.
- StorageLocation: warehouse, optional parent, code/name/kind/active; uniqueness is warehouse + code.
- Asset: immutable generated tag and product identity, current location/lifecycle/condition tied to ledger; serial normalization and review state already exist.
- AssetChangeLog: generic entity_kind/entity_pk, optional asset FK, actor, action, recorded_at, before/after JSON and reason. Existing triggers prohibit UPDATE/DELETE.

No model was duplicated or changed. Product category/manufacturer and location warehouse/parent use existing FKs. No Asset.warehouse field was added: a location already determines its warehouse.

No migration is needed for the implemented operations. makemigrations --check --dry-run reports no changes. No inventory.0004 or historical migration change exists.

## Architecture and compatibility

New master_serializers.py defines explicit request/response allowlists. Unknown/read-only input fields are rejected rather than silently discarded. Identifier input is trimmed and uppercased before duplicate validation. Existing identifiers remain immutable on edit. full_clean() runs on the complete proposed instance, including partial edits, so existing model/check/FK/unique rules are retained.

New master_service.py coordinates mutations:
1. Begin an atomic transaction and acquire the existing advisory lock (73921,2).
2. Reload actor activity and required Django permissions.
3. Lock the affected row for updates.
4. Validate allowlisted data, required reason and expected version.
5. Apply only permitted fields; run model validation and retain database constraints/triggers.
6. Save changed fields plus version/updated_at; normalize edited serials and reset serial review to UNREVIEWED.
7. Append AssetChangeLog in the same transaction.
8. Return only after the service transaction completes. Failed audit insertion or deferred/integrity checks roll back the record change.

New master_api.py registers separate /api/management/ routes. The existing /api/inventory/, /api/warehouses/ and /api/locations/ endpoints remain read-only. The original Phase 4A tests still assert 405 for legacy writes and pass unchanged.

No writable stock, assignment, audit-count, import, review, approval, revocation or promotion endpoint was added. DELETE has no handler. No automatic account or permission administration exists.

## API reference

For each resource below:
- GET /api/management/{resource}/: paginated list, existing search/filter/order behavior.
- GET /api/management/{resource}/{id}/: current record and version.
- POST collection: create (except assets, which returns the documented 409).
- PATCH detail: partial edit.
- PUT detail: complete edit using the same guarded mutation service.
- DELETE: 405.

| Resource | Django model | Editable business fields |
| --- | --- | --- |
| categories | inventory.AssetCategory | code on create; name, description, is_active |
| manufacturers | inventory.Manufacturer | code on create; name, description, is_active |
| product-models | inventory.ProductModel | SKU on create; name, category, manufacturer, model_number, part_number, tracking_mode, description, is_active |
| warehouses | warehouse.Warehouse | code on create; name, description, address, is_active |
| locations | warehouse.StorageLocation | code on create; name, warehouse, parent, kind, is_active |
| assets | inventory.Asset | existing device_name, serial_raw, description, remarks only |

All writes require nonblank change_reason (maximum 500 characters). Updates also require expected_version from the management GET response. Version mismatch returns 409 and does not overwrite the newer record. A successful update increments version. No browser-supplied actor, id, version, timestamp, normalized serial, lifecycle, condition, product reassignment or location assignment is accepted for asset edits.

For a new asset validation request, product_model must reference an active SERIALIZED product and current_location an active location. The warehouse picker is UI-only and is never submitted as a nonexistent asset field. A valid request still returns the receipt blocker; it does not register an asset.

Status conventions:
- 401 anonymous.
- 403 missing model/relationship permission or failed CSRF.
- 400 invalid fields, duplicates detected by validation, malformed reason/version/FK or attempted identifier/state changes.
- 404 missing detail record.
- 409 stale version, registration blocker or a database uniqueness/hierarchy/stock rule conflict.
- 503 database/audit write unavailable; no partial business mutation is committed.
- 405 unsupported operations, including deletion and writes to Phase 4A endpoints.

Database diagnostics are not returned. Duplicate races remain protected by database constraints. There is no blind client retry after an uncertain write; refresh and inspect existing identifiers before resubmission.

## Permission matrix

| Operation | Required existing Django permissions |
| --- | --- |
| Master GET | view_<model> |
| POST | view_<model> + add_<model> |
| PUT/PATCH | view_<model> + change_<model> |
| Asset management GET (serials/notes) | view_asset + change_asset |
| Product category/manufacturer selection | corresponding related model view permission when a nonnull FK is supplied |
| Location warehouse/parent selection | view_warehouse / view_storagelocation |
| New asset validation selection | view_productmodel / view_storagelocation |
| Management warehouse/{id}/locations | view_warehouse + view_storagelocation |

Django superuser semantics for ordinary business model permissions are retained; no user is made a superuser. Permissions are checked on each request and reloaded inside the service. Existing Phase 4A login/logout/CSRF/throttling/cookie protections remain unchanged.

The me response now reports only the six models' existing add/change permissions in addition to the previous read allowlist. It does not grant anything or reveal confidential review capabilities. UI controls follow those grants; backend authorization remains authoritative.

Model permissions are global to these existing models; this phase does not introduce warehouse-specific object authorization. Permission freshness and optimistic versions cover this application path, not arbitrary privileged SQL writers. All cooperating master writers use the service/advisory lock; unrelated direct SQL must remain under the existing administrative controls.

## Business validation and safeguards

- Duplicate codes/SKUs use existing unique rules; location codes are unique per warehouse.
- Existing named codes/SKUs and asset tags remain stable.
- Newly selected associations must be active. An unchanged existing inactive association may be retained during an edit, without allowing a new association to that inactive record.
- Parent warehouse, cycle, root-kind and allowed-child-kind checks use StorageLocation.clean() and existing guards.
- Occupied location moves/deactivation, active-audit hierarchy changes and referenced product tracking-mode changes remain subject to database guards. Failures roll back the audit and record together.
- Asset state, current location, product, condition and tag are never changed here.
- Serial numbers are normalized by the existing model. Editing a serial resets its review state. Serial uniqueness is deliberately not invented: the schema permits duplicates and tracks serial review separately.
- No asset, master record, stock history or audit history deletion is implemented.

## Audit behavior

Every committed supported mutation appends the existing AssetChangeLog:
- actor is the freshly checked authenticated user, never a body field;
- entity_kind is the model label, entity_pk the real saved PK;
- action is MASTER_CREATE or MASTER_UPDATE;
- timestamp comes from the existing server-side recorded_at default;
- before/after capture business metadata and version, with changed_fields;
- asset FK is populated only for asset edits;
- reason is required.

Free-form descriptions, remarks, addresses, raw/normalized serials and legacy audit metadata are excluded from snapshot values. changed_fields still records which of these fields changed. Decimal metadata is serialized safely. No credentials, sessions or password hashes are copied. Users must not enter secrets into the free-text reason.

Existing changelog UPDATE/DELETE guards remain intact. No audit-read endpoint was added. The append and master mutation share a transaction: a missing audit privilege or database failure returns 503 and rolls back both. Audit IDs/sequences may have normal PostgreSQL gaps after rollback.

This guarantees consistency for these API mutations, not complete auditing of arbitrary SQL by someone holding writable database credentials. Stronger DB-enforced actor attribution/all-writer auditing would require a separate reviewed security design; it is not falsely claimed here.

## Runtime privilege proof and deployment boundary

No persistent DB role, ACL, credential or ownership change was performed. All role provisioning in phase4b_validation/runtime_probe.py is synthetic-only and explicitly guarded.

The real nonowner proof verified create/edit of all five master types and asset metadata editing with:
- explicit catalog/auth/hierarchy reads;
- master INSERT plus sequence USAGE;
- column-limited metadata UPDATE, excluding asset position/tag/product and original identifier columns;
- audit INSERT, sequence USAGE and SELECT(id) only, required by PostgreSQL INSERT RETURNING;
- no audit payload SELECT/UPDATE/DELETE;
- no review-evidence reads/writes, stock writes, DDL, owner membership, TEMP/CREATE or superuser privileges.

The existing invoker stock/hierarchy guards require reads of stock/audit foundation tables when metadata is updated. The proof retains those reads but exposes no new raw-history API. It does not present its test SQL as a production provisioning script. Missing audit INSERT was tested to fail closed with zero committed master rows.

Read-only inspection of the live environment found:
- actual Django session_user=current_user is itwarehouse_backend, PostgreSQL 17.11, database it_warehouse;
- all queried privileged role flags are false and public schema CREATE is false;
- audit INSERT, SELECT(id) and changelog sequence USAGE are currently available;
- direct SELECT on inventory_importreviewevent is still available, requiring a separate authorized least-privilege review;
- inventory.0001/.0002/.0003 are applied and eleven review functions exist.

No grant was changed to make a live request pass. Persistent authenticated mutation smoke tests were not run.

## Frontend workflows

The Phase 4A layout/login/dashboard and read APIs are reused. Catalog tables now show:
- Register controls only with view+add;
- Edit controls only with view+change;
- unchanged read-only presentation for readers;
- active/inactive filters for categories, manufacturers, warehouses and locations;
- existing asset lifecycle/product tracking/warehouse filters and search/pagination;
- warehouse detail and location browsing.

MasterData.jsx supplies reusable configuration-driven forms and paginated/searchable relationship pickers. Codes are read-only on edit. Current inactive selections are retained visibly. Forms show field errors, permission failures and conflicts without discarding entered text. They send JSON with fresh CSRF tokens, reasons and loaded versions. Duplicate submission/cancel during saving is disabled. Dialogs support keyboard containment, Escape and focus restoration.

Success is shown only after the API returns a committed success; lists refresh while retaining browsing state. The asset form clearly explains its registration blocker before submission; it cannot show a fabricated created-asset notification.

No dependencies were added. Existing React/Vite/Vitest tooling is reused.

## Verification results

Final clean results, reported independently without double-counting retries:

| Suite | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
| Phase 4B API/validation/audit/concurrency | 29 | 0 | 0 | 0 |
| Phase 4B real nonowner writer proof | 6 | 0 | 0 | 0 |
| Existing Phase 4A API/security | 29 | 0 | 0 | 0 |
| Existing Phase 4A restricted read-runtime proof | 6 | 0 | 0 | 0 |
| Existing current regression | 205 | 0 | 0 | 0 |
| Existing historical registry | 45 | 0 | 0 | 0 |
| Existing review-read security proof | 20 | 0 | 0 | 0 |
| Existing runtime/stock/review regression | 16 | 0 | 0 | 0 |
| Frontend (all four files, including Phase 4A regressions) | 39 | 0 | 0 | 0 |

Backend concurrency tests use actual concurrent connections: one update commits and one stale edit returns 409; duplicate create produces one record and one audit, with the second request rejected. Audit-failure tests prove rollback. Existing tests were not changed to hide failures; two API-client cases were appended to the existing frontend tests.

Django system check: no issues. Model migration dry-run: no changes detected. Frontend production build and distinct backend/frontend validation-image builds: PASS.

The first disposable writer probe correctly exposed missing SELECT(id) for audit RETURNING; the narrowly scoped test grant was corrected and a clean full run passed. No persistent grants were changed. Earlier exploratory/focused runs are not extra passing test counts.

Actual HTTP/Vite smoke using itw_phase4b_runtime in the private disposable namespace passed:
- frontend and proxied health 200;
- login 200 and anonymous management 401;
- missing-CSRF write 403;
- five master creates 201;
- category and asset metadata edits 200;
- stale edit and ledger-free asset registration 409;
- deletion and legacy write 405;
- logout 200 and subsequent me 401;
- exactly seven new audit records;
- unchanged asset, stock-movement, stock-operation and stock-balance counts.

No ports were published for that smoke. Browser component tests are jsdom-based; a full browser-engine visual test was not run. Private logs/evidence are under ~/.local/share/it-warehouse-phase4b/.

## Reproduce verification

From the repository with unused disposable container names and existing test images:

~~~sh
git branch --show-current
git status --short
PYTHONDONTWRITEBYTECODE=1 python3 backend/phase4b_validation/run_host.py
docker build -t itw-phase4b-backend-validation backend
docker build -t itw-phase4b-frontend-validation frontend
PYTHONDONTWRITEBYTECODE=1 python3 backend/phase4b_validation/http_smoke.py
docker run --rm --network none itw-phase4b-frontend-validation npm test
docker run --rm --network none itw-phase4b-frontend-validation npm run build
PYTHONDONTWRITEBYTECODE=1 python3 backend/phase4b_validation/cleanup.py
~~~

run_host.py creates only a new network-none PostgreSQL tmpfs cluster, a source-mounted test client and separate synthetic runtime clones. It never loads .env. The unchanged existing runtime harness's synthetic password contract is used in its own disposable cluster. http_smoke.py follows that runner, uses a test actor/password only in the clone, shares the private namespace and uses wsgiref strictly as test transport, not production hosting.

Do not point mutation tests or test grant code at development. Cleanup verifies explicit Phase 4B names/labels and no persistent volumes before stopping/removing only disposable containers. Retain evidence before cleanup.

## Deployment and rollback

No persistent deployment, restart, migration, account/permission grant or credential change was executed. Existing source binds may expose the new authenticated routes through the already running development stack; this is not a claim that a controlled runtime rollout was performed.

Before a controlled rollout:
1. Review/commit through the user's normal Git workflow; refresh any HEAD-bound deployment manifest afterward.
2. Review runtime grants and existing user view/add/change assignments, without automatic privilege expansion. Resolve the confidential review SELECT issue separately.
3. Re-run isolated verification with the intended runtime matrix and approved images.
4. Use the approved backup/change-control/application deployment process. Do not weaken the old D.4 schema-only runbook's guards to accept new application routes.
5. Verify actual effective role and authenticated functionality using authorized accounts and a controlled non-destructive smoke plan.

No schema rollback is needed because no schema changed. For an application rollback, redeploy a previously approved application image/configuration through change control; do not reset the repository, erase audit history or reverse old migrations. Already committed master changes remain real data: correct them with an authorized audited update, a fresh version and reason. Do not delete records to mimic rollback, revert credentials to owner, or disable triggers.

## Remaining limitations and Phase 4C

- New asset creation remains blocked until a separately reviewed ledger-backed receipt/pre-registration workflow is authorized. Asset tag/product/location/lifecycle changes and assignment transactions remain excluded.
- Editable product fields are an intentional subset of the existing technical specification model; no new specification schema was invented.
- There is no destructive delete, bulk edit, upload/import, audit-history UI, object-level warehouse tenancy, stock posting or review activation.
- A live writable credential can bypass application audit conventions using permitted direct SQL; append-only audit history itself remains protected. Production deployment must keep migration/owner credentials separate and review all writers.
- Phase 4A's multiworker/shared-cache and HTTPS/reverse-proxy requirements still apply.
- Persistent authenticated mutation deployment remains an operator-controlled task; current global model permissions are not newly granted here.

Recommended Phase 4C: review the controlled receipt workflow and object-level scopes, then extend operational inventory only through the existing guarded stock services, with explicit authorization and isolated adversarial tests. Do not make ledger-free asset insertion a shortcut.

## Exact changed files

Modified:
- backend/apps/accounts/session_api.py
- backend/config/api_urls.py
- frontend/src/App.jsx
- frontend/src/api.js
- frontend/src/api.test.js
- frontend/src/styles.css

Created:
- backend/apps/inventory/master_api.py
- backend/apps/inventory/master_serializers.py
- backend/apps/inventory/master_service.py
- backend/config/test_phase4b.py
- backend/phase4b_validation/run_host.py
- backend/phase4b_validation/runtime_probe.py
- backend/phase4b_validation/http_smoke.py
- backend/phase4b_validation/cleanup.py
- frontend/src/MasterData.jsx
- frontend/src/MasterData.test.jsx
- docs/phase4b-implementation.md

No model, historical migration, stock service, audit model, .env, Compose configuration, dependency manifest or existing backend test was modified. main and develop were not checked out or updated.

## Live read-only URL observations

The existing externally running stack returned:
- http://127.0.0.1:5173/ — 200.
- http://127.0.0.1:5173/api/health/ — 200.
- http://127.0.0.1:8000/api/management/categories/ — 401 without a session, as expected.

No persistent login or business mutation was performed to obtain those observations. Disposable validation services are cleaned up afterward; the original PostgreSQL volume and application containers are preserved.

Final cleanup completed: only the four labeled disposable Phase 4B validation containers were removed after security evidence was retained. The original development database, backend, frontend and persistent PostgreSQL volume were left intact. The final refreshed frontend validation image passed all 39 tests and its production build. The strengthened before-value audit assertion also passed in a focused rerun; it is not an additional unique test count.
