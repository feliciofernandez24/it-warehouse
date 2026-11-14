# Runtime database role separation: restored-backup rehearsal

Date: 2026-11-14. Repository develop at 922e84c, initially clean. This is an additional security feasibility rehearsal, not authorization to change the persistent development database.

**Conclusion: GO for the tested runtime/owner separation mechanism. NO-GO for an unqualified deployment or operational capture rollout.** The review preflight/evidence access path and privileged administration routes require explicit decisions; all earlier secure-capture blockers remain open.

## Verified source and isolation

The required backup was found at /home/itadmin/it-warehouse-db-backups/it_warehouse_pre_review_migration_20261114_111141.dump. Its measured SHA-256 exactly matched:

2dfe16325d081973a41d246a065c631dc54560d459419d411fd820f057f97697

The older repository backup had a different hash and was not restored. Archive metadata confirms PostgreSQL 17.11, source database it_warehouse and original object owner it_warehouse. The restore showed inventory.0001 applied, inventory.0002/.0003 absent, and transactions.0001 through .0005 applied. Initial restored asset, stock-balance, movement and operation counts were all zero; tests used newly created synthetic actors/products/locations only. No restored business row values or credentials are included in evidence.

A new PostgreSQL 17.11 container, it-warehouse-runtime-separation-db, used 768 MiB tmpfs at /var/lib/postgresql/data, no persistent volume and no published ports. Only the verified dump was mounted, read-only. The new it-warehouse-runtime-separation-client shared that container's network namespace, used loopback and explicit synthetic environment values, and mounted backend source read-only. .env was never read or changed.

The persistent development database, original workbook and existing development containers were not connected to or changed. Development facts in the request were treated as supplied evidence; no live production/development inspection was performed.

## Migration and role rehearsal

A pg_dump archive does not provision cluster roles/passwords. In the disposable cluster, original table owner it_warehouse was reconstructed as a restricted NOLOGIN role, separate from both application and migration logins. A synthetic itw_rehearsal_migrator LOGIN could SET ROLE it_warehouse; Django confirmed session_user=migrator and current_user=owner during fixture/migration work.

The Django runtime itw_django_rehearsal is a real restricted LOGIN, not SET ROLE from an administrator. It owns no application tables/schema and has zero role memberships, including no direct or inherited membership in the table owner, migration login or proposed review owner.

inventory.0002 and .0003 applied successfully only in itw_runtime_rehearsal through the separate migration identity/owner context. New review objects consequently shared the correct it_warehouse owner; no existing migration was edited. A second independent restore, itw_runtime_pre, supplied the pre-review comparison without reversing migrations. Gateway comparisons were fresh clones of the migrated restored schema; the final one was itw_runtime_gateway_auth. Intermediate comparison clones stayed within the same disposable tmpfs container.

## Actual test results

| Final stage | Passed | Failed/errors | Skipped |
| --- | ---: | ---: | ---: |
| Restricted Django over pre-review restore | 12 | 0 | 0 |
| Restricted Django after inventory.0002/.0003 | 16 | 0 | 0 |
| Restricted Django plus proposed review-owner transfer | 18 | 0 | 0 |
| Final stage executions | 46 | 0 | 0 |

These are 18 distinct test methods exercised across three configurations, not 46 new independent tests. The prior 284-case result remains historical evidence and was not rerun or added to these totals. No tracked application/test/migration file changed.

Evidence includes final actual table/column grants, role flags, memberships, ownership and migration state: [before review](runtime-role-rehearsal-pre.json), [after review](runtime-role-rehearsal-post.json), [gateway comparison](runtime-role-rehearsal-gateway.json). makemigrations --check --dry-run also reported No changes detected.

Verified application behavior:

- Actual Django login, automatic upgrade of a synthetic obsolete password hash, last_login update, session INSERT/UPDATE, logout DELETE, admin index and process health.
- Bulk receive/issue/return/transfer, exact idempotent replay and conflicting-request rejection.
- Serialized receive/issue/return with custody creation and return updates.
- Explicit stock permission enforcement, including denial of an ungranted superuser.
- Audit draft/start, snapshot creation, observed count and freeze protection.

Verified database safeguards:

- Direct unbalanced quantity changes fail the existing deferred conservation guard.
- A ledger insert without a matching open operation fails the existing operation guard.
- Posted operation mutation fails the immutable operation guard.
- Existing ledger UPDATE/DELETE triggers still reject mutations even with deliberately added temporary grants. The exact required UPDATE(id) also cannot rewrite the ledger.
- Existing audit snapshot guards reject changed expected evidence.
- Runtime cannot ALTER protected tables, disable triggers, TRUNCATE protected data, change replication role, create schemas/tables/temp tables, use auth sequences or assume owner/migrator privileges.
- Runtime cannot provision users/groups/permission memberships or edit product master fields.

