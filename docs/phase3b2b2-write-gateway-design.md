# Phase 3B.2B.2 write gateway design

Status: proposal only. See [architecture](phase3b2b2-capture-architecture.md) for trust and artifact definitions and [transaction](phase3b2b2-registration-transaction.md) for write order.

## Guard compatibility decision

0003 compares current_user to each protected table's relowner. SECURITY DEFINER switches current_user to the function owner; a separate function owner with ordinary INSERT grants still fails. Do not add GUC bypasses, special runtime exceptions, disable triggers, change existing migrations or grant runtime owner membership.

Proposed resolution: a dedicated NOLOGIN review owner owns the capture function AND the existing seven import/review tables (ImportBatch, ImportStagingRecord, ImportSourceProfile, ImportPreparationRevision, ImportRevisionParticipant, ImportPreviewSnapshot, ImportReviewEvent), their owned sequences and new capture metadata tables. It owns no stock/auth/warehouse tables. Transfer ownership in a reviewed forward migration/deployment step, preserving relowner equality checks unchanged. Related identity sequences, indexes and constraints must be catalog-audited; use explicit object lists, never broad REASSIGN OWNED.

The owner has inherent broad privileges over its own review tables, including snapshots and profiles, but exposes exactly one capture-only entrypoint. This is privileged code, not column-grant containment against a compromised function body. Runtime cannot assume the owner. Existing migrations need a controlled migration administrator able to manage this owner without giving that membership to any application role. This ownership change requires independent review before implementation; if unacceptable, capture remains disabled rather than weakening guards.

## Proposed roles and grants

| Role | Proposed boundary |
| --- | --- |
| migration administrator | Controlled offline DDL/ownership authority; no request traffic |
| itw_review_owner | NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; owns listed review objects, private schema and capture function |
| itw_capture_runtime | Dedicated restricted LOGIN; schema USAGE and exact public gateway EXECUTE only |
| identity broker / capture verifier | Separate signing services; no review DML or database owner membership |
| evidence reader | Separate service with explicit evidence authorization; no capture mutation grants |

Runtime receives no direct SELECT/DML/TRUNCATE/REFERENCES/TRIGGER/sequence/schema CREATE privileges, no helper EXECUTE, no role membership, no ability to set replication role or disable triggers. Review owner receives selected-column SELECT on auth_user(id,is_active), auth_permission(id,content_type_id,codename), django_content_type(id,app_label,model), direct/group membership joins. It receives no auth mutation or stock mutation grants. Existing invoker trigger helpers needed by owner are explicitly executable by owner only; audit all their dependencies.

Revoke PUBLIC schema access/CREATE and function EXECUTE in the creation transaction, before runtime exposure. Revoke default PUBLIC EXECUTE for future functions created by the owner. Audit database CONNECT/TEMP and public schema grants across all runtime memberships; NOINHERIT alone does not prevent SET ROLE into a granted role. Grant only required database CONNECT. Private objects are inaccessible to web runtime except the one function.

## Proposed SQL interface

Design signature (not installation SQL):

itw_capture.register_v1(request_id uuid, request_bytes bytea,
                       identity_assertion bytea, verifier_assertion bytea,
                       capture_bytes bytea)
RETURNS TABLE(batch_public_id uuid, revision_id uuid, event_id bigint,
              receipt_digest text, result_bytes bytea)

request_bytes is a bounded canonical itw.capture-request.v1 object containing actor ID, action register_verified_capture, null revision/version, envelope and request fingerprint inputs. It is a signed internal protocol, not a client-controlled actor field in the existing B.1 payload. The future adapter derives actor from request.user; it must not relax B.1 reserved-key rejection. Capture bytes are sent once; SQL derives source rows and manifest from them, rather than accepting parallel row arguments. Proposed hard cap is 32 MiB capture, 64 KiB envelope/request, 16 KiB per assertion; depth/node/string limits require measured fixtures and parity with reader bounds. Do not pass a large manifest through the current 1 MiB/20,000-node preflight payload validator.

