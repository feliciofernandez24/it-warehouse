# Phase 3B.2 review and approval workflow

PROPOSED, NOT IMPLEMENTED. Applies to the four proposed models in the schema plan. The existing offline command remains unchanged and cannot perform any transition below.

## Permission matrix

All capabilities are explicit inventory app grants through direct user permissions or Django groups, plus authenticated active identity. Never use superuser implication, cached has_perm results, staff status or AssetRecipient as authority. The initial trusted-organization scope and confidential-evidence capability must be enforced server-side; warehouse/tenant restrictions require the additional entitlement design described in the security plan.

| Action | Required permission(s) | Independence / other checks |
| --- | --- | --- |
| Register/upload capture | inventory.capture_import (new) | Active authenticated uploader; verified source; actual identity recorded |
| Start/edit/evidence preparation | inventory.prepare_import (new) | Actor enrolled as contributor; PREPARING only for edits |
| Submit | inventory.prepare_import | Complete server validation; freezes contributor set and content |
| Inspect private source/evidence | inventory.view_import_evidence (new), within the trusted organization | Separate from generic model view; no anonymous access |
| Accept review / return / reject | inventory.review_import (existing) and view_import_evidence | Actor != uploader and every contributor |
| Approve | inventory.approve_import (new) and view_import_evidence | Same independence; a current valid REVIEW_ACCEPT event required |
| Revoke approved decision | inventory.revoke_import (new) | Active authorized revoker; mandatory reason; may be original independent approver |
| Supersede unapproved revision | inventory.prepare_import | Batch lock, current head, successor created atomically |
| Supersede approved revision | inventory.prepare_import + revoke_import | No silent replacement of approval |
| Future promote | inventory.promote_import (existing) + transactions.receive_stock and future policy | Disabled regardless of grant in Phase 3B.2 |

A reviewer may also approve if separately granted both capabilities and independent. An approve-only actor may approve a prior independent review but cannot create their own REVIEW_ACCEPT without review_import. Recheck the prior review actor's active status and current review permission at approval. Neither person may have prepared/uploaded the revision. Three-person separation is an optional organizational policy requiring explicit adoption, not a hidden assumption.

PROPOSED provisioning command would create dedicated Capture Operator, Import Preparer, Import Reviewer, Import Approver and Import Revoker groups with only their listed grants and confidential-view permission where needed. No existing Administrator/stock group acquires import approval automatically. Grants are additive and memberships explicit; provisioning must report existing excess grants rather than claim additive provisioning revokes them. No promotion group is enabled.

## State machine

| From -> To | Operation / authorization | Required validation and committed evidence |
| --- | --- | --- |
| none -> CAPTURED | register_capture / capture_import | Bounded source reparse; immutable 920-row registration; creator participant; CAPTURE event |
| CAPTURED -> PREPARING | start_preparation / prepare_import | Current head; source intact; creator/editor enrolled; START event |
| PREPARING -> PREPARING | edit or preparation evidence / prepare_import | Expected version; source cannot change; enroll editor before change; EDIT/EVIDENCE event |
| PREPARING -> READY_FOR_REVIEW | submit / prepare_import | Nonempty proposed accepted set; complete 897 decisions; immutable snapshot and SUBMIT event |
| READY_FOR_REVIEW -> same | record_review / review_import | Independent review of exact snapshot; REVIEW_ACCEPT event binds all scope decisions |
| READY_FOR_REVIEW -> APPROVED | approve / approve_import | Fresh full verification; independent actor and valid prior review; signed APPROVE event |
| READY_FOR_REVIEW -> RETURNED_FOR_CORRECTION | return / review_import | Independent actor, reason/issues; immutable RETURN event; terminal revision |
| READY_FOR_REVIEW -> REJECTED | reject / review_import | Independent actor, reason; immutable REJECT event; terminal revision |
| CAPTURED/PREPARING/READY_FOR_REVIEW -> SUPERSEDED | create successor / prepare_import | Current head; parent-child continuity; SUPERSEDE event and new CAPTURE event atomically |
| APPROVED -> SUPERSEDED | create successor / prepare_import + revoke_import | Authority ended explicitly; preserve signature/snapshot; linked events and successor |
| APPROVED -> REVOKED | revoke / revoke_import | Current approval, mandatory reason; REVOKE event; snapshot/receipt unchanged |
| RETURNED/REJECTED/REVOKED -> new CAPTURED revision | create successor / prepare_import | Old state remains terminal; one child; new actor and inherited contributors; source unchanged |
| APPROVED -> PROMOTED | Future only | Always rejected in proposed Phase 3B.2 CHECK/services; no inventory writes |

