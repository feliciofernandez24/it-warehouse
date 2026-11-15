# Phase 3B.2D.3 final development schema deployment decision

Date: 2026-11-16 (Asia/Tokyo). Repository: /home/itadmin/projects/it-warehouse. Branch: develop. Verified HEAD: 7bb8e09. The worktree was clean at entry. **No persistent development connection or deployment was made.**

## Four independent recommendations

| Decision | Recommendation | Evidence and remaining gates |
| --- | --- | --- |
| Schema-only development migration: inventory.0002 then inventory.0003 | **GO for a controlled maintenance installation only** | Verified backup restored twice; migrations succeeded under the separate migration LOGIN in the original owner context; all original rows survived; catalogs, disabled workflows and owner-context application smoke tests passed. Requires a fresh pre-window backup/restore, matching preflight, application/writer isolation and explicit acceptance of temporary shared-owner development risk. This is not approval to activate review/capture or a claim of runtime isolation |
| Restricted runtime-role activation | **NO-GO for immediate activation** | All 16 restricted-runtime methods pass on the migrated restore. The service-specific secret/environment split, privileged auth administration routing, final role/default-ACL manifest and controlled cutover configuration remain unimplemented/unapproved. The broad existing SQL example is not suitable |
| Operational review gateway | **NO-GO** | The 20 metadata-read proof tests pass, but per-user synthetic database principals do not independently authenticate humans behind the shared Django LOGIN. Trusted identity verification, scope administration, full authority-writer coordination and application integration remain absent |
| Secure inventory capture | **NO-GO** | No operational capture endpoint or write gateway exists. Independent uploader/verifier authentication, complete SQL canonical/byte binding, vetted signature packaging, artifact retention/recovery integration and the writable-owner policy decision remain unresolved |

This is a narrower conclusion than D.2's combined rollout NO-GO: **additive, inactive schema installation can be separated from runtime-role activation and operational review.** The schema GO does not authorize this agent to execute deployment. If policy requires nonowner isolation before any web traffic resumes, keep the application stopped until the runtime transition is approved; do not describe owner-based operation as secured by these guards.

## Evidence inspected and verified baseline

Inspected the runtime-role rehearsal/grant matrix and test code; D.2 architecture, deployment, validation, readiness and ACL evidence; B.1 review services/authorization/read-only SQL proof; source-profile/owner feasibility and capture blockers; current Django/Compose settings, URLs and inventory admin/views; inventory.0002/.0003; Phase 2C service and guard definitions. No separately named Phase 3B.2D.1 report exists in this checkout; its runtime-role evidence is in the runtime-role-* reports. Those and all prior tests remain unchanged.

The two immutable migration files hash to:

| File | SHA-256 |
| --- | --- |
| backend/apps/inventory/migrations/0002_import_review_schema.py | 0a9028ef00485e0048cbb21b9e8011a707cbd2380a404a6ca7974f141a06133c |
| backend/apps/inventory/migrations/0003_import_review_guards.py | 58fff9f1844291019ef8f55497b547d7d19968b440dcd273c414b96f4fa5e879 |

0002 depends on inventory.0001, the user model and transactions.0005. It adds five review models, their constraints/indexes/FKs and permission declarations; it seeds no operational source profile. 0003 installs 11 invoker integrity functions and 18 review triggers across the five new and two existing import tables. Neither migration installs a SECURITY DEFINER operational gateway, HTTP endpoint, artifact importer or stock posting workflow.

## Restore and source-preservation proof

The supplied archive was read-only mounted from:

/home/itadmin/it-warehouse-db-backups/it_warehouse_pre_review_migration_20261114_111141.dump

Its freshly measured SHA-256 is exactly:

2dfe16325d081973a41d246a065c631dc54560d459419d411fd820f057f97697

Archive metadata: source it_warehouse, PostgreSQL/pg_dump 17.11, custom format, archive timestamp 2026-11-14 02:11:41 UTC. This is a verified historical backup, not a claim that it represents all development changes on November 16.

