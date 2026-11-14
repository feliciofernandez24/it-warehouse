# Phase 3B.2A implementation

Date: 2026-11-13, Asia/Tokyo. Actual HEAD before changes: 56fb442 on develop. Four Phase 3B.2 design documents were already untracked and were preserved. This implementation stops at the schema stage.

## IMPLEMENTED files

| File | Change |
| --- | --- |
| backend/apps/inventory/models.py | Modified: expose four review models; add reviewed capture/prepare/approve/revoke/evidence permission declarations. Existing stock fields and services unchanged. |
| backend/apps/inventory/review_models.py | New: four sensitive models, lifecycle/action enums, constraints and safe representations. |
| backend/apps/inventory/migrations/0002_import_review_schema.py | New: additive schema/permission metadata; depends on actual transactions.0005 graph; forward-only. |
| backend/apps/inventory/migrations/0003_import_review_guards.py | New: review/source integrity functions and triggers; no approval implementation. |
| backend/apps/inventory/test_review_schema.py | New: 48 synthetic schema/concurrency cases. |
| backend/config/historical_inventory.py | New: isolated historical app registry, excluding the four review models only in the test process. |
| backend/config/historical_inventory_migrations/__init__.py | New: historical migration namespace. |
| backend/config/historical_inventory_migrations/0001_initial.py | New: imports the unchanged original Migration class; no copied/rewritten historical SQL. |
| backend/config/settings/historical_tests.py | New: guarded settings for the separate disposable historical database. |
| docs/phase3b2a-implementation.md | New: implementation/status report. |
| docs/phase3b2a-migration-review.md | New: SQL/locking/privilege review. |
| docs/phase3b2a-testing.md | New: exact validation commands and results. |
| docs/phase3b2a-security-limitations.md | New: explicit deferred controls and deployment blockers. |

No existing tests, transaction migrations/services, stock/audit guards, React files, credentials or Compose files were changed.

## IMPLEMENTED model fields

All foreign keys use PROTECT. New models have no default CRUD permissions, no admin registration, no API or functional service. Their string/repr identifies only model and internal PK, never source values.

- ImportPreparationRevision: UUID id; batch; revision_number; optional unique parent; state; version; created_by/created_at; layout_digest; manifest_digest; capture_storage_key; capture_artifact_digest; draft_payload.
- ImportRevisionParticipant: BigAutoField id; revision; user; first_seen_at; unique revision/user.
- ImportPreviewSnapshot: UUID id; unique revision; canonical_bytes; digest; created_at. Bytes are bounded to 32 MiB.
- ImportReviewEvent: BigAutoField id; revision; sequence; unique request_id; request_fingerprint; actor/recorded_at; kind/from_state/to_state; optional snapshot/source_row; reason_code/reason/details; optional review_event/signature_algorithm/signing_key_id/signature. No signature is issued in this phase.

There are 27 named model constraints, plus PK/FK/field unique constraints and supporting indexes. They cover unique active revision, batch revision number, positive number/version/sequence, enum/parent shapes, hex digests, nonblank keys/reasons, JSON objects, byte limits, event sequence, one potential approval per revision, contributor uniqueness and signature null/size shape. SQL NULL semantics for signature metadata are explicitly constrained.

DB triggers assign insertion timestamps and enforce history/state integrity. Draft payload is bounded to 32 MiB; event details to 1 MiB and reason text to 32,767 characters. No raw inventory appears in ordinary model representations or static guard error codes.

## TESTED database invariants

| Invariant | Enforcement |
| --- | --- |
| One active revision | Partial unique batch index for CAPTURED/PREPARING/READY_FOR_REVIEW/APPROVED |
| Revision lineage | Shared lock then batch lock; max number + 1; immutable same-batch immediate predecessor; unique parent |
| Initial capture | State CAPTURED, version 1, empty draft; sequence-1 CAPTURE self-transition by creator/uploader; explicit capture grant; creator enrollment |
| Participants | Append-only; enroll preparation-event actors; inherit predecessor contributors; additions frozen after submission |
| Event history | Append-only; sequence/version/to-state and prior-event chain agreement; deferred final evidence check |
| Draft changes | Only PREPARING -> PREPARING with a new event/version and matching internal DB payload digest |
| Snapshot | One per revision; byte hash verified; UTF-8 JSON equals frozen draft; insert only at structural submission; no UPDATE/DELETE |
| Source ownership | Event source row belongs to revision batch; snapshot and event revision match |
| Registered source | Freeze captured rows and batch identity/legacy approval fields; ordinary batch notes remain editable |
| Legacy adoption | Reject reviewed/APPROVED/PROMOTED batch adoption and promoted source rows |
| Independent review events | REVIEW_ACCEPT/RETURN/REJECT require active explicit review/evidence grants and actor distinct from uploader/all contributors |
| Approval/promotion | Hard rejection of APPROVE/REVOKE issuance and APPROVED/REVOKED/PROMOTED state transitions |
| Rollback / concurrency | Missing evidence fails at deferred check; competing initial revisions yield one commit; no stock effects |

No application endpoint or command drives the new lifecycle. Successful schema transitions in tests are privileged, synthetic fixtures only.

## Structural submission is not verified readiness

A schema fixture may seal a snapshot in READY_FOR_REVIEW only with a byte hash, matching draft, exact registered source-row coverage, matching source/layout/manifest digest metadata and complete candidate label/scope coverage. It must explicitly say verification_status=STRUCTURAL_ONLY.

This is not complete Phase 3B.2 submission validation. SQL does not establish canonical spelling, physical truth, approved mappings, complete receipt semantics, evidence availability, dictionary authenticity or a trusted authenticated human actor. Empty accepted scope and unresolved mapping semantics are not certified by this stage. Full submission/approval services are BLOCKED; Stage A never treats a structural snapshot as approvable.

The source workbook was not registered into PostgreSQL. Its existing 897 candidates remain 105 BLOCKED and 792 NEEDS_CLARIFICATION, zero approved; no real row is advanced.

## Validation and next boundary

All 142 original behavioral cases are preserved: 97 on the current schema, 45 on a separate historical schema. There are 48 new cases: 190 total passing across the two isolated suites, no final failures/skips. See the testing report for chronology and exact commands.

Migrations were applied only to disposable PostgreSQL databases/test databases. Development PostgreSQL and its persistent volume were never connected or modified. No source edits, live records, stock movements, approval issuance, signing keys, commit or push.

Before Phase 3B.2B, review generated SQL, ownership/grants, authenticated actor trust, canonical/full-plan verification, permission/master coordination, retention and key policy. Do not apply these migrations to development until separately reviewed and authorized.