Terminal revisions cannot return to PREPARING or be approved again. Corrections create a new revision, digest, snapshot and review. Supersession is not approval of the successor. CAPTURED to PREPARING to READY to APPROVED are new revision states, not additions to existing RowStatus/BatchStatus in this design.

Every successful operation has one request_id, fingerprint, active actor, capability check, expected version and append-only event. Revision.version equals the last committed event sequence. A deferred trigger rejects an event without its matching revision mutation, a revision mutation without its event, an APPROVED state without its immutable snapshot/review/approval receipt, or an incomplete multi-row capture.

## Per-row labels and scope

BLOCKED, NEEDS_CLARIFICATION, READY_FOR_REVIEW and EXCLUDED_WITH_REASON are preparation labels. Accepted/deferred/excluded is a separate exhaustive scope partition for all 897 candidates. A READY label is never approval; a blocked row may be deferred but never accepted. Exclusions require nonblank explicit reason/evidence, proposed by the preparer and affirmatively accepted by independent review.

A sealed snapshot can contain proposed excluded labels; these are proposed scope decisions until REVIEW_ACCEPT/APPROVE affirm the exact snapshot. The service must distinguish proposed versus effective exclusion and never automatically drop a candidate. Reviewer edits to any scope/reason require return and a new revision/snapshot rather than changing sealed bytes.

Registration reconciliation: 920 = 897 candidates + 21 headers + 2 sequence-only rows, across 15 sheets. Preserve exact row coordinates and worksheet trailing whitespace. Headers/sequence-only are structural, not candidate exclusions. Candidate triage counts sum to 897; accepted + deferred + excluded also equals 897.

All accepted rows must be READY_FOR_REVIEW, have no unresolved blocking/required issue, accepted quantity/tracking policies, approved catalog/SKU and active physical locations, retained source digest, acknowledged warnings and verified evidence. Unselected blocking rows remain visible. Selected/deferred overlap must be reviewed for duplicate physical stock. A blocked duplicate cannot be hidden as deferred while its counterpart is silently accepted.

Current source has zero READY candidates. Submission/approval for an empty accepted set fails; no automatic promotion of the existing 105/792 labels occurs.

## Canonical snapshot contract

Reuse the Phase 3A.1 UTF-8 sorted compact canonical JSON contract and source-row digest domain. Enforce no duplicate keys on JSON ingestion, no floats/NaN/Infinity, canonical decimal strings without exponent/redundant fractional zeros (zero is 0), integer counts/row numbers, nulls for absent values, ISO dates and UTC evidence timestamps with six fractional digits and Z. No Unicode normalization of raw source identity. Pin encoder, Python/Unicode, layout, parser, normalizer and contract versions.

Order arrays explicitly: sheet ordinal then numeric Excel row; cells by numeric column; issues by code/coordinate/evidence ID; dictionaries/evidence/participants by stable IDs or digest; planned lines by source order. Reject duplicate source/line identities. Canonicalization is more than calling the existing generic canonical helper.

Snapshot domain itw.import-preview.v1 binds:

- Workbook SHA-256 from immutable batch; layout/manifest/capture artifact digests and original source-row identities/digests/classifications.
- All 920 structural/source rows and all 897 candidate normalized decisions, issues/dispositions, explicit accepted/deferred/excluded scope and reasons.
- Rule/dictionary content digests and versions, policy/evidence artifact hashes and versions, fixed validation date/timezone, revision number/preparation version and complete inherited contributor IDs.
- Approved ProductModel/category/manufacturer/warehouse/location/specification reference IDs and relevant complete field content; location ancestor chain and active states. An ID or updated_at alone cannot prove unchanged meaning.
- Accepted quantities, units, tracking, missing-value policy and every planned receipt semantic field, including serial_raw/device_name, condition/state, endpoints, metadata and source provenance. Optional fields must be explicit; do not rely on NEW/AVAILABLE/quantity defaults.
- Aggregate row/serialized-unit/bulk-SKU-unit reconciliation and the complete selected receipt plan.

For selected receipts, spell out Request.reason/external_reference and every current Line semantic field: operation_type=STOCK_IN, quantity, asset_id=null, approved product_model_id, source_location_id=null, destination_location_id, source_condition/source_state, condition/state, device_name/serial_raw, recipient_id=null, assignment_id=null, destination_reference/description, purpose, due_at=null and reverses_id=null. Explicit source-row provenance and supported metadata accompany the semantic plan; current Line still cannot carry import_row. Planned posting actor/time policy is explicit cutover policy, never an invented historical actor/date. Future operation keys use a separate noncircular plan-identity derivation, not approval request_id. No stock request is executed in review.

The plan supports only existing-source truthful on-hand receipts: one serialized unit per source row or verified integer bulk PIECE. Multi-unit serialized/split targets, ambiguous packaging and external custody cutover remain blocked until a separate cardinality/custody contract. No invented SKU/specification/location/history.