Initial experiments exposed missing ledger row-lock rights; UPDATE(id) solved the existing return/reversal SELECT FOR UPDATE requirement without weakening immutability. Adversarial-test cleanup also demonstrated that revoking a table UPDATE grant removes subordinate column grants; cleanup was corrected to restore the exact prior narrow grant. Initial assertions used the wrong ledger error wording and were corrected to the actual historical-record guard message and SQLSTATE. Final counts above are the successful completed runs.

## Effect of review owner-only guards

The review migrations do not prevent the tested Django authentication, session, stock or audit operations. Those continue unchanged under the explicit [grant matrix](runtime-role-grant-matrix.md). Review source/profile/revision/participant/event writes are intentionally unavailable to runtime. An accidental participant INSERT/sequence grant still fails REVIEW_SERVICE_DISABLED.

The strict role has no direct SELECT over confidential import/review tables. This exposes an actual B.1 compatibility issue: register_verified_capture's read-only preflight queries ImportReviewEvent directly and now fails closed with sanitized DATABASE_OPERATION_FAILED. Its internal preflight cannot be declared functional under this ACL design. There is currently no operational review endpoint, so this is a blocked future interface, not a broken stock service.

Do not solve that failure with broad evidence SELECT or owner membership. Implement a separately reviewed, authorization-scoped read/preflight gateway, or explicitly redesign and review the application's confidential-evidence trust boundary. Other revision preflights also use SELECT FOR UPDATE and therefore need an appropriate lock-capable trusted path.

Ordinary Django user/group administration is also deliberately excluded from this stock runtime. Admin login/index work; privileged user/group/permission editing needs a separate management service/identity or disabled routes. The shared runtime can UPDATE password because ordinary Django authentication upgrades hashes; that is a trusted authentication boundary, not a claim of independent human identity attestation.

## Proposed review gateway compatibility

In the final comparison clone only, the seven import/review tables and their identity sequences moved to a dedicated NOLOGIN review owner. The proof function had the same owner, fixed search_path and qualified relations. The runtime received only schema USAGE and exact EXECUTE for the synthetic enrollment proof, with no review-owner membership or evidence SELECT.

The actual restricted Django connection committed one synthetic CAPTURE revision/event through that function. The unchanged owner-only guards accepted it, while direct runtime review DML/evidence reads and owner assumption stayed denied. All 12 ordinary Django/stock/audit tests passed again after transfer. The review owner had no stock INSERT privilege.

This establishes compatibility with the role split; it does not authenticate a workbook or solve capture security. The reused fixture function accepts dummy source references and is explicitly unsuitable for deployment. The Phase 3B.2A prohibition on procedure ownership of application tables remains a policy conflict requiring a reviewed decision. Cryptographic packaging, canonical SQL validation, broker authentication, authority locking and production artifact retention remain blocked as previously documented.

## Required deployment configuration changes — NOT APPLIED

1. Provision a reviewed restricted application LOGIN and keep its secret separate from the schema owner and migration administrator. Never grant runtime either owner/migrator membership.
2. Configure the web process DATABASES credentials/secret references for that runtime. Do not use the database-bootstrap POSTGRES_USER/POSTGRES_PASSWORD as an implicit shared application/migration identity. The current settings read those variables; distinct service/job environments or a reviewed settings split are needed.
3. Run migrations in a separate controlled job with migration credentials and the deliberate table-owner context. Runtime startup must not migrate, create permissions, bootstrap users or install grants/functions.
4. Apply reviewed explicit object/column/sequence/function grants, database CONNECT restrictions and schema/default-ACL policy. Inventory all existing PUBLIC and inherited grants before cutover. The current phase2c-runtime-role.sql.example is too broad for confidential review: it grants ALL TABLES SELECT, broad sequences and DELETE on protected tables. It was inspected but not modified or applied.
5. Design/disable privileged Django auth-administration routes for the runtime process. Plan password/session handling, connection-pool credential separation and migration-job isolation.
6. Resolve the review read/preflight boundary and review-owner policy conflict before enabling review functionality. Do not expose the synthetic proof.
7. Rehearse the final reviewed rollout with production-like workload and independent review, then obtain separate authorization for persistent configuration/schema/ACL changes. This stage grants none.

No .env, Compose configuration, application settings, persistent role/owner/ACL, stock service/guard, existing migration, original workbook or development schema was changed. No inventory.0004, production credential, deployment script, commit or push was created. Only the two new disposable containers are stopped after evidence collection.

## Files added

- backend/feasibility_runtime/README.md
- backend/feasibility_runtime/harness.py
- backend/feasibility_runtime/run.py
- backend/feasibility_runtime/tests.py
- docs/runtime-role-separation-rehearsal.md
- docs/runtime-role-grant-matrix.md
- docs/runtime-role-rehearsal-pre.json
- docs/runtime-role-rehearsal-post.json
- docs/runtime-role-rehearsal-gateway.json

[Standalone reproduction instructions](../backend/feasibility_runtime/README.md) preserve the disposable boundary. This rehearsal is complete; persistent deployment and operational capture remain NO-GO pending the decisions above.