# Phase 3B.2B.1 implementation report

## Starting state and scope

Branch develop, HEAD 45acda8 (feat: implement Phase 3B.2A hardened import review schema).
The initial working tree and index were clean. The prior reported staged/CRLF condition was
not present; no prior work needed repair. No commit, push or staging was performed.

Implemented authenticated internal authorization and fail-closed future service interfaces,
plus an executable isolated read-only restricted PostgreSQL proof. Registration/review writes
remain unavailable. This is not a live importer or operational review workflow.

## Exact file inventory

All files below are new; no pre-existing tracked file was changed.

- backend/apps/inventory/review/__init__.py: module boundary.
- backend/apps/inventory/review/errors.py: fixed sanitized error codes and retry classification.
- backend/apps/inventory/review/authorization.py: trusted User, fresh direct/group grants,
  independent-review validation.
- backend/apps/inventory/review/services.py: seven reserved interfaces, read-only locked
  preflight, version/fingerprint/replay checks, disabled approval/revocation/promotion.
- backend/apps/inventory/review/gateway_poc.sql.example: isolated read-only SQL proof,
  restricted NOLOGIN owner and nonsuperuser runtime; no production installer.
- backend/apps/inventory/test_review_services.py: synthetic authorization, replay, rollback,
  concurrency and disabled-operation tests.
- backend/apps/inventory/test_review_gateway.py: real restricted LOGIN privilege tests.
- docs/phase3b2b1-authentication-architecture.md.
- docs/phase3b2b1-database-gateway.md.
- docs/phase3b2b1-security-testing.md.
- docs/phase3b2b1-implementation-report.md.

## Implemented versus deferred

Implemented: no automatic staff/superuser authority; uncached permissions; active-user checks;
separate evidence requirement; uploader/creator/contributor separation; bounded sanitized
requests; advisory lock before revision locks; expected-version validation; exact historical
preflight matching; explicit conflicts; sanitized retry classification; no service writes.
The read-only proof has narrow SQL signatures, fixed search_path, qualified relations,
PUBLIC EXECUTE revocation, restricted column grants and runtime login tests.

Deferred: authenticated capture registration, all operational state/event/participant writes,
independent DB identity attestation, permission/master-data race coordination, durable original
write results, verified business snapshots, operational endpoints and production provisioning.
There is no new migration, no changed model, and no guard exception for gateway roles.
The proof cannot issue mutations under the existing owner-only guards.

## Validation and preservation

250 tests passed: 218 existing plus 32 new; zero failures/skips in the final runs.
Fresh committed migrations succeeded only in the disposable database and model drift was absent.
The initial focused run exposed three synthetic fixture mistakes; all were corrected before
the final regression runs. No production behavior or committed guard was changed to accommodate tests.

The protected-file digest comparison checks all pre-existing backend Python files and the
original workbook against their starting SHA-256 values. Existing migrations and the Phase 2C
engine/guards remain byte-identical. Git index stays unchanged, new text uses LF, and whitespace
validation reports no errors. No private source artifacts or inventory values were added.
The source workbook was not modified; no original candidate was processed or advanced.

Only the explicitly named disposable PostgreSQL container was accessed. No development
PostgreSQL inventory was read or modified and no persistent volumes were reset.
Synthetic test fixtures create isolated state only; the service itself creates no stock or
review records. Approval/revocation issuance and live stock promotion remain disabled.

## Remaining decisions

See the database-gateway document for the deployment blockers. Owner/security approval is
required for the identity and role model, coordination protocol, narrow guard-compatible
mutation design and later migration proposal. Physical/source-data verification remains a
separate prerequisite from authentication; missing workbook facts are never fabricated here.

Stop at Phase 3B.2B.1. The next phase is not authorized or automatically enabled by this work.
