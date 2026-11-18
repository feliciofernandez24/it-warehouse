# Phase 4C registration correction and safe master deletion

Date: 2026-11-17 (Asia/Tokyo). Branch feature/phase4c, base commit f56d27d2979295d79a57e2a8bbce63d7778ad84a. Changes are intentionally uncommitted.

## Actual deployment result

Registration correction is deployed. Backend/PostgreSQL are healthy; frontend responds at http://127.0.0.1:5173/ and backend at http://127.0.0.1:8000/. Manual registration remains enabled under itwarehouse_backend.

Deletion is implemented and isolated-tested, but **not activated persistently**. All five live DELETE privileges remain false and the new flag defaults false. No ACL, owner, schema, migration, credential, inventory or account-permission changes were made. No persistent sample registration or deletion was performed.

Only backend/frontend application images were rebuilt and containers recreated with docker compose up -d --no-deps backend frontend. PostgreSQL container ID 06a763552cf644ecb68efa4873bb00b978c7a4970acc7586a8eacf3cec035c11 and volume it-warehouse_postgres_data were preserved. No commit/push.

## Obsolete warning cause and corrected registration

Assets -> Register asset was still setting editing={id:null}, opening the Phase 4B MasterEditor, whose legacy asset-create form intentionally warns that it cannot create ledger movements. The Phase 4C InventoryOperations form already existed separately.

When the identity response reports manual_inventory_enabled=true, that button now navigates to #/operations?register=1, rendering InventoryOperations and the secured POST /api/transactions/manual/register/ workflow. A defensive MasterEditor wrapper also uses the Phase 4C form if enabled. When the feature is false, the legacy warning/fail-closed behavior remains. No backend flag bypass or legacy asset insertion was introduced; POST /api/management/assets/ remains the old protected interface.

The form loads SERIALIZED active product models, category/manufacturer filters, active warehouses, warehouse-filtered locations, device name, optional raw serial, explicit condition/state and reason. Existing product creation/edit links remain. The manual service now returns:
- existing operation_key, movement_ids, asset_ids, replayed and warnings;
- assets: id + generated asset_tag;
- receipt: immutable movement id/public_id, recorded_at, operation_type and quantity.

Reads occur inside the atomic service boundary, including replay, so a response-read failure cannot falsely report a rollback after a prior commit. Old response keys are preserved. React displays the generated tag and actual receipt UUID/time, never a fabricated success. Structured field-level API errors are displayed.

Deployed route resolution confirms the manual register POST handler exists and MANUAL_INVENTORY_ENABLED is true. Live anonymous POST is correctly denied. Real authenticated registration, receipt/tag output and same-key replay were verified over HTTP on a synthetic disposable PostgreSQL instance; no real inventory was posted as validation. Refresh the page or sign in again to reload the deployed navigation and identity flags.

## Deletion API and business rules

DELETE /api/management/{categories|manufacturers|product-models|warehouses|locations}/{id}/
JSON body:
~~~json
{"expected_version":0,"change_reason":"Verified unused duplicate"}
~~~

Session authentication, CSRF, model view + delete permissions and fresh active actor validation are required. User-supplied actor IDs/extra fields are rejected. Assets and movement history remain non-deletable. Legacy read-only routes remain read-only.

The new MASTER_DATA_DELETE_ENABLED setting (env ITW_MASTER_DATA_DELETE_ENABLED=1) defaults false and is reported as master_data_delete_enabled. It must not be enabled until separate ACL authorization, recovery checks and actual runtime verification succeed. Authorized requests while disabled return sanitized 503; unauthorized users still receive 401/403.

The service:
1. Rejects any model outside the exact five-class allowlist.
2. Takes advisory transaction lock (73921,2), freshly verifies actor permissions and locks the target row.
3. Requires the expected version to match.
4. Checks every reverse FK using existence queries, including historical rows, specifications and zero-quantity stock balances.
5. Checks durable StockOperation JSON references to product/location IDs, even pending requests without movements.
6. Rejects storage-location deletion while any COUNTING/SUBMITTED audit freezes the hierarchy.
7. Deletes precisely one allowlisted table/PK using parameterized SQL with quoted server-owned identifiers, with no ORM collector/cascade.
8. Forces deferred constraints before appending MASTER_DELETE to AssetChangeLog in the same transaction.

Existing PostgreSQL FK/trigger protections remain final authority against concurrent dependencies; the row lock also conflicts with concurrent FK key-share locks. Normal service writers share the same advisory lock. No referenced/occupied item, warehouse with locations/thresholds, location with children/inventory/history, or product with specifications/history is deleted.

Dependency/stale-version failures return 409 with meaningful field messages and deactivation guidance. Invalid fields/missing reason/version return 400. Missing ACL/audit failures return sanitized 503 with rollback. Successful deletion returns 204.

The audit retains entity kind/PK, actor, reason, before metadata and empty after-state. Snapshot policy preserves identifiers, names, parent/FK bindings, version and other non-sensitive fields while omitting raw serials, free-form descriptions, addresses/notes and secrets. Deletion does not delete old audit events.

## React deletion behavior

Delete buttons appear only for the five master pages, with model-level view/delete permission and the deployment flag enabled. Buttons exist in the tables and the existing eligible warehouse detail view. The confirmation identifies record name/ID, fetches its latest management version, requires a reason, and never submits automatically. Successful deletion clears details and refreshes the list. Dependency/field errors remain visible. Edit/deactivate is offered when change permission exists; existing occupied/location guards can still reject deactivation.

The DELETE client bootstraps CSRF separately from existing POST/PATCH helpers. Existing Create/Edit flows and unsupported api.save DELETE behavior are preserved.

