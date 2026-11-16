# Phase 3B.2D.4 maintenance and backup

**Future commands below require separate development deployment authorization. They were rehearsed only on disposable targets. Do not execute the development sequence during preparation.**

## Prerequisites and writer inventory

Run from WSL Linux, not Windows Git. No credential-bearing Compose expansion or docker environment dump is needed.

~~~sh
cd /home/itadmin/projects/it-warehouse
git rev-parse HEAD
git status --short
docker compose ps -a
docker ps -a --format '{{.Names}} {{.Status}} {{.Networks}}'
docker inspect it-warehouse-db-1 --format '{{.Id}} {{json .Mounts}} {{json .NetworkSettings.Networks}}'
crontab -l
systemctl list-timers --all
systemctl list-units --type=service --state=running
df -Pk /home/itadmin/it-warehouse-db-backups
docker exec it-warehouse-db-1 df -Pk /var/lib/postgresql/data
~~~

Record the exit status of crontab inspection; distinguish “no crontab” from permission/inspection failure. Review other users' schedules, workers, application connection inventories and network members with the authorized host administrator. Obtain explicit confirmation that no unrelated service depends on this database. Do not terminate unknown clients or stop unrelated containers to force a pass.

Read-only live census:

~~~sh
docker exec -e PGOPTIONS=-cdefault_transaction_read_only=on it-warehouse-db-1 psql -X -v ON_ERROR_STOP=1 -U it_warehouse -d it_warehouse -c "SELECT pid,usename,application_name,client_addr,state,xact_start IS NOT NULL AS in_transaction FROM pg_stat_activity WHERE datname=current_database();"
~~~

All background writers must be stopped under their own reviewed service commands before proceeding. These cannot be invented from a single empty census. At preparation time backend/frontend were already stopped and no worker was declared. Approval must identify any newly discovered jobs and their exact stop/restart instructions.

## Isolation mechanics

`runbook.py isolate` records database ID/mounts/networks and each configured application container ID/status in a private journal. It refuses an unexpected target, image, volume or existing state file. It stops only configured applications that were running. It disconnects the DB from its recorded bridge networks, verifies no remaining network endpoints and zero other database clients, and rechecks the same ID/mounts/system identifier.

The implementation is intentionally conservative: other sessions detected at initial inspection cause cancellation before service changes. If current apps have long-lived connections, coordinate their stop under the separately authorized window, record their original status first, and independently review that change; do not bypass the gate or lose the original restart record.

No DB stop/start/recreate, Compose up/down, volume deletion, role alteration, HBA edit or database connection-limit change is used. Namespace-local migration access remains available via Docker exec and a pinned one-off client sharing the DB namespace. A separate disposable probe verifies external bridge access fails after disconnection.

This boundary assumes exclusive Docker/host administrative control. It cannot constrain another host administrator, root, an existing local-trust actor or an independently retained DB session. If those actors cannot be controlled, cancel. Removing all networks may affect unrelated dependencies; explicit attestation precedes it.

## Fresh backup

The [migration runbook](phase3b2d4-migration-runbook.md) supplies the exact guarded CLI. Each new timestamped state directory is mode 0700; backup, role SQL, manifests and inspection evidence are mode 0600. They belong on the private backup filesystem, never in Git or a public artifact store.

`backup` requires isolation and the exact pending plan. It takes:
- `pg_dump -U it_warehouse -d it_warehouse -Fc`;
- `pg_dumpall -U it_warehouse --roles-only --no-role-passwords`;
- a before-manifest with server-side SHA-256 of every original row and key, counts, sequence state, function/trigger definitions, owners, ACLs, role attributes/memberships, default ACLs, extension owner/version and migration history.

No shell pipeline is involved. Python checks each subprocess exit code, uses exclusive file creation, flushes/fsyncs, rejects empty output and verifies custom archive structure with `pg_restore --list`. Failed partial files remain private for diagnosis; there is no successful-backup marker. Never reuse that directory after failure.

Minimum free host space is max(1 GiB, eight times database size). The disposable recovery DB has 1 GiB tmpfs; the script rejects a source estimate above its conservative capacity. Also verify Docker-host available memory before the window; filesystem space does not prove memory capacity. Expand/rehearse a reviewed capacity configuration if the database grows. Preparation capacity was ample for the approximately 10 MiB source.

The fresh backup expires for apply/verification after two hours. Cancellation/review is required if the window exceeds that bound; do not edit timestamps. Hash manifests bind backup, role metadata and before-manifest. The restore proof must match those bytes.

## Restore proof and recovery coverage

`restore-check` creates a NEW explicitly named PostgreSQL 17.11 container on tmpfs, network none, pinned image, separate restore_admin and synthetic credentials. It restores role attributes/membership without passwords, creates the DB under the original owner, reconstructs built-in plpgsql ownership in that empty disposable database, and uses `pg_restore --single-transaction --exit-on-error` with original ownership and ACL entries.

It compares all source row hashes/counts, table/sequence ACLs/owners/state, migration history, database/schema/default ACL metadata, source roles/membership and stock function/trigger definitions. The disposable restore_admin is the sole permitted additional role. This proof is more than a no-owner/no-acl data restore.

This is still a logical recovery proof, not a full cluster backup: source password hashes, server files/HBA, WAL/PITR, tablespace layouts, Docker secrets and arbitrary cluster configuration are not recovered. The observed source has only plpgsql, no memberships/default ACL entries and standard public objects. Any new extensions, tablespaces, role settings or ownership topology require expanded review. Keep the approved configuration/secret recovery process separately; never reuse synthetic restore passwords.

## Historical archive and preparation result

The archive at `~/it-warehouse-db-backups/it_warehouse_pre_review_migration_20261114_111141.dump` was 203233 bytes, mode 0600, with SHA-256:

`2dfe16325d081973a41d246a065c631dc54560d459419d411fd820f057f97697`.

It restored successfully to disposable PostgreSQL 17.11. A new backup of that disposable restored source was independently restored and compared with role/ACL/owner metadata intact. This does not replace a fresh isolated development backup at deployment time. No fresh development dump or maintenance isolation was executed in this phase.
