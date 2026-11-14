# Phase 3B.2 schema and migration plan

PROPOSED ONLY. No Python model, migration file, SQL function, trigger, role or grant is implemented by this document. Baseline: develop 56fb442; inventory.0001 and transactions.0001 through .0005 exist.

## Conventions

Use plain Django models with the explicit fields below, not TimestampedModel: its mutable updated_at/version behavior is inappropriate for immutable snapshots/events. Existing models remain unchanged in this stage.

All FKs use on_delete=PROTECT and matching database FKs; none cascade-delete evidence. Existing User is referenced through settings.AUTH_USER_MODEL. Required means NOT NULL; optional means NULL, never an empty identifier. Django FK indexes are retained unless a specified leading composite index already covers them. All SHA-256 columns are lowercase CharField(64) with DB hexadecimal checks. JSON uses JSONField/jsonb; canonical bytes use BinaryField/bytea and remain authoritative.

Retention R: all new records and source references are retained for the approved inventory-evidence retention period, with legal/incident holds if organizationally required. No runtime deletion, cascading purge or automatic cleanup. Final duration and restricted archival/purge process need owner approval; backups and signing keys must cover the same evidence lifetime. This applies to every field below, including superseded, rejected and revoked revisions.

## ImportPreparationRevision

| Field | Type / nullability | FK / uniqueness / index | Enforcement / mutability |
| --- | --- | --- | --- |
| id | UUID PK, required, generated server-side | PK unique | Immutable identity |
| batch | FK ImportBatch, required | Composite (batch, revision_number) unique | Immutable source owner |
| revision_number | PositiveBigInteger, required | Same composite; DB > 0 | Monotonic batch-local allocation under batch lock |
| parent | OneToOne self FK, optional only for revision 1 | Unique nonnull parent; FK index | Immutable; DB same batch, parent number = number-1, no cycle |
| state | Char(24), required | CHECK enumerated states; partial unique batch while active | Only controlled transitions; no ORM/direct UPDATE grant |
| version | PositiveBigInteger, required, starts 1 | DB > 0 | Increment exactly once per successful event; optimistic expected-version check |
| created_by | FK User, required | FK index | Immutable, active explicit prepare/capture authority on creation |
| created_at | timestamptz, required, DB time | No standalone index | Immutable |
| layout_digest | Char(64), required | Hex CHECK, not unique | Immutable capture binding |
| manifest_digest | Char(64), required | Hex CHECK, not unique | Immutable capture binding |
| capture_storage_key | Char(255), required | Nonblank; not unique | Immutable private artifact locator, never public URL |
| capture_artifact_digest | Char(64), required | Hex CHECK, not unique | Immutable complete private artifact hash |
| draft_payload | JSON object, required | No GIN index; CHECK object | Only PREPARING through controlled edit; freeze permanently on submission/terminalization |

States: CAPTURED, PREPARING, READY_FOR_REVIEW, APPROVED, RETURNED_FOR_CORRECTION, REJECTED, SUPERSEDED, REVOKED. PROMOTED is a documented future state but deliberately excluded from the Stage 2 implementation CHECK and transition functions until a later migration.

Active-state partial uniqueness is on batch where state is CAPTURED/PREPARING/READY_FOR_REVIEW/APPROVED. Creating a successor first terminalizes the predecessor in the same transaction. Latest revision numbers are verified against all prior revisions, not merely active ones. RETURNED/REJECTED/REVOKED may have one successor; history is never reactivated.

draft_payload holds versioned decisions/proposals/evidence references and planned semantics, not another copy of original raw workbook cells. Source hash is read from immutable batch.file_sha256, avoiding a second authoritative workbook hash column. Capture bindings may repeat across revisions, intentionally referring to unchanged source evidence.

## ImportRevisionParticipant

| Field | Type / nullability | FK / uniqueness / index | Enforcement / mutability |
| --- | --- | --- | --- |
| id | BigAutoField PK, required | PK | Append-only identity |
| revision | FK revision, required | Unique (revision,user); leading composite index | Insert only while revision CAPTURED/PREPARING |
| user | FK User, required | FK index for conflict queries | Creator and every semantic editor automatically enrolled; inherited contributors copied |
| first_seen_at | timestamptz, required, DB time | No standalone index | Immutable |

No editable role flag: every participant is disqualified from reviewing/approving that revision. An inspector whose evidence is incorporated as preparation is recorded as a contributor when identified as an authenticated system actor. Immutable external evidence identifies other observers without inventing accounts.