New containers it-warehouse-phase3b2d3-db and it-warehouse-phase3b2d3-client used PostgreSQL 17.11, 768 MiB tmpfs data, no persistent database volume and no published database port. The client shared only that container's network namespace and read-only backend source. All connection values were explicit synthetic values; .env was not read.

The archive restored successfully using pg_restore --exit-on-error --single-transaction. Owner it_warehouse was reconstructed as an ordinary nonsuperuser LOGIN with a synthetic password. A separate restricted migration LOGIN could SET ROLE it_warehouse; runtime credentials were not changed in development.

Preflight confirmed inventory.0001 only and transactions.0001 through .0005. There were 29 original public tables and 165 rows:

| Original table group | Rows before | Rows immediately after migration |
| --- | ---: | ---: |
| auth_permission | 113 | 118 |
| django_content_type | 25 | 30 |
| django_migrations | 27 | 29 |
| Other 26 original tables, including all inventory/transactions/audits/auth-user/session data | 0 | 0 |

All 165 ORIGINAL rows were compared by primary key and SHA-256 of PostgreSQL JSONB row serialization. They remained byte-representation equivalent in the same server/timezone. All original tables other than the three expected metadata tables matched exactly, including counts. Only five permissions, five content types and two migration records were added by migration/post_migrate.

An independent empty recovery database, itw_recovery_check, was then restored from the same archive after the migration rehearsal. It reproduced all 29 pre-migration table counts/hashes and inventory.0001-only history. SHA-256 of the sorted original table-count/hash manifest:

60e977235565590cae0dddbf0252a8d7e984d1b4a90038452d8e27b6c480127b

The restore copy proves this archive is usable. Roles/passwords are cluster state and are not supplied by this single-database dump; recovery reconstructed only synthetic owner identities, never production credentials.

## Postmigration validation

Immediately after migration all five new tables were empty:

- inventory_importsourceprofile
- inventory_importpreparationrevision
- inventory_importrevisionparticipant
- inventory_importpreviewsnapshot
- inventory_importreviewevent

All declared model constraints and valid indexes were found. PostgreSQL reported 63 constraint records across these tables, all validated: 35 CHECK, 12 FK, 5 primary-key, 7 ordinary unique and 4 deferred trigger constraints. Two conditional uniqueness rules are valid partial indexes rather than ordinary pg_constraint rows.

All 11 review functions were invoker functions owned by it_warehouse. All 18 review triggers were enabled; four final-state constraint triggers were DEFERRABLE INITIALLY DEFERRED. New-table ownership was consistent with the original owner context. No itw_read_poc/fa_owner/capture gateway schema was installed in the restored migration target.

Existing Phase 2C function-definition hashes and non-review trigger definitions/enabled states matched before and after migration and after smoke tests. This comparison is distinct from source-file/Git checks.

A valid owner-context call to the reserved register_verified_capture interface still raises GATEWAY_UNAVAILABLE without creating source/review records. APPROVE/REVOKE/promotion interfaces raise ACTION_DISABLED. Owner-context SQL attempts to set APPROVED/REVOKED/PROMOTED revision states or issue APPROVE/REVOKE review events fail REVIEW_APPROVAL_DISABLED. The fixture metadata used to test those denials was synthetic and rolled back.

Current URLs remain admin/ and api/health/; inventory views/admin are reserved placeholders. No operational capture/review route was activated. Merely declaring permissions, tables and state names does not enable issuance or posting.

## Security regression results

| Final suite/configuration | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
| Current existing Django regression | 205 | 0 | 0 | 0 |
| Historical isolated registry | 45 | 0 | 0 | 0 |
| New restored-schema/catalog/disabled-workflow tests | 8 | 0 | 0 | 0 |
| Existing application/stock/audit smoke subset under actual OWNER LOGIN | 8 | 0 | 0 | 0 |
| Existing restricted-runtime tests on migrated restore | 16 | 0 | 0 | 0 |
| Existing metadata-read gateway proof on separate synthetic database | 20 | 0 | 0 | 0 |

