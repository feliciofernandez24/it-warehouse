# Phase 3B.2D.2 role and migration deployment plan

Status: PREPARED ONLY. **Do not execute now: NO-GO.** No command in this plan has been run against persistent development. Current authorization covers disposable testing and documentation only.

## Scope and gates

Target, when separately authorized: it_warehouse on PostgreSQL 17, with inventory.0001 and transactions.0005 already applied, adding ONLY inventory.0002/.0003 and a restricted stock/session/audit runtime. No inventory.0004, prototype SQL, capture endpoint, review issuance or promotion is included.

The shared-runtime review gateway is independently blocked by trusted human authentication. Either keep every review/preflight entrypoint disabled for the narrower migration/runtime cutover or resolve that blocker and separately review its integration first. Do not treat the synthetic proof as deployable authentication.

Before scheduling: freeze an approved Git revision and images; review the pending runtime work; review exact ACLs, existing role attributes/memberships and schema ownership; prepare separate application/migration secret configuration and privileged admin-route policy; verify the recovery destination and operator responsibilities. If it_warehouse has unexpected superuser/administration attributes, stop and redesign the owner/migration split. Do not blindly grant membership in an elevated role.

## Ordered execution sequence for a later approved window

### 1. Quiesce and take a CURRENT verified backup

Stop application writers/jobs and new sessions for the maintenance window; retain the existing database/volume. Record database/version, schema owner/ACLs, migration history, protected-table counts and a role/membership/default-ACL manifest. Use protected libpq service/password files, not credentials in command arguments or logs.

The prior backup hash 2dfe16325d081973a41d246a065c631dc54560d459419d411fd820f057f97697 is evidence of the earlier restore rehearsal, not proof a future backup is current. Create a new archive and verify its own hash. Example operator command forms (service names and backup directory must be approved):

~~~sh
pg_dump --dbname='service=itw-backup-admin' --format=custom --file="$BACKUP_DIR/before-review.dump"
sha256sum "$BACKUP_DIR/before-review.dump"
pg_restore --list "$BACKUP_DIR/before-review.dump"
~~~

Capture cluster role/membership metadata separately without password hashes, and preserve the current application secret/configuration version in the secret manager. pg_dump covers one database, not global roles. [PostgreSQL 17 pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html).

### 2. Restore and validate away from persistent development

Provision a NEW disposable PostgreSQL 17 destination, no shared persistent volume, no development network/credentials. Reconstruct only reviewed owner identities, restore with --exit-on-error into the explicitly named empty validation database, preserve object owners/ACLs, compare counts/history and inspect restore errors. Do not restore over the source or use --clean against it. [PostgreSQL 17 pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).

Rehearse steps 3-7 below on that fresh restore before approving execution on persistent development. Run the existing runtime tests against synthetic additions in the isolated restore only, then verify source rows/history are preserved. This stage did not repeat a restored-data rehearsal; the earlier runtime report records that evidence, while current tests use synthetic data only.

### 3. Create separate runtime and migration identities

A trusted database administrator creates a dedicated application LOGIN with NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOINHERIT, NOBYPASSRLS, no grant option and NO owner/migration role memberships. Provision its password in the application-only secret store. Create a distinct restricted migration LOGIN with credentials available only to the maintenance job.

For the already tested owner model, migration LOGIN may SET ROLE it_warehouse under a reviewed membership; application LOGIN must not. Plan to make the old owner NOLOGIN only after the runtime cutover is proven and owner-login dependencies have been audited. Do not revoke its current access before a verified replacement exists. A role-membership audit must include inherited and SET paths, not just NOINHERIT flags.

No production role creation SQL or password is provided by the proof installer. Production names, existing-role collisions and elevated attributes require an operator-reviewed manifest.

### 4. Review ownership and establish pre-migration grants

Keep application tables under the deliberate schema owner; do NOT transfer tables to the read-function owner. Ensure the controlled migration connection reports session_user=migration login and current_user=it_warehouse before creating review objects. Check all existing import/stock tables and function owners, public schema/database defaults and identity sequences.

Apply only the reviewed explicit stock/session/audit matrix in docs/runtime-role-grant-matrix.md, with current application compatibility review. Required subtleties include auth_user.password for Django hash upgrades, UPDATE(id) for ledger row locks, UPDATE(version) for product row locks and current AuditLine.save() column behavior. Runtime DELETE is limited to sessions. No direct review SELECT, DML or review sequence grant is allowed.

Do not run the broad phase2c-runtime-role.sql.example unchanged. Audit and remove unintended PUBLIC/inherited grants through reviewed explicit objects. Restrict database CONNECT/TEMP and schema CREATE without breaking unrelated approved clients. Establish the correct owner's future default privileges and inspect new objects after migration; never grant broad defaults as a shortcut.

### 5. Apply ONLY existing review migrations as the migration identity

Use a separate controlled maintenance container/job, read-only approved source, explicit target database, migration-only secret and deliberate owner context. Never source the web runtime's shared .env for migrations. First confirm the plan:

~~~sh
python manage.py showmigrations inventory transactions
python manage.py migrate inventory 0003 --plan
python manage.py migrate inventory 0003 --noinput
python manage.py showmigrations inventory transactions
~~~

These are command forms for the approved migration-job environment, not commands executed here against development. PGOPTIONS=-crole=it_warehouse was tested with a distinct migration LOGIN in the prior rehearsal. Verify that the approved target plan applies 0002 then 0003 and nothing unexpected. inventory.0002 is explicitly forward-only; 0003 has no reverse SQL. Do not fake, reverse, edit historical migrations or add 0004.

Inspect resulting seven import/review table owners, guard definitions, constraints, function EXECUTE ACLs and default grants. Verify their owner consistency with the migration context; ensure runtime gained no new evidence rights. Do not install feasibility_review_read/gateway.sql, its principal tables or synthetic LOGINs.

### 6. Transition ONLY application credentials

Compose currently gives backend env_file: .env while the database bootstrap also reads POSTGRES_USER/PASSWORD; base.py consumes those same names. Prepare a reviewed service-specific environment/secret overlay so backend receives restricted application credentials and the migration job receives separate credentials. Keep database bootstrap variables independent. Do not globally replace POSTGRES_USER in .env and assume all services should share the new account.

Ensure no owner/migration password or role option reaches web containers, workers, connection pools or logs. Restart application connections under the new LOGIN; verify session_user=current_user=runtime and absence of all owner/migrator memberships. Do not automatically SET ROLE to an owner. Backend currently starts runserver, not migrate; retain the separation rather than adding migrations at startup.

Disable or separately route privileged auth user/group administration and any unready review/preflight jobs. Admin login/index are supported by the tested runtime; arbitrary user/group editing is not. Read-gateway integration is disabled until independently authenticated and reviewed. Do not introduce the proof's isolated identity flag into application requests.

### 7. Startup, smoke tests and migration-history verification

Run read-only live readiness checks under the actual new application connection: current database/user, expected table/column/function ACLs, schema owners, no owner/migrator memberships and expected migration history. /api/health/ is process liveness only and cannot certify database readiness.

Exercise authorized authentication/session flows with an approved test account and audit any expected login writes. Perform stock mutation/guard regression tests on the isolated restored twin, never destructive negative probes on live data. Do not execute TRUNCATE, ALTER/DISABLE TRIGGER or stock-ledger corruption attempts against persistent development merely to prove they fail; use catalog checks there.

Verify inventory.0002/.0003 and transactions.0005 entries, fresh relevant schema/guard catalog state, application health and sanitized denial of all unavailable review/capture paths. Confirm no startup code is installing proof SQL or provisioning permissions. Only after successful smoke checks should writers resume.

Retire the old owner LOGIN/credential from application access through a separately reviewed final step, preserving controlled migration SET ROLE access and offline recovery. Update the deployment record with exact source/image/backup hashes, migration run, ACL manifest and secret versions.

## Reversible configuration versus forward-only schema

| Change | Recovery class |
| --- | --- |
| Backend environment/secret reference and process routing | Reversible through controlled configuration rollout and connection restart |
| New runtime LOGIN/grants | Can be disabled/revoked by an administrator; do not grant owner authority during recovery |
| Owner NOLOGIN retirement | Reversible administratively, but owner credentials must never become the routine web fallback |
| inventory.0002/.0003 committed DDL/history | Forward-only; use a reviewed repair or full verified restore, never migration unapply/fake |
| New application writes after cutover | Cannot be discarded safely by reverting an environment variable; preserve and reconcile evidence |

## Controlled failure recovery

Before migration commit: keep writers stopped, inspect transaction/migration history from the maintenance identity and correct the cause in the isolated twin first. Never infer complete rollback from a disconnected client alone. Check applied history and catalog state before retrying.

After committed schema migration: stop routing/writers, retain the migrated database and its logs for analysis. Prefer a reviewed forward repair; an older application build may tolerate additive schema only if verified on the twin. Do not attempt to unapply 0002/0003.

If full restore is necessary, restore the verified pre-window archive to a NEW recovery database/volume, reconstruct reviewed roles/ACLs, validate data/history and switch application configuration only after verification. Preserve the failed target; never wipe/reuse the named persistent volume as an automatic rollback. If post-cutover writes occurred, preserve them and obtain a reconciliation plan before choosing a restore, since the backup predates them.

Configuration rollback must not silently reconnect the web process as table owner. Keep the application offline if a safe restricted configuration cannot be restored. Revoke any mistakenly exposed entrypoint EXECUTE first while preserving immutable history. Record every recovery action.

## Current decision

All steps above are conditional preparation only. No persistent backup, restore, role, ACL, ownership, credential or migration operation was executed in this phase. Required configuration artifacts, administration routing and independent identity integration are not implemented. Overall deployment remains **NO-GO**; see [readiness](phase3b2d2-readiness-decision.md).