DB transition/edit procedures enroll the actor before accepting any semantic edit/evidence change. Successor creation copies the union of predecessor participants and its creator; conservative carry-forward prevents cloning from laundering preparer involvement. Participants cannot be removed, changed or added after submission. Review-only comments on a sealed payload do not make the reviewer a preparer; any content change requires a successor revision and contributor enrollment.

## ImportPreviewSnapshot

| Field | Type / nullability | FK / uniqueness / index | Enforcement / mutability |
| --- | --- | --- | --- |
| id | UUID PK, required | PK unique | Immutable |
| revision | OneToOne FK revision, required | Unique revision | Exactly one submitted snapshot; never replaced |
| canonical_bytes | BinaryField, required | No index; proposed max 32 MiB CHECK | Full submitted approval-domain payload in private DB storage |
| digest | Char(64), required | Nonunique B-tree index for integrity lookup; hex CHECK | DB hash of exact bytes must match; no cross-batch uniqueness shortcut |
| created_at | timestamptz, required, DB time | No standalone index | Immutable |

Created only by submission. Snapshot bytes contain contract/rule versions, all source identities, all candidate decisions and complete selected plan. No JSON duplicate column or separate mutable approval flag is needed. Server parses bytes with strict schema; DB parses UTF-8 JSON and compares against server-submitted revision projection plus relational proofs. See verification boundary below.

Snapshot is immutable in READY_FOR_REVIEW as well as APPROVED. Deferred constraints require exactly one snapshot once submitted, an associated SUBMIT event and consistency with the frozen revision. Parent terminal states may lack a snapshot only if never submitted.

## ImportReviewEvent

| Field | Type / nullability | FK / uniqueness / index | Enforcement / mutability |
| --- | --- | --- | --- |
| id | BigAutoField PK, required | PK | Append-only |
| revision | FK revision, required | Unique (revision,sequence); FK index subsumed | No reassignment |
| sequence | PositiveBigInteger, required | Same unique key; >0 CHECK | Equals new revision.version; contiguous under lock |
| request_id | UUID, required | Globally unique | Retry identity, not stock operation identity |
| request_fingerprint | Char(64), required | Hex CHECK | Server recomputes actor/action/expected version (sequence-1)/snapshot/reason/details fingerprint |
| actor | FK User, required | FK index | Authenticated active actor; explicit capability; no supplied username |
| recorded_at | timestamptz, required, DB time | Composite (revision,recorded_at,id) for audit ordering | Immutable; timestamps not event identity |
| kind | Char(24), required | CHECK enumerated action | CAPTURE, START, EDIT, EVIDENCE, SUBMIT, REVIEW_ACCEPT, RETURN, REJECT, APPROVE, SUPERSEDE, REVOKE |
| from_state | Char(24), required | State CHECK | DB matches previous state; CAPTURE special initial self-transition |
| to_state | Char(24), required | State CHECK | DB action/transition matrix; comments/review may retain state |
| snapshot | FK snapshot, optional | FK index | Required for submission and all actions on sealed revision; same revision enforced |
| source_row | FK ImportStagingRecord, optional | FK index | Optional row-level evidence/decision; DB same batch |
| reason_code | Char(64), required | Nonblank CHECK | Controlled static code; not a raw source value |
| reason | Text, required | Nonblank CHECK; no index | Restricted human explanation; append corrections rather than UPDATE |
| details | JSON object, required | No GIN index; CHECK object, bounded size | Versioned evidence refs/hashes, dispositions, changed field refs, prior/next digest, related revision ID and policy refs |
| review_event | FK self, optional | FK index | Required for APPROVE only; points to prior REVIEW_ACCEPT of same revision/snapshot |
| signature_algorithm | Char(32), optional | CHECK null or HMAC-SHA256-v1 | APPROVE requires it; all other events null |
| signing_key_id | Char(128), optional | No index | APPROVE requires nonblank retained key identifier |
| signature | BinaryField, optional | DB length 32 for APPROVE | MAC of canonical receipt envelope; never a shared secret stored in DB |

A partial unique index permits one APPROVE event per revision. Return/reject/revoke/reapprove never reuse the same sealed revision. A repeated request_id must match fingerprint and actor exactly; return original event plus current state, not a new signature. Changed payload/actor is a conflict.