Current persistent deletion controls remain hidden/default-off until authorization; this is intentional rather than a claim that deletion is operational.

## Proposed privilege manifest — not applied

Exact proposal: database/master-data-delete.sql.example
SHA-256: f7d9c6164fccb92dc2ca1d6f633e0b5b043ad7587014ab3f0772aaf348e4a646

It proposes only:
- DELETE on inventory_assetcategory, inventory_manufacturer, inventory_productmodel, warehouse_warehouse, warehouse_storagelocation.
- SELECT(product_model_id) on inventory_assetspecification, solely for dependency existence checks; no specification values are selected.

No DELETE on assets, balances, operations, movements, assignments, audit history, review evidence, migration history or authorization tables. No GRANT ALL, public-wide DELETE, TRUNCATE, ownership/membership changes, new SECURITY DEFINER functions or migration.

The combined existing Phase 4B role already supplies SELECT/column UPDATE for row locking. itadmin already has the relevant Django model delete permissions; other operators need their own authorized view/delete grants. None were assigned by this task.

The SQL credential is a trusted application credential. Per-human permission checks and audit atomicity are enforced by the service; this design does not claim independent human authentication or mandatory auditing for arbitrary raw SQL issued after credential compromise. Existing FK/trigger protections still apply to direct SQL. The proposed five-table privilege scope is deliberately narrower than broad application-wide DELETE.

Private reviewable manifest, containing target identity, SQL digest, source-content digests and unapproved status:
/home/itadmin/.local/share/it-warehouse-phase4c-fixes/20261117T053607Z/master-delete-authorization-manifest.json

Activation of deletion requires separate explicit authorization for this exact change set, current target/source revalidation, fresh backup/restore and maintenance controls, applying only approved ACLs and verifying denial of all excluded deletions, then enabling the deletion flag and restarting backend. Existing Phase 4C activation authorization does not cover these new grants. No approval is fabricated here.

## Validation results

Final results; failures corrected during development are not counted as final successes or duplicated in totals:

| Suite | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| Phase 4A backend | 29 | 0 | 0 | 0 |
| Phase 4B backend | 29 | 0 | 0 | 0 |
| Phase 4C backend | 22 | 0 | 0 | 0 |
| New deletion/registration backend | 17 | 0 | 0 | 0 |
| Existing current stock/staging/review | 205 | 0 | 0 | 0 |
| Historical regression | 45 | 0 | 0 | 0 |
| Phase 4A restricted runtime | 6 | 0 | 0 | 0 |
| Phase 4B restricted runtime | 6 | 0 | 0 | 0 |
| Phase 4C restricted runtime | 6 | 0 | 0 | 0 |
| Review read security proof | 20 | 0 | 0 | 0 |
| Stock/runtime security | 16 | 0 | 0 | 0 |
| New nonowner deletion proof | 5 | 0 | 0 | 0 |
| Frontend entire suite | 58 | 0 | 0 | 0 |

Total: 464 passed test executions across separately listed suites. The new nonowner proof verifies missing grants fail closed, all five allowed deletions audit correctly, forbidden DELETE/DDL remain denied, CSRF and audit-grant failure rollback. Concurrency tests verify simultaneous deletes yield exactly one success/audit.

The previous Phase 4B test expecting DELETE 405 for every master was updated for the new permission-gated contract: unauthorized master deletion is 403; asset DELETE remains 405. No stock-integrity expectation was weakened.

Additional real HTTP smoke on newly built backend with synthetic data verified login/CSRF, serialized registration with generated tag and receipt, replay stability, dependency 409 and unused-category 204. This is separate smoke evidence, not added again to the unittest totals.

Frontend production build passed (33 modules). Backend/frontend Docker builds, Django system check, migration drift check and git diff --check passed. No migration file changed or was generated. Write tests ran only in isolated tmpfs PostgreSQL; existing workbook files/reports were not regenerated.

Reproduce:
~~~sh
docker build -t itw-phase4c-backend-validation backend
PYTHONDONTWRITEBYTECODE=1 python3 backend/phase4c_validation/run_host.py
docker build -t itw-master-delete-frontend frontend
docker run --rm --network none itw-master-delete-frontend npm test
docker run --rm --network none itw-master-delete-frontend npm run build
~~~
Private test logs: /home/itadmin/.local/share/it-warehouse-phase4c/.
Private HTTP/deployment evidence: /home/itadmin/.local/share/it-warehouse-phase4c-fixes/20261117T053607Z/.

## Deployment preservation and limitations

Application writers were briefly stopped for code deployment. All table row hashes and owner/ACL/trigger metadata matched across the restart. Live runtime identity, installed inventory 0001–0003 and transaction 0001–0005, enabled stock guards and feature flags were checked read-only.

The deployed frontend source contains the corrected /operations?register=1 navigation and tag/receipt display. Manual posting is enabled, deletion disabled; the new specification-FK SELECT privilege is absent, as expected. No persistent catalog or inventory data was changed by validation or deployment.

Changed/new files:
- backend/apps/accounts/session_api.py
- backend/apps/inventory/master_api.py
- backend/apps/inventory/master_delete.py
- backend/apps/transactions/manual_service.py
- backend/config/settings/base.py
- backend/config/test_phase4b.py
- backend/config/test_master_delete.py
- backend/phase4c_validation/run_host.py
- backend/phase4c_validation/master_delete_runtime.py
- frontend/src/App.jsx
- frontend/src/MasterData.jsx
- frontend/src/InventoryOperations.jsx
- frontend/src/MasterDelete.jsx
- frontend/src/MasterDelete.test.jsx
- frontend/src/api.js
- frontend/src/api.test.js
- database/master-data-delete.sql.example
- docs/phase4c-registration-and-deletion.md
