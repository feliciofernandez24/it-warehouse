# Phase 3B.2 architecture — Stage 1 design

Design only, 2026-11-13 (Asia/Tokyo). Inspected clean develop at baseline 56fb442. EXISTING means repository code, not an assertion about installed development schema. PROPOSED and NOT IMPLEMENTED mean no corresponding model, migration, service or grant was created.

## Verified existing boundary

| EXISTING component | Verified behavior / limit |
| --- | --- |
| ImportBatch | public_id, filename/hash/storage key, uploader/time, mapping_version/timezone, status, reviewer/time, approved_preview_digest and notes. Hash is indexed, not unique. Reviewer differs from uploader only. Approval fields do not prove an immutable payload. |
| ImportStagingRecord | Unique batch/worksheet/one-based row; raw_values, normalized_values, errors/warnings, status, source_row_digest, promoted target/time. PROMOTED requires exactly one asset/balance target. No preparer list or immutable revision. |
| BatchStatus | UPLOADED, VALIDATED, IN_REVIEW, APPROVED, PROMOTED, FAILED, REJECTED. No PREPARING, SUPERSEDED or REVOKED. |
| RowStatus | CAPTURED, INVALID, READY, IGNORED, APPROVED, PROMOTED, REJECTED. Distinct from the four design labels. |
| Other inventory enums | Tracking SERIALIZED/BULK; condition NEW/USED/REFURBISHED/BROKEN/UNKNOWN; lifecycle AVAILABLE/QUARANTINED/ASSIGNED/DISPOSED/LOST; bulk state AVAILABLE/QUARANTINED; serial review UNREVIEWED/VERIFIED/DUPLICATE/MISSING. |
| Offline staging | Bounded XLSX parsing, exact profile, canonical source/layout/manifest digests, proposal-only normalization and private content-addressed capture. Local OS authorization; no authenticated uploader/reviewer, DB staging writes, exclusion or approval. |
| Canonical helper | Sorted compact UTF-8 JSON; no floats; raw strings preserved. It does not itself validate JSON duplicate input keys, schema, array order or semantic completeness. |
| Permissions | inventory.review_import and inventory.promote_import declared on ImportBatch; default Django model permissions also exist. Stock services explicitly query transactions grants, ignore superuser implication/cache and reload actors. |
| Posting | Complete requests, immutable StockOperation/history, advisory transaction lock (73921,2), permission/approval checks, ledger/custody constraints and audit freezes. Import-linked movement insertion is explicitly rejected by 0004; 0005 does not enable it. |
| Accounts/audits | AssetRecipient is a recipient identity, not review authority; use AUTH_USER_MODEL for actors. AssetChangeLog is append-only but has generic entity_kind/entity_pk rather than review-specific FK/state enforcement. |
| Deployment | Runtime-role SQL is a review template; grants SELECT broadly and inventory DML, not approval authority. Existing stock-role provisioning grants stock capabilities only and does not assign memberships. Installed roles were not queried. |

Reviewed inventory models/choices/staging/command; transactions models/services/0001–0005 and role provisioning; account/audit/common models; migration graph and tests; all eight requested Phase 3A.1/3B.1 documents. Tests inspected include 43 historical inventory-schema tests, two historical PostgreSQL transaction tests, 59 current engine tests, 37 staging tests and the health test: documented baseline 142. They were not rerun for documentation-only changes.

## Recommended minimal entities — PROPOSED

Four new inventory models:

1. ImportPreparationRevision: batch-local revision identity, parent, editable preparation payload, source-artifact bindings and authoritative lifecycle projection.
2. ImportRevisionParticipant: append-only preparer/editor user set, including inherited contributors.
3. ImportPreviewSnapshot: exactly one immutable canonical submitted payload per revision. Created at READY_FOR_REVIEW, before approval; approval never edits it.
4. ImportReviewEvent: append-only typed transition/review/evidence/approval events, including approval receipt/signature metadata and idempotent request identity.

Reuse ImportBatch as the immutable source envelope and ImportStagingRecord as captured source rows, never as mutable revision storage. Reuse AssetChangeLog for cross-system notifications only if later needed; duplicating the same full review history there is unnecessary. An approval signature is one APPROVE event, not a fifth approval table. Supersession/revocation are events plus guarded revision state, never deletion or replacement of snapshot bytes.