The signed receipt envelope reconstructs from event request_id, revision/snapshot IDs and digest, actor ID, DB timestamp, review_event ID, reason, signature algorithm/key ID and contract version. The service obtains a DB timestamp in the transaction, constructs canonical bytes and computes MAC with a preloaded external key; the procedure checks event/time/context consistency. There is no external KMS network call while holding locks. This is a server attestation of authenticated approval, not a personal certificate/digital signature.

## Existing-table integration

No existing field removal, rename or enum rewrite. Future registration atomically inserts ImportBatch and captured ImportStagingRecord rows, verifies 920/897/21/2 accounting and creates revision 1/CAPTURE event/participants. Raw staging capture stores classification/section metadata under immutable normalized_values.capture; revision proposals never overwrite it.

PROPOSED additive triggers prevent edits to batch source identity, uploader/time/timezone/mapping version and capture storage key, and prevent INSERT/UPDATE/DELETE of source rows once a revision has registered the capture. Existing deletion guards remain. Runtime writes to legacy batch reviewer/digest/APPROVED/PROMOTED fields are denied for newly managed batches. The new lifecycle is not projected into those insufficient legacy fields.

Existing rows, if any, receive no automatic capture/approval backfill. Offline files must be explicitly registered by an authenticated uploader. Unexpected historical APPROVED/PROMOTED metadata causes adoption to fail closed pending separate review.

## DB versus service verification

DB CHECK/UNIQUE/FK/trigger/procedure enforcement: enums; source ownership; participant completeness for edits; independent actors; current explicit grants; immutable source/snapshot/event bytes; state/version/event agreement; request uniqueness; one active revision; approved snapshot/event/review link; all-selected rows structurally admissible; total source coverage; positive integer quantities; valid tracking/unit/condition/state; active referenced masters and exact compared master-field content; import promotion forbidden.

Use PostgreSQL 17 SHA-256 over bytea for snapshot digest verification; no pgcrypto extension is required just for hashing. Parse UTF-8 bytes and compare JSON semantic content with locked revision/source rows. Do not hash jsonb::text and claim it equals Python canonical bytes.

The trusted service validates canonical byte spelling/order, duplicate JSON keys, source parsing, formula/lexical fidelity, dictionary signatures/versions, evidence availability/MACs and physical-fact policies. DB cannot prove a physical observation, read external files, verify an external-secret MAC or establish HTTP user identity. Privileged procedures independently check stored hashes/relations/scopes; they do not claim full canonical-encoder equivalence. Runtime cannot insert a snapshot/event via ordinary ORM DML. Application compromise and database-owner bypass remain explicit trust limits.

## Proposed migration units — none created

| Proposed file | Dependencies / exact purpose |
| --- | --- |
| inventory.0002_import_review_schema | inventory.0001, transactions.0005 and swappable auth dependency. Create the four models, CHECK/FK/UNIQUE/index definitions; add inventory custom capture_import, prepare_import, approve_import, revoke_import, view_import_evidence while retaining review_import/promote_import. New models set default_permissions=() to avoid accidental CRUD grants. |
| inventory.0003_import_review_guards | inventory.0002. Add immutable source/participant/snapshot/event guards, transition procedures, deferred state/event completeness, DB grant checks and lock coordination for review plus relevant auth/master mutations. Reject PROMOTED and all stock-side effects. Do not edit transactions migrations or replace posting guards. |

Exact file names are proposals, subject to the migration graph at implementation. They are forward-only operational migrations: no runtime downgrade that destroys evidence, no reverse SQL dropping populated review tables, and no stock DML/automatic approval/backfill. Future source-consumption/posting schema is outside both units.

Privileged procedure ownership, EXECUTE revocation from PUBLIC, role grants and key provisioning use separately reviewed deployment SQL after migrations, not a migration that grants broad rights to unknown existing logins. Django post_migrate creates permission metadata only; group membership remains manual/explicit.

## Migration safety

Inspect generated sqlmigrate output, catalog dependencies, function security/search paths and no-stock-DML assertions before applying anywhere. First rehearse a fresh database and a disposable restore; run the unchanged 142 baseline plus planned tests. Verify source hashes/private artifacts separately. Test that guards are installed atomically and ordinary DML is denied.

Never alter historical 0001–0005 files. Do not connect to development in this design stage. Later deployment needs reviewed backup, authorization to apply, bounded lock_timeout/statement_timeout and maintenance plan for auth/master triggers. Failure rolls back the forward migration; recovery is a reviewed repair migration, never trigger disablement or deleting inventory volumes.
