# Phase 3B.2D.4 forward-only recovery

**A failure means retain maintenance isolation until a known state is verified.** This document does not authorize development recovery mutations. Do not reverse either migration, fake history, disable integrity triggers, delete/recreate the original volume or restore over the live database.

Retain the private journal, before/after manifests, fresh backup, role metadata, archive listing, restore proof, command status/times and stderr under restricted permissions. If later app writes occurred, preserve them before selecting an older recovery point.

## Read-only classification

Use the same pinned project/config and target identity checks. Collect a fresh audit into a NEW private directory; audit performs no DDL, DML or maintenance. For an ambiguous migration connection result, inspect via local retained access:

~~~sh
docker exec -e PGOPTIONS=-cdefault_transaction_read_only=on it-warehouse-db-1 psql -X -v ON_ERROR_STOP=1 -U it_warehouse -d it_warehouse -c "SELECT app,name FROM django_migrations WHERE app IN ('inventory','transactions') ORDER BY app,name; SELECT relname,pg_get_userbyid(relowner) FROM pg_class WHERE relnamespace='public'::regnamespace AND relname LIKE 'inventory_import%' AND relkind='r' ORDER BY relname; SELECT proname,prosecdef,proacl FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname LIKE 'itw_review_%' ORDER BY proname; SELECT pid,usename,state,xact_start IS NOT NULL AS in_transaction FROM pg_stat_activity WHERE datname=current_database();"
~~~

Do not infer a rollback from a failed CLI exit or infer a commit from tables alone. Match history AND catalog objects/constraints/triggers with the private baseline. An open migration transaction must be resolved first; do not kill an unidentified session.

## A — failure before any migration

If no maintenance began, there is nothing to restore. Fix the preparation problem, discard no evidence and start with a new private state directory.

If isolation completed but apply did not begin, compare source rows, owners/ACLs/roles, history, sequence and guard definitions against before.json. Only when unchanged, the authorized operator may run:

~~~sh
python3 "$d4_runner" resume --config "$d4_config" --state "$d4_state" --execute-development --approval "$d4_approval" --allow-pre-migration-abort
~~~

The flag is not a schema rollback. It requires exact history and preservation comparison and resumes only recorded active services. If isolation failed midway, do not re-run isolate: inspect the journal and actual endpoints/containers, complete a reviewed reconciliation and restore only the recorded disconnections. Do not manufacture a success marker. Failure before a before-manifest exists requires independent comparison and manual approved recovery.

Disposable validation: isolation followed by this abort path restored the original running/stopped mock states, the same DB container/mounts and recorded networking.

## B — failure during an uncommitted migration

A failed atomic migration rolls its own transaction back, not a prior migration. Wait for/resolve the known migration session; inspect history/catalogs afterward.

- Neither 0002 nor 0003 committed: verify exact original state, then use A or plan a new authorized attempt with a new fresh backup.
- 0002 committed, 0003 absent: the five tables and 0002 history are expected. Keep application offline. Confirm no 0003 functions/triggers survived and that original records/guards are intact. Normal apply refuses this partial state.
- Do not force the normal preflight through by deleting 0002 history, manually dropping tables or faking migrations.
- The operator must choose a separately reviewed forward completion of 0003 after identifying the cause, or a new-target recovery. A bespoke partial-state forward procedure must validate its precise plan and fresh recovery evidence; it is deliberately not automated here.

Disposable validation held an ACCESS EXCLUSIVE lock on importbatch, applied 0002, then forced 0003 to hit a one-second lock timeout. 0003 history and all review functions remained absent, while 0002 remained committed. The ordinary apply and complete-schema verify both rejected that target. No guard was disabled.

## C — commit succeeded but verification failed

Keep all writers stopped. Preserve the failed DB and take a separately authorized forensic backup if required. Determine whether failure is an inspection/configuration problem, an unexpected metadata addition, changed source data, schema inconsistency or guard drift. Repair forward only through a reviewed change; no inventory.0004 is created by this phase.

