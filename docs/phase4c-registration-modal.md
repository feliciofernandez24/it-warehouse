# Phase 4C asset registration modal

Implemented and frontend-only deployed on feature/phase4c. Clicking Assets -> Register asset opens a centered modal without changing #/assets or navigating to Inventory Operations.

## Components and behavior

SerializedAssetRegistration.jsx owns the single serialized-registration lookup/request/confirmation/posting implementation. AssetRegistrationModal.jsx hosts it in an accessible portal dialog on the Assets page. InventoryOperations.jsx uses the same component for its existing registration action; bulk receiving, transfer, issue, return and activity remain in Inventory Operations.

App.jsx keeps the Catalog component mounted, sets local modal state rather than location.hash, and refreshes the asset query after successful registration. Search, filters, pagination and warehouse selection are retained. Success remains visible in the modal, including actual server asset tags and receipt UUID/time. A summary also remains on the Assets page after closing.

The modal uses the existing palette and editor backdrop, a responsive width, scrollable body and persistent header/footer controls. It has aria-modal/labelled dialog semantics, background inert/aria-hidden handling, body scroll locking, initial focus, Tab/Shift+Tab trapping and focus restoration to the trigger.

Close, Cancel and Escape dismiss a clean/completed modal without navigation. Dirty state requires confirmation. Closing is disabled while a request is in flight. An ambiguous result has a stronger warning containing the operation key before abandonment. Validation failures leave the modal open; confirmed HTTP 400 errors make the fields editable and show structured field errors with aria-invalid/describedby.

A synchronous ref lock, immutable pending request and completion guard prevent duplicate posts even before React renders disabled buttons. Network/ambiguous failures retry the exact same UUID and payload. A new operation is created only by a new explicit review. Inventory Operations offers Register another asset after confirmed success; the Assets modal retains the success until dismissed.

The feature flag and required permissions remain enforced in the client and unchanged backend. Disabled registration shows a fail-closed message, not the obsolete Phase 4B form. Both interfaces use POST /api/transactions/manual/register/ through the existing session/CSRF API helper. No backend stock business logic, request schema, migrations, roles, ACLs or database records were changed for this task.

## Validation

Full frontend suite: **71 passed, 0 failed, 0 skipped**, across seven files. This includes 13 new modal tests covering:
- no redirect and unchanged #/assets;
- Close, Cancel, Escape and focus restoration;
- unsaved-change confirmation;
- focus trapping;
- preserved search/filters;
- existing Phase 4C API, generated tag/receipt and automatic list refresh;
- editable validation errors;
- duplicate-click protection and in-flight dismissal lock;
- same-key/payload retry;
- disabled feature behavior;
- Inventory Operations registration reuse.

Existing tests were updated for the shared loader's asynchronous tab lookups and removal of the legacy warning/form. Initial test failures were resolved before deployment. A success/close timing issue was corrected by synchronizing modal posting status before paint.

Frontend production build passed: 36 modules transformed. git diff --check passed. Backend tests were not repeated because this task changed only frontend rendering/state and retained the backend API contract; previous backend/deletion work was preserved, not modified.

Tests use jsdom and mocked API transport. No persistent sample receipt or browser inventory posting was performed.

Commands:
~~~sh
docker build -t itw-registration-modal-frontend frontend
docker run --rm --network none itw-registration-modal-frontend npm test
docker run --rm --network none itw-registration-modal-frontend npm run build
docker compose build frontend
docker compose up -d --no-deps frontend
~~~

## Deployment

Frontend rebuilt/recreated successfully and responds at http://127.0.0.1:5173/.
Frontend root and proxied /api/health/ return HTTP 200.
Served App.jsx contains the modal host and no old /operations?register=1 redirect. The served modal and shared form modules contain the dialog controls and existing register endpoint.

Backend and database container IDs/images were identical before and after deployment; both remained healthy. The PostgreSQL volume was not modified or recreated. No configuration, persistent authorization, sample stock or audit/ledger data was changed. No commit/push.

Private evidence:
~/.local/share/it-warehouse-registration-modal/20261117T231649Z/
Includes before-container identities, tested source hashes and deployment-result.json. The directory timestamp is UTC.

Refresh the browser once to load the new frontend. Thereafter Register asset opens the modal while remaining on #/assets.

## Files changed in this task

- frontend/src/App.jsx
- frontend/src/MasterData.jsx
- frontend/src/InventoryOperations.jsx
- frontend/src/SerializedAssetRegistration.jsx (new)
- frontend/src/AssetRegistrationModal.jsx (new)
- frontend/src/styles.css
- frontend/src/AssetRegistrationModal.test.jsx (new)
- frontend/src/InventoryOperations.test.jsx
- frontend/src/MasterData.test.jsx
- frontend/src/MasterDelete.test.jsx
- docs/phase4c-registration-modal.md (new)

Pre-existing uncommitted backend, deletion and API-helper changes from the preceding task remain intact. Safe master deletion remains subject to its separate, previously documented ACL authorization gate.


## Follow-up commit checkpoint

Reviewed the original 14 modified and 11 untracked paths before committing the combined Phase 4C improvements. Review found and removed an accidental master-delete expression in dashboard stock activity: it referenced Catalog-only variables and would crash for a nonempty activity list. Added a nonempty-dashboard regression in frontend/src/App.test.jsx. This adds one reviewed modified path to the original set.

Fresh checkpoint validation: 406 backend test executions passed (Phase 4A 29, Phase 4B 29, Phase 4C 22, deletion/registration 17, current stock/staging/review 205, historical 45, restricted runtimes 6+6+6, deletion runtime 5, review read proof 20, stock/runtime security 16). Frontend: 72 passed across seven files. Final failures/errors/skips: zero. Total: 478 passed; earlier runs are not added again.

Frontend production build, Django system and migration-drift checks, source/credential scans and whitespace checks passed. Docker registry DNS/timeouts prevented refreshing validation images. Backend suites ran with the current read-only backend bind mount; final frontend tests/build used current read-only frontend/src mounted over cached, unchanged dependencies. No successful fresh image refresh is claimed for this checkpoint. No persistent database operation, deployment, migration, ACL change or execution of the pending SQL example occurred.

The SQL example is credential-free proposed documentation only. Deletion remains subject to separate operational authorization. Private .env, inventory files, backups, logs and generated artifacts are excluded from the commit. The current Git identity is used without changing repository configuration; no push is authorized.