The eight owner-context smokes reuse eight methods also exercised in the 16-method restricted suite; they demonstrate a different credential context and must not be counted twice as new unique methods. No aggregate unique-baseline total is claimed. The historical 34 capture-feasibility cases and two prior writable-owner compatibility methods were not rerun and are not counted as skipped/passed here. Existing files/results were preserved.

The owner smokes cover Django login, automatic password-hash upgrade, last_login, session creation/update/logout, admin index/health; bulk and serialized receive/issue/return/transfer; idempotent replay/conflict; ungranted-superuser denial; conservation, open-operation and committed-operation guards; audit count/freeze behavior. Stock test writes used synthetic additions and rolled back. Original rows were rechecked after smokes and remained unchanged.

Restricted-runtime tests confirm no owner/migrator membership, no direct review SELECT/DML, denied protected ALTER/TRUNCATE/trigger control and no implicit superuser capability. Their B.1 preflight still fails closed under no-evidence SELECT grants. The separate read-proof suite confirms scoped diagnostics but shared-identity denial. Neither proof is installed in the restored target.

makemigrations --check --dry-run reported No changes detected. The new reproducible test is [backend/feasibility_schema/run.py](../backend/feasibility_schema/run.py). Detailed transient evidence was generated at /tmp/phase3b2d3-schema-evidence.json in the disposable client; this report preserves its decisions, counts, manifest and catalog results before cleanup.

## Role policy and temporary shared-owner operation

**Django using it_warehouse is NOT a restricted runtime.** The existing owner-only comparisons accept that current_user. A table owner can alter owned tables and control user triggers; a superuser can do still more. Real development role flags were not queried during this task. The disposable role was intentionally only an ordinary owner, sufficient to demonstrate the problem.

A rolled-back disposable probe successfully added a temporary review-table column and disabled USER triggers on the ledger table. It also confirmed owner TRUNCATE privilege. No ledger data was modified while triggers were disabled; all probe DDL rolled back, and guard definitions/enabled states were revalidated afterward. No such probe ran against persistent development.

With guards left intact, Phase 2C conservation, immutable history, operation matching and explicit application capability checks still run under the owner. They protect against many accidental/invalid writes, not against an owner credential deliberately modifying DDL, disabling guards or fabricating SQL identities. Review owner-only gates are controlled-bootstrap boundaries, not independent authentication or isolation from this shared owner.

Therefore:

- Schema installation can proceed offline without changing credentials or activating any workflow. It does not need the operational read/capture gateway.
- Resuming unchanged owner-based development service is an explicit continuation of the existing trusted-development model, with new empty schema. It is not a security upgrade or acceptable production role model.
- If temporary owner operation is allowed, record who accepts the risk, its review deadline, local access restrictions and the separate runtime-transition work. Do not store actual workbook evidence or exercise review/capture in that interval.
- If nonowner isolation is mandatory immediately, do not resume application traffic; await the restricted-role configuration decision.
- Restricted activation remains separate: dedicated runtime LOGIN, no owner/migrator membership, exact table/column/sequence/function grants, separate migration credentials, no owner secrets in web containers, and approved handling of privileged Django user/group administration.
- Do not apply database/phase2c-runtime-role.sql.example unchanged: its broad SELECT/sequence/DELETE grants are incompatible with confidential review evidence.

This report does not convert the D.2 synthetic read-identity mapping into a human authentication service. Operational review/capture remain disabled regardless of owner or restricted credential.

## Exact FUTURE commands: controlled schema-only installation

**The following persistent-target commands were NOT executed.** Run only after separate deployment authorization, a declared maintenance window and the gates below. The commands deliberately retain existing credentials/ownership for this narrow installation; they do not activate a runtime role or gateway.

### A. Pin source and inspect the exact target