Exclude render time, random upload-attempt UUID, reviewer signature/time, generated asset tags/PKs and posting results from the preview hash. Actual evidence timestamps stay included. Approval receipt signs snapshot ID/digest and revision identity separately, binding the approval to its specific batch/revision even if another snapshot has identical semantic content. No circular inclusion of receipt signature or stock-operation UUIDs.

This approval-domain snapshot cannot be obtained by merely toggling approval_enabled in a Phase 3B.1 artifact: that artifact has a different domain, unresolved masters and no accepted plan.

## Server verification and signature

Before submission, regenerate authoritative source facts, verify private file/hash/layout/manifest, apply pinned approved policies and build the snapshot server-side. On approval, repeat complete schema/reconciliation/dictionary/evidence/master checks, recanonicalize the persisted frozen proposal and compare stored bytes and DB-computed SHA-256. A client supplies snapshot ID, expected state/version and idempotency key only; a digest is an optional precondition, never truth.

Use a server HMAC-SHA256-v1 receipt envelope with external retained key ID and 32-byte MAC. Fetch key material before the locked transaction; signing itself is local and bounded. Record approval identity, DB timestamp, snapshot digest, review-event ID and reason in the event. Replaying after key rotation verifies against the retained old key, never silently re-signs history. This authenticates the server's recorded decision, not a legal personal signature.

Published dictionaries/evidence use immutable content references. Any replacement, missing artifact, expiry or policy retirement invalidates effective approval and requires a successor/review; no in-place rehash/repair. Master drift before approval rejects approval. After approval, relevant master changes are serialized and refused until explicit revoke/supersede; exact compared fields are pinned by contract. Effective-validity checks additionally detect external artifact loss or privileged bypass.

APPROVED is historical revision state. Effective approval additionally requires no terminalization, matching artifacts/current master contents and current active independent reviewer/approver grants. Supported destructive permission changes require prior/atomic REVOKE events; historical APPROVE events remain unchanged. A read-side mismatch also fails closed. Grant restoration never reactivates a REVOKED revision; a new reviewed revision is required.

## Transactions and races

Parsing/expensive artifact reads and key retrieval happen before the write transaction. Verified content-addressed objects must remain immutable; final in-transaction byte/digest availability checks use the pinned object, not an arbitrary client path. No external network/object-store operation is held across the engine lock.

Use READ COMMITTED, not a stale repeatable-read snapshot. Every review write first acquires transaction advisory lock (73921,2), then ImportBatch row, revision rows in revision-number order, snapshot row, source rows in Excel order if needed, participant/event rows. Read current authorization from the database after obtaining the lock, without cached auth or pre-lock user row locks. No review transaction calls posting or locks balances/assets.

New review source/master/auth mutation entry points must acquire that same advisory lock before any row mutation locks. PROPOSED BEFORE STATEMENT coordination covers relevant auth_user, auth_group, user/group membership and permission-grant tables, auth_permission/content-type changes, and referenced catalog/specification/location/warehouse master mutations. Existing engine functions/guards are preserved. Auth/group provisioning and administrative writers must adopt the lock-first protocol too; arbitrary SELECT FOR UPDATE before this lock is forbidden in supported service/admin paths.

After waiting, refetch actor/grants/state/version and then decide. Permission revocation committed first prevents approval. If approval commits first, a destructive grant/user-state change must explicitly revoke the affected import approval before changing authority under the same lock; uncoordinated destructive changes fail closed. This prevents restoring a grant from resurrecting an old approval. Grant writers cannot change authority midway through a locked decision. Without reviewed auth coordination, this guarantee is NOT implemented and must block deployment.

A simultaneous edit/submit/approve cannot all succeed: the first locked version wins; stale requests fail EXPECTED_VERSION_CONFLICT. Submitted content cannot be edited even by a preparer. Supersession/revocation winning first blocks approval; approval winning first forces the competing operation to use approved-state authorization.

Duplicate approval with the same request_id/fingerprint/actor returns original receipt and current state after current access authorization. Different request IDs racing for one revision yield one success; unique APPROVE revision index prevents a second signature. Same key with changed actor/payload fails. Revoked/superseded history is never presented as currently authorized just because a receipt exists.

State, event, participants, snapshot and signature commit in one transaction; force deferred checks before outer commit and publish success only afterward. Failed signing/validation/constraint checks roll everything back. Notifications use on_commit. Never catch DB exceptions inside a broken atomic block or report a generated signature as committed before commit succeeds.

Use bounded timeouts. Retry a whole transaction after a deadlock/serialization error with the same request identity; do not retry only an inner statement. Single-lock serialization deliberately favors correctness over throughput.