No new product/warehouse/location masters are created by this subsystem. Their approved IDs and relevant content snapshots are bound in canonical payloads. No source-consumption/posting tables are proposed for implementation in Stage 1; those remain necessary before eventual promotion.

    ImportBatch --< ImportStagingRecord
         |
         +--< ImportPreparationRevision --0..1 ImportPreviewSnapshot
                    |
                    +--< ImportReviewEvent --0..1 source row
                    +--< ImportRevisionParticipant --> authenticated user
                    parent --> previous revision in the same batch

Every relationship and immutability rule is specified in the [schema plan](phase3b2-schema-migration-plan.md). Source row ownership and snapshot/event ownership require DB cross-row guards, not merely foreign keys.

## Lifecycle ownership

New revision states are separate from existing batch/row enums. ImportBatch.status remains source-registration compatibility metadata (UPLOADED/VALIDATED/IN_REVIEW), not review approval authority. Its legacy reviewer/digest fields must stay unset for newly managed batches. The new revision/snapshot/APPROVE event exclusively define approval. Existing APPROVED/PROMOTED batches, if any, require a separately reviewed adoption plan; do not silently migrate their meaning.

Captured source rows remain CAPTURED with no promoted targets. Per-revision labels, accepted/deferred/excluded scope and evidence belong in revision/snapshot payloads. Approval does not mark existing staging rows APPROVED because that would conflate independently reviewed revisions and future stock promotion.

One active revision per batch avoids competing approval heads. Creating a successor terminalizes its predecessor atomically; an approved predecessor requires explicit supersession/revocation authority. Immutable snapshots remain readable after their authority ends.

## Snapshot and service boundary

PROPOSED services: register_capture, start_preparation, edit_revision, submit_revision, record_review, approve_revision, return_revision, reject_revision, supersede_revision and revoke_approval. Authenticated actors and explicit capabilities are required. No generic update endpoint or writable admin exists for state, participants, snapshots or events.

Registration reparses verified source bytes under Phase 3B.1 limits, verifies the private artifact rather than trusting its JSON, and captures all 920 populated rows atomically with uploader identity. Previously captured offline files are evidence, not authenticated upload records. No import of all 897 candidates into review-ready state occurs automatically.

Submission freezes all decisions and complete planned receipt semantics into canonical bytes. Approval recomputes verification from server-held source/dictionaries/evidence/masters and compares persisted bytes and digest, rather than accepting a browser digest. The receipt attests to those exact bytes. See the [workflow](phase3b2-review-approval-workflow.md).

## Decisions recommended for review

- Adopt four models, a single immutable snapshot per submitted revision and append-only events instead of mutable approved JSON.
- Allow one independent person to perform both review and approval only with both explicit permissions; both must differ from uploader/all contributors. Three-person review can be added as a policy, not assumed.
- Use server HMAC approval receipts (not legal user digital signatures); external key storage and key retention need deployment approval.
- Serialize review and relevant authorization mutations using the existing engine lock. Adding auth/master coordination triggers and restricted procedures needs explicit migration/security review.
- Use DB-protected snapshot bytes as approval authority, retaining encrypted external raw artifacts. Final retention duration and backup/key policies remain organizational decisions.
- Keep first planned receipts on-hand, single-unit serialized or verified bulk PIECE only. Package units, multi-target source rows and custody cutover remain unsupported.

Owner SKU/condition/tracking/location/quantity policy and physical exceptions remain unresolved. Current 897 candidates stay 105 BLOCKED and 792 NEEDS_CLARIFICATION, zero ready/approved. No empty or blanket approval is permissible.

## Safe implementation order — NOT IMPLEMENTED

Review these documents and resolve deployment/signature/retention decisions first. Then implement additive source/revision schema, constraints and immutable capture; controlled permissions and grants; canonical snapshot/validation; review/approval/event transactions; revocation/supersession; and isolated adversarial/concurrency tests. Review generated SQL and rehearse on disposable PostgreSQL before any separately authorized development migration.

Authenticated internal UI/API can follow only after service/security tests. Import promotion, source consumption and any change to import-posting guards require a later phase. This stage creates only four documents; implementation must await review.