~~~sh
set -euo pipefail
cd /home/itadmin/projects/it-warehouse
test "$(git branch --show-current)" = develop
test "$(git rev-parse --short=7 HEAD)" = 7bb8e09
git diff --exit-code
git diff --cached --exit-code
test "$(sha256sum backend/apps/inventory/migrations/0002_import_review_schema.py | cut -d ' ' -f1)" = 0a9028ef00485e0048cbb21b9e8011a707cbd2380a404a6ca7974f141a06133c
test "$(sha256sum backend/apps/inventory/migrations/0003_import_review_guards.py | cut -d ' ' -f1)" = 58fff9f1844291019ef8f55497b547d7d19968b440dcd273c414b96f4fa5e879
docker inspect it-warehouse-db-1 --format '{{range .Mounts}}{{println .Type .Name .Destination}}{{end}}'
docker exec it-warehouse-db-1 psql -X -v ON_ERROR_STOP=1 -U it_warehouse -d it_warehouse -c "SELECT current_database(),session_user,current_user,current_setting('server_version_num'); SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=current_user; SELECT app,name FROM django_migrations WHERE app IN ('inventory','transactions') ORDER BY app,name;"
~~~

Require the named volume it-warehouse_postgres_data at /var/lib/postgresql/data, PostgreSQL 17.11, database/user it_warehouse, inventory.0001 only and transactions through .0005. Resolve any unreviewed untracked files or source/image drift. If a later approved commit supersedes this baseline, re-review and update the pin rather than bypassing it. Record any superuser/administrative flags as additional residual risk; this report did not verify live role attributes.

### B. Stop all writers and take a fresh private backup

~~~sh
docker compose stop frontend backend
docker exec it-warehouse-db-1 psql -X -v ON_ERROR_STOP=1 -U it_warehouse -d it_warehouse -c "SELECT pid,usename,application_name,state,backend_type FROM pg_stat_activity WHERE datname=current_database();"
umask 077
backup_dir=/home/itadmin/it-warehouse-db-backups
mkdir -p "$backup_dir"
backup_path="$backup_dir/it_warehouse_before_phase3b2d3_$(date -u +%Y%m%dT%H%M%SZ).dump"
test ! -e "$backup_path"
docker exec it-warehouse-db-1 pg_dump -U it_warehouse -d it_warehouse -Fc > "$backup_path"
sha256sum "$backup_path"
~~~

Stop/coordinate any non-Compose workers, scripts and external writers too; do not assume two service stops isolate every client. Cancel if active writers cannot be identified/quiesced. Preserve the current volume, image IDs, credential/configuration references, owners, role/membership/default-ACL manifest and predeployment source counts/hashes. Do not print secrets or use docker compose config output as a secret manifest.

### C. Restore the FRESH archive to a NEW disposable target and rerun evidence

These are only disposable credentials. Do not reuse any original owner password. Names below must be unused. No existing database/volume is overwritten.

~~~sh
docker run -d --name it-warehouse-predeploy-restore-db --network bridge \
  --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=768m \
  --mount "type=bind,source=$backup_path,target=/verified-backup.dump,readonly" \
  -e POSTGRES_PASSWORD=runtime-rehearsal-admin-only -e POSTGRES_DB=itw_runtime_rehearsal postgres:17-alpine
restore_ready=0
for restore_attempt in $(seq 1 60); do
  if docker exec it-warehouse-predeploy-restore-db pg_isready -U postgres -d itw_runtime_rehearsal; then restore_ready=1; break; fi
  sleep 1
done
test "$restore_ready" = 1
docker exec it-warehouse-predeploy-restore-db psql -X -v ON_ERROR_STOP=1 -U postgres -d itw_runtime_rehearsal -c "CREATE ROLE it_warehouse LOGIN PASSWORD 'owner-rehearsal-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; CREATE ROLE itw_rehearsal_migrator LOGIN PASSWORD 'migration-rehearsal-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; GRANT it_warehouse TO itw_rehearsal_migrator; ALTER DATABASE itw_runtime_rehearsal OWNER TO it_warehouse;"
docker exec it-warehouse-predeploy-restore-db pg_restore --list /verified-backup.dump
docker exec it-warehouse-predeploy-restore-db pg_restore --exit-on-error --single-transaction -U postgres -d itw_runtime_rehearsal /verified-backup.dump
docker run --rm --network container:it-warehouse-predeploy-restore-db \
  --mount type=bind,source=/home/itadmin/projects/it-warehouse/backend,target=/app,readonly \
  -e PYTHONDONTWRITEBYTECODE=1 -e DJANGO_SECRET_KEY=predeploy-disposable-only \
  -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_DB=itw_runtime_rehearsal \
  -e POSTGRES_USER=it_warehouse -e POSTGRES_PASSWORD=owner-rehearsal-only \
  -e ITW_SCHEMA_REHEARSAL=1 it-warehouse-backend python feasibility_schema/run.py
