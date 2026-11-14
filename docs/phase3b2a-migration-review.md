# Phase 3B.2A migration and SQL review

## IMPLEMENTED migration graph

inventory.0002_import_review_schema depends on inventory.0001, transactions.0005_serialized_reclassification and the swappable auth dependency. inventory.0003_import_review_guards depends on inventory.0002. No historical migration was edited.

0002 creates four tables and declarative constraints/indexes. AlterModelOptions changes Django permission metadata only; normal post_migrate creates permission rows in the disposable database. It grants no user/group membership. A guarded unapply method always raises IrreversibleError before table operations can reverse.

0003 is a RunSQL operation with no reverse_sql. It is intentionally irreversible. Recovery after successful deployment requires a reviewed forward repair; no destructive reverse migration is provided to satisfy legacy tests.

## Generated SQL ? TESTED / REVIEWED

| Item | 0002 | 0003 |
| --- | ---: | ---: |
| CREATE TABLE | 4 | 0 |
| CREATE FUNCTION | 0 | 9 |
| CREATE TRIGGER, including constraint triggers | 0 | 16 |
| Deferred, initially deferred constraint triggers | 0 | 4 |
| REVOKE EXECUTE FROM PUBLIC | 0 | 9 |
| SECURITY DEFINER | 0 | 0 |
| DROP TABLE / TRUNCATE / DELETE FROM data DML | 0 | 0 |

No stock DML occurs. The only integrity-helper INSERT is contributor enrollment in the new participant table. This does not grant a permission or user membership.

Functions: itw_review_lock, itw_review_can, itw_review_revision_guard, itw_review_source_guard, itw_review_participant_guard, itw_review_snapshot_guard, itw_review_event_guard, itw_review_assert and itw_review_final_guard.

All functions use invoker rights and fixed search_path=pg_catalog,public,pg_temp; table/function references are public-qualified and no dynamic SQL is used. Byte hashing uses PostgreSQL 17 built-in sha256, not an extension.

There are six statement-level lock triggers: four new tables plus ImportBatch and ImportStagingRecord. Six row guards cover those same tables. Four deferred constraint triggers cover revision/participant/snapshot/event changes. Source changes are blocked immediately once registered; row deletion also retains prior Phase 2B history guards.

## Ownership and grants ? IMPLEMENTED limits

On the disposable database, functions/tables are owned by its migration owner (postgres). This is a test owner, not a deployed application role. Catalog tests verify invoker flags, fixed paths, nine PUBLIC EXECUTE revocations and four deferred triggers.

No SECURITY DEFINER procedure, production role, runtime grant, signing key, auth coordination trigger or master coordination trigger was installed. A new restricted role in rollback-only tests cannot UPDATE/TRUNCATE/disable triggers, change session_replication_role or directly call the private helper. No superuser/BYPASSRLS/schema-owner rights were given to an application runtime role.

These migrations alone do not deploy a usable review writer role. A future review runtime would require reviewed table/function permissions or narrowly scoped definer procedures with separate nonlogin ownership and authenticated service trust. Do not grant broadly just to make ORM writes work. PUBLIC revocation means nested helper execution also needs explicit reviewed rights for any nonowner writer.

## Lock order and operational effects

Before any row mutation on a new review table or source envelope/row table, a statement trigger acquires pg_advisory_xact_lock(73921,2), the existing Phase 2C engine lock. Revision guard then locks ImportBatch, validates lineage and lets the row mutation proceed. Deferred checks compare final event/version/payload/source/contributor evidence.

No review function calls stock posting or locks assets/balances. No auth/master coordination was attempted. Existing Phase 2C statement/row guards remain byte-identical.

The shared lock serializes source/review writes with supported inventory writers. New registration can therefore briefly delay posting, and source-note writes participate in the same order. Use bounded lock/statement timeouts operationally. A caller that manually locks a batch/revision before obtaining the advisory lock can introduce deadlock; future service/provisioning paths must lock advisory first. Retry a whole failed transaction, not a statement inside a broken atomic block.

Actor checks query active users and explicit inventory grants. Because auth writers do not share this protocol yet, those checks are not a race-safe approval authorization guarantee. Approval is hard-disabled for that reason and others.

## Snapshot and event evidence

Snapshot bytes are verified with encode(sha256(bytes),'hex'), parsed as UTF-8 JSON and compared semantically to the frozen draft. Source-row identities/digests and classifications must exactly cover the registered rows without duplication; candidate decisions must exactly cover registered candidates. This is structural verification only.

Event details.after_payload_digest is an internal PostgreSQL SHA-256 over draft_payload::text. It binds each event to its actual database draft, but is not the canonical preview digest: PostgreSQL jsonb::text must never be presented as Python canonical bytes. The future approval request fingerprint/canonicalization contract is deferred.

State/version mutations cannot commit without matching event evidence. Initial CAPTURE version/sequence is exactly 1, from CAPTURED to CAPTURED; later versions advance by one. Participants and events are append-only. No trigger can issue APPROVE or make APPROVED reachable.

Registered source rows are completely frozen. Batch id/public_id, filename/hash/storage key, uploader/time, mapping version/timezone, status/reviewer/digest and creation identity are frozen. Non-source notes and routine update metadata remain editable, preserving existing behavior outside source integrity.

## Validation and safety

Generated sqlmigrate output was inspected before/after the final guard narrowing. Fresh disposable databases successfully applied all migrations through inventory.0003. Django test databases recreated the final SQL from scratch. Migration plan reported no pending operations after apply, drift check found no changes, and system checks passed.

The separate historical registry exposes only unchanged inventory.0001, so original tests never unapply new irreversible schema. No application or deployment setting uses this historical registry.

Development migration is NOT AUTHORIZED or executed. Do not run compose migrate on the existing database. Review this SQL, source-adoption policy and role/trust decisions before any later deployment.