Function is SECURITY DEFINER, fixed search_path=pg_catalog,pg_temp, with all tables/helpers/functions schema-qualified, including cryptographic calls. No dynamic SQL, caller-controlled identifiers, filesystem access, HTTP fetches or external language execution. Set local lock_timeout=5s and statement_timeout=30s, validate supported transaction isolation (READ COMMITTED), and use a fresh post-lock authorization statement. Bound execution/memory and reject expired assertions again after lock waiting. Return no rows or SQL diagnostics containing confidential contents on denial.

Only a vetted, pinned database-local signature verifier may run in this boundary. Select Ed25519 with fixed algorithm/version and separately managed public-key allowlists for broker and verifier; no algorithm chosen by caller, no private signing key in PostgreSQL. PostgreSQL core SHA-256 support is not an Ed25519 verifier. Selecting, packaging and reviewing the required extension/helper and strict canonical parser are OPEN IMPLEMENTATION BLOCKERS; no unsafe placeholder verification is acceptable.

Identity assertion binds issuer/audience/deployment+database instance ID, key ID, actor ID, action, request UUID, request fingerprint, nonce and issued/expiry timestamps (proposed maximum five minutes). Verifier assertion independently binds the same request/actor/fingerprint plus envelope digest and storage receipt. SQL checks purpose, algorithm, signature, audience, timing, key revocation and exact byte bindings. Reject arbitrary GUCs and actor headers. Compromise of runtime credentials cannot mint either signature. Compromise of a signing authority remains a trusted-boundary failure.

## Authorization race protocol

Fresh permission reads alone do not prevent a concurrent revocation. Forward migration must install BEFORE STATEMENT lock triggers on user, permission, content-type, direct-permission, group membership and group-permission mutation (including all affected auth group operations and TRUNCATE prohibition). Every provisioning/admin writer must acquire (73921,2) BEFORE selecting FOR UPDATE or taking relevant row locks. Trigger coverage protects ordinary DML; administrator bypass remains trusted. Review ORM admin save/delete ordering and multi-statement provisioning. No writer may start by locking auth rows then request the advisory lock.

Under READ COMMITTED, registration takes the lock, then executes fresh current active/direct/group grant checks against exact inventory/importbatch content type. SQL helper itw_review_can currently filters app_label but not model: the gateway must use the stricter query; do not rely on that helper alone. Concurrent revocation either commits before registration checks, denying it, or waits until registration commits. Attestation-key revocation, policy changes and retention collectors use the same ordering. Existing long-running transactions using older snapshots must be rejected. Coordination proof is a blocker, not an assumption about Django caches.

## Proposed forward-only inventory.0004

Do not create it at this stage. Plan dependencies on inventory.0003 and the existing auth schema. It should add immutable capture policy bindings, trusted public-key records, capture receipts (unique request UUID, actor/fingerprint/result bytes/hash/event/revision references), source claims (unique workbook SHA-256), attestation/nonce consumption records and their integrity/deferred completeness guards. Model state must match schema; operational role provisioning stays a reviewed deployment operation where migration privileges are insufficient.

It must install the capture-only function, signature/canonical validation dependencies, auth coordination triggers and explicit ACL/default-ACL changes atomically. Verify expected owners/guards first; refuse unexpected ownership or insecure dependencies. Ownership/grant transition and application credential separation must be rehearsed on a fresh disposable database AND an upgrade populated solely with synthetic data. Legacy batches remain untouched; collisions produce conflict, not adoption/backfill.

A source claim prevents additional batches for the same original workbook even under a different profile; alternate interpretation requires a future revision workflow. Profile and policy definitions remain immutable and owner-registered, unavailable from register_v1. New receipt/claim guards bind profile, actor, envelope, rows and event; no incomplete claim may commit.

Rollback is forward repair: revoke entrypoint EXECUTE and disable feature routing while preserving immutable history. Never reverse 0002/0003, delete receipts or reset source claims. No APPROVE, REVOKE, PROMOTED, review transition, snapshot creation or stock operation entrypoint is added.