~~~

The test requires exactly PostgreSQL 17.11 and stops on changed migration history, source changes or catalog/test failures. A restore/fixture failure or materially different source population requires review, not forced continuation. Bound readiness waiting operationally; cancel rather than leaving maintenance open indefinitely. Keep this verification database until evidence/recovery checks are accepted.

### D. Preview then apply only the two migrations, while application remains stopped

~~~sh
docker compose run --rm -T --no-deps backend python manage.py showmigrations inventory transactions
docker compose run --rm -T --no-deps backend python manage.py migrate inventory 0003 --plan
docker compose run --rm -T --no-deps backend python manage.py migrate inventory 0002 --noinput
docker compose run --rm -T --no-deps backend python manage.py migrate inventory 0003 --noinput
docker compose run --rm -T --no-deps backend python manage.py showmigrations inventory transactions
docker compose run --rm -T --no-deps backend python manage.py makemigrations --check --dry-run
~~~

The existing service-specific environment must resolve to the verified target and current owner; verify that before execution. Use these one-off maintenance commands, not runserver startup. Do not create/grant runtime roles, copy prototype SQL, seed profiles, fake migrations, add 0004 or enable review paths.

Each migration is atomic separately, NOT one all-or-nothing transaction spanning both. If 0002 commits and 0003 fails, 0002 remains applied. Keep the application stopped; inspect catalog/history and repair or restore before any restart.

### E. Verify catalogs and original data before restart

~~~sh
docker exec it-warehouse-db-1 psql -X -v ON_ERROR_STOP=1 -U it_warehouse -d it_warehouse -c "SELECT app,name FROM django_migrations WHERE app IN ('inventory','transactions') ORDER BY app,name; SELECT relname,pg_get_userbyid(relowner) FROM pg_class WHERE relnamespace='public'::regnamespace AND relname LIKE 'inventory_import%' AND relkind IN ('r','S') ORDER BY relname;"
docker exec it-warehouse-db-1 psql -X -v ON_ERROR_STOP=1 -U it_warehouse -d it_warehouse -c "SELECT proname,pg_get_userbyid(proowner),prosecdef,proacl FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname LIKE 'itw_review_%' ORDER BY proname; SELECT c.relname,t.tgname,t.tgenabled,t.tgdeferrable,t.tginitdeferred FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid WHERE t.tgname LIKE 'review_%' ORDER BY c.relname,t.tgname;"
docker exec it-warehouse-db-1 psql -X -v ON_ERROR_STOP=1 -U it_warehouse -d it_warehouse -c "SELECT 'profile',count(*) FROM inventory_importsourceprofile UNION ALL SELECT 'revision',count(*) FROM inventory_importpreparationrevision UNION ALL SELECT 'participant',count(*) FROM inventory_importrevisionparticipant UNION ALL SELECT 'snapshot',count(*) FROM inventory_importpreviewsnapshot UNION ALL SELECT 'event',count(*) FROM inventory_importreviewevent; SELECT count(*),count(*) FILTER (WHERE NOT convalidated) FROM pg_constraint WHERE conrelid IN ('inventory_importsourceprofile'::regclass,'inventory_importpreparationrevision'::regclass,'inventory_importrevisionparticipant'::regclass,'inventory_importpreviewsnapshot'::regclass,'inventory_importreviewevent'::regclass);"
~~~

