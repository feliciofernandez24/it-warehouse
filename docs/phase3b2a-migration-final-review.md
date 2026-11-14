# Phase 3B.2A migration final review

Date: 2026-11-14, Asia/Tokyo. Corrections apply only to uncommitted, undeployed inventory.0002 and inventory.0003. Earlier Phase 2B/2C migrations and posting guards are unchanged.

## Schema decision and model consistency

The additional schema was proposed before implementation. ImportSourceProfile stores a versioned immutable definition. ImportPreparationRevision has a required PROTECT source_profile FK. Every successor must inherit it. ImportBatch needs no extra column; its immutable revision lineage binds the registered source to a fixed definition.

0002 was regenerated from the original inventory.0001/current transactions.0005 graph, preserving all prior Stage A fields, constraints and permission declarations. It now creates five sensitive tables, with no default CRUD permissions. The ten new profile constraints bring the named model constraints to 37, in addition to field/PK/FK/unique indexes. Django makemigrations --check --dry-run reports no drift.

The swappable user dependency and transactions.0005 dependency are retained. No historical migration, extra migration number, destructive reverse migration or profile data seed was introduced.

## Generated SQL review

| Property | 0002 | 0003 |
| --- | ---: | ---: |
| Tables created | 5 | 0 |
| Functions created | 0 | 11 |
| Triggers created | 0 | 18 |
| Initially deferred constraint triggers | 0 | 4 |
| PUBLIC EXECUTE revocations | 0 | 11 |
| SECURITY DEFINER | 0 | 0 |
| DROP TABLE / TRUNCATE / destructive DELETE DML | 0 | 0 |

0003 has seven statement lock triggers, seven row guards and four deferred integrity triggers. The two new private functions are itw_review_profile_guard() and itw_review_check_profile(bigint,uuid,text). No workbook-specific hash or 15/920/897/21/2 branch remains in production SQL.

All functions are invoker-rights, public-qualified where relevant, fixed search_path=pg_catalog,public,pg_temp, with no dynamic SQL. SQL owner on the disposable deployment is postgres; no production or development ownership/grants were configured. Catalog checks confirmed 11 private non-definer functions and no PUBLIC execution.

Both migrations set transaction-local lock_timeout=5s and statement_timeout=30s. These bound migration execution only, not future application requests. Generated SQL remains transactional; newly created callable functions and ACL revocations become visible together at commit.

## Integrity and write gates

New profile INSERT validates exact byte SHA-256, supported JSON definition, exact typed count keys, count reconciliation and database role/timestamp metadata. Only table owner can bootstrap definitions for controlled tests. UPDATE/DELETE is always rejected, including for pending definitions.

Revision insertion and deferred final checks require a verified definition, workbook/layout agreement and exact observed row counts for every profile. Revision/profile identities, registered source rows and lineage are immutable; snapshots also bind profile digest. Definition attestation does not establish uploaded file authenticity.

Nonowner profile/capture registration and review-table mutation are explicitly denied, even with accidentally granted DML. No gateway or runtime writer grant was created. Owners remain privileged and can alter DDL; they are not application principals.

Snapshot entry-type validation now prevents text row-number coercion and requires typed identity/digest fields. EXCLUDED scope and EXCLUDED_WITH_REASON agree in both directions; reason is nonblank text. Existing exact coverage and duplicate checks remain in force.

Deferred state/event/version/participant checks, one active revision, immutable snapshots/history, independent reviewer checks and hard-disabled approval/promotion remain intact. PostgreSQL JSONB equality is not advertised as canonical-byte proof.

## Locking and concurrency

All source/profile/review mutations use pg_advisory_xact_lock(73921,2) before row mutation. Revision guard then locks ImportBatch before allocating lineage. No new lock namespace, stock call, asset/balance lock, broad auth trigger or master trigger was added.

New tests observe a real ungranted advisory-lock request in pg_locks, then release the first transaction. Registration first causes later source changes to fail. A profile-relevant source classification change first causes registration to revalidate and fail counts. Concurrent state/event updates reject a stale version. Existing concurrent initial registration still commits exactly one revision.

These are structural source/locking guarantees. Raw file authenticity and a stale raw-value digest cannot be proved by count reconciliation; runtime capture remains disabled until a trusted authenticated service reparses the immutable source.

Lock-first ordering must be maintained in future services/admin/provisioning. Arbitrary manual row locks before the global lock can deadlock. Use bounded request timeouts and whole-transaction retry; do not recover inside a failed atomic block. Permission/master races are not solved or claimed here.

## Forward-only safety and isolation

0002 unapply always raises IrreversibleError. 0003 has no reverse SQL. Do not add DROP/reverse operations to satisfy historical tests. Those 45 cases use the separate historical registry exposing only original inventory.0001; the additional profile model is excluded there along with the earlier four review models.

The complete pre-apply migration plan and sqlmigrate output were reviewed. Fresh disposable PostgreSQL successfully applied all final migrations; post-apply plan has no operations. Fresh Django test databases applied the final SQL from scratch too.

Read-only rehearsal checks: profiles, revisions, snapshots, events, assets, balances, movements and operations all zero. No real definitions or source rows were seeded. No development connection/migration, PostgreSQL volume reset, stock DML, signing key or production grant was performed.

Before deployment: review schema/gates, migration SQL/timeouts, nonowner runtime credentials, authenticated gateway design, source/evidence retention and trust decisions. Applying these migrations to development still requires separate review/authorization.