A changed verifier/manifest is not permission to bless the target. Recreate evidence on an independent restored twin and review the discrepancy. Resume only after every preservation/catalog/security/smoke gate passes. If integrity cannot be established, use F and preserve the failed target for analysis.

## D — unknown commit outcome

A dropped connection or lost response may follow a successful commit. Do not rerun apply. Read history and catalogs using the classification query. If both migrations and catalogs are complete, run the read-only verifier against the original before-manifest; successful verification establishes outcome without a duplicate migration. If partial, use B; if neither committed, use A/B; if inconsistent, use C/F.

The code's normal apply rejects an already-installed schema. The independent read-only complete-schema verifier was tested after successful commit; history remained 29 rows and no replay writes occurred. Automatic recovery cannot infer outcome from a log message alone.

## E — application incompatibility

Do not undo committed schema. Keep/re-enter the approved application maintenance state and retain DB networking isolation where safe. Diagnose connection identity/configuration, missing grants or application behavior against the disposable twin. Revert only a reviewed reversible application/configuration change that remains compatible with the installed schema and migration history.

Never fall back from a failed restricted-role cutover to superuser credentials silently. This migration contains no role cutover. Do not start previously stopped services merely for a health check. Stock mutations, login/session fixture tests and destructive guard probes remain confined to disposable databases.

If no compatible application deployment is available, keep services offline and choose a forward fix or F. Subsequent writes require reconciliation before an older backup can serve traffic.

## F — PostgreSQL unavailable or logical restoration required

Do not reset or replace it-warehouse_postgres_data. Preserve original container/volume/configuration and record why unavailable. Storage/host investigation and a separately authorized recovery decision precede changes.

Verify the private backup and role-manifest checksums, archive list, source version/dependencies, secret/configuration recovery capability and recovery-point acceptability. The rehearsed safe command is a NEW-target restore proof:

~~~sh
python3 "$d4_runner" restore-check --config "$d4_config" --state "$d4_state" --restore-name "$d4_restore" --execute-development --approval "$d4_approval"
~~~

This command requires the original target to remain inspectable and isolated. If it is unavailable, it intentionally stops; it is not an automatic availability recovery tool. The pure restore implementation in runbook.py creates only a NEW named tmpfs container, restores passwordless roles, DB owner/extension, then the archive with --single-transaction --exit-on-error, and compares the baseline. failure_tests uses it without depending on an available original and successfully reconstructed a separate recovery target while leaving the partial failed target intact.

A tmpfs proof is NOT durable replacement service storage. A durable recovery requires separate authorization specifying a new unused persistent volume/container, approved administrator/role secrets, network/routing plan, retention, capacity and reconciliation. Do not route applications to a synthetic-password restore or copy its superuser restore_admin into an application configuration. No executable durable cutover is claimed ready here.

After a separately approved new-target restore, validate every original row/ACL/owner/history/guard and secret configuration before choosing forward migration and application routing. Keep the original failed volume retained. Routing/configuration changes can be reversed; committed schema/history and lost post-backup writes cannot.

## Rehearsed coverage and limits

| Scenario | Evidence |
| --- | --- |
| Empty/failed dump and corrupt archive | rejected; no successful backup proof |
| Missing authorization | all six development mutation paths denied before side effects |
| Source row / role / ACL drift | comparator rejects |
| Pre-migration abort | isolated disposable target restored original network/service states |
| Uncommitted 0003 after 0002 commit | real lock timeout; 0003 rolled back; partial retry rejected |
| Known complete result after response ambiguity | read-only verification succeeds without rerunning migrations |
| New-target restore | source data, role attributes/membership, owners/ACLs/history matched; failed target retained |
| Full daemon/storage outage or post-cutover reconciliation | procedural only; no persistent infrastructure failure was injected |

Stop for uncertainty, unexpected dependents/sessions, missing approved secrets/recovery capacity, expired/changed backup, source/guard drift, partial resume or unknown commit state. Never weaken an integrity guard to restore service.