Require five empty tables, 63 validated constraint records, 11 invoker review functions with intended owner-only EXECUTE ACLs, 18 enabled review triggers/four deferred final checks and correct owner consistency. Compare pre/post ORIGINAL-row hashes and stock guard definitions against the fresh verified restore using the same fingerprint method in the test script. Accept only the expected metadata additions. Do not test live permissions by attempting destructive TRUNCATE or guard disabling.

Only after all checks and explicit acceptance of continued temporary owner operation:

~~~sh
docker compose up -d --no-deps backend frontend
curl --fail http://127.0.0.1:8000/api/health/
~~~

Health is liveness only. Verify authorized login/session behavior and current database identity through the application; confirm all review/capture paths remain unavailable. Perform stock mutations/negative guard probes only on the disposable twin. If owner-based service is not acceptable, omit the restart and retain maintenance isolation.

## Restricted runtime transition: separate gated work

No runtime activation command is authorized or represented as ready by this schema GO. Before activation, prepare/review an application-only LOGIN/secret and a distinct migration identity; no runtime membership in owner/migration roles; explicit grants per [matrix](runtime-role-grant-matrix.md); service-specific Compose/environment/secret configuration; supported admin-route policy; connection-pool restart and effective-identity/ACL smoke tests.

Current Compose shares .env with backend, and base.py reads POSTGRES_USER/PASSWORD also used for database bootstrap. Do not globally change those variables and accidentally change every service's identity. Do not restore owner access as an undocumented fallback. The exact versioned configuration/role manifest does not exist yet, so inventing a production role/secret overlay here would misrepresent readiness. Follow [D.2 sequencing](phase3b2d2-role-and-migration-deployment-plan.md) after those artifacts are approved.

## Forward-only recovery and cancellation

inventory.0002 explicitly refuses unapply; 0003 has no reverse SQL. Never run migrate inventory 0001, edit/fake historical migrations or delete migration rows. On an ambiguous connection/commit result, keep writers stopped and inspect both history and catalogs before retrying.

Before commit, the failing migration transaction can roll back; after 0002 commits, failure in 0003 does not undo 0002. Prefer a reviewed forward repair or restore the fresh pre-window archive to a NEW recovery database/volume. Preserve the failed target for analysis; never reset/reuse it-warehouse_postgres_data as an automatic rollback. Restore owner identities/ACLs deliberately and verify history and data before changing application connection configuration.

If any post-cutover writes occurred, preserve them and obtain a reconciliation plan before selecting an older backup. Configuration/connection routing can be reversed; committed schema/history and subsequent writes cannot be made safe by an environment-variable rollback. Keep the application offline if a safe recovery configuration is unavailable.

Cancel deployment for: wrong target/volume/version/HEAD/migration hashes; missing/currently unverified backup; failed restore; unquiesced writers or active audit/cutover conflicts; unexpected history/partial review objects; inconsistent owners; timeout/catalog/constraint/source-fingerprint drift; unexpected permission assignment; pending migration outside these two; unsafe role/configuration changes; any operational review/capture activation; or inability to accept temporary owner risk. Do not weaken guards to get through a cancellation condition.

## Executed work and preservation

Only the new phase3b2d3 containers were created/used. The backup was restored to itw_runtime_rehearsal and an independent itw_recovery_check; itw_runtime_pre preserved the old history. Existing test runners were invoked in isolated databases; the 20 read tests used a separate synthetic phase3b2b1_test database. The disposable postgres password was changed only to satisfy that existing harness's synthetic credential contract; no production credential was accessed/provisioned.

All relevant prior evidence, fixtures, historical migrations and Phase 2C source are preserved. No warehouse workbook was opened. No persistent development read/write/DDL, credential/ACL/owner/history change, operational registration/approval/revocation/promotion, production deployment, inventory.0004, commit or push occurred.

Files added in this phase:

- docs/phase3b2d3-schema-deployment-decision.md
- backend/feasibility_schema/run.py

The new containers are stopped after evidence collection. The named persistent development volume and all existing containers are left untouched.