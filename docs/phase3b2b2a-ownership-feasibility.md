# Phase 3B.2B.2A ownership feasibility

Status: isolated feasibility verified; deployment blocked. Date: 2026-11-14. Branch develop, HEAD c834bc3. See [results](phase3b2b2a-feasibility-results.md) and [catalog evidence](phase3b2b2a-feasibility-evidence.json).

## VERIFIED

Six standalone OwnershipTests passed on disposable PostgreSQL 17.11. The harness cloned a freshly migrated synthetic database; no development connection or production role change occurred. It inspected pg_class, pg_proc, role flags, memberships and ACLs before/after explicit transfers. The seven import/review tables initially belonged to postgres, with null relacl (owner defaults). Review guard functions initially belonged to postgres, were invoker functions, and had explicit owner-only EXECUTE ACLs. Existing stock helpers generally retained default PUBLIC EXECUTE. See the evidence JSON for exact names and ACL strings.

The NOLOGIN itw_fa_owner has no superuser, CREATE ROLE, CREATE DB, INHERIT or BYPASSRLS authority. Only the seven import/review tables are transferred. Their indexes and five identity sequences follow table ownership automatically in this tested schema. The proof does not use REASSIGN OWNED or transfer stock/auth tables. Review trigger/helper functions remain owned by postgres; selected invoker helper EXECUTE grants allow the new owner to use them.

The synthetic fa_owner.enroll(bigint,uuid) function is SECURITY DEFINER, has a fixed pg_catalog,pg_temp search_path and qualified relations, and only creates revision 1 plus its CAPTURE event over preseeded SYNTHETIC-ONLY.xlsx rows. The unchanged event trigger enrolls the participant. It is deliberately not an authenticated source-registration API: its dummy row digests and caller-selected fixture references are unsuitable for real captures.

A function owner with ordinary table/sequence grants but no table ownership fails REVIEW_CAPTURE_SERVICE_DISABLED. Following ownership transfer, the same restricted LOGIN can invoke the proof and commit CAPTURED/version 1 with one event and contributor. Both an empty fresh-install path and a populated-upgrade path passed. The latter seeds a complete existing revision/event/participant history under the original owner, transfers ownership, confirms the existing revision, then captures a new synthetic fixture.

Actual runtime LOGIN tests deny owner assumption, evidence SELECT, direct DML, sequence use, TRUNCATE, trigger disablement, schema CREATE, private helper calls and stock table writes. An accidental participant INSERT/sequence grant still fails REVIEW_SERVICE_DISABLED. Rolling back a synthetic ownership ALTER restores the prior owner; revoking the entrypoint prevents new calls.

## PROPOSED

A future migration administrator could apply explicit table/function ownership and ACL changes atomically after catalog precondition checks. This requires controlled maintenance locks and a deployment identity that can manage the NOLOGIN owner. PostgreSQL ownership changes require appropriate authority and can acquire strong table locks; a live rollout needs bounded lock waits and maintenance planning. [PostgreSQL 17 ALTER TABLE documentation](https://www.postgresql.org/docs/17/sql-altertable.html).

The review owner should own only reviewed capture code and these sensitive review tables, while retaining no login or runtime membership. Runtime receives exact entrypoint EXECUTE only. Function ownership is broad authority over all its owned tables; the SQL body and every callable dependency become part of the security boundary.

## BLOCKED

This proposal conflicts with the explicit Phase 3B.2A decision that a procedure owner must not own application tables. Mechanical feasibility is not approval to supersede that policy. A reviewed architecture decision must either accept this narrowly scoped ownership model or select another design while keeping owner guards intact. Merely adding a GUC bypass or nonowner exception is unacceptable.

Compatibility findings:

- A former nonsuperuser migration/bootstrap owner with an accidental INSERT grant fails profile registration after transfer; this is tested. Future migrations/bootstrap must deliberately use the controlled new owner/administrator.
- Existing Django inventory views/admin are reserved placeholders. B.1 mutation interfaces are still disabled, so no legitimate operational capture API is broken.
- The existing Phase 2C runtime-role example grants SELECT on ALL public tables and broad sequence usage. It cannot serve as the confidential capture role unchanged; existing grants survive ownership transfer and require a reviewed ACL inventory.
- Ordinary ORM SQL needing review evidence now requires explicit authorized access. Existing stock services and guards were inspected and remain unchanged; import posting remains forbidden. The 250-case baseline passes on the original ownership model. A full restricted-runtime stock workload after transfer was NOT tested and must not be claimed certified.

pgsodium's unrelated masking DDL event hook interfered with ALTER TABLE without shared preloading. Isolated administrator sessions use its explicit enable_event_trigger=off setting to contain that hook; no inventory/Phase 2C trigger is disabled. See [signature findings](phase3b2b2a-signature-verification.md). This workaround is not a production extension deployment decision.

## NOT IMPLEMENTED

No inventory.0004, production ownership script, role provisioning, grant migration or rollback deployment exists. Operational rollback should first revoke entrypoint EXECUTE and stop routing requests, preserving immutable evidence. Restoring old ownership later requires a reviewed forward repair and permission/dependency audit; never reverse 0002/0003 or delete capture history.