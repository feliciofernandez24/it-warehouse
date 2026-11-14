# Disposable restored-database runtime-role rehearsal

Test-only harness. Never point this at development/production, load .env, reset a persistent volume or deploy the synthetic roles/function. The runner requires explicit synthetic runtime settings, a known rehearsal database name, ITW_RUNTIME_REHEARSAL=1 and PostgreSQL 17.11. Those guards supplement the dedicated-container boundary; database names alone are not isolation.

The source backup must hash to 2dfe16325d081973a41d246a065c631dc54560d459419d411fd820f057f97697. No original workbook is needed.

## Reproduce in Linux/WSL

Start from /home/itadmin/projects/it-warehouse. Use unused container names and verify the backup before creating anything:

~~~sh
sha256sum /home/itadmin/it-warehouse-db-backups/it_warehouse_pre_review_migration_20261114_111141.dump

docker run -d --name it-warehouse-runtime-separation-db --network bridge \
  --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=768m \
  --mount type=bind,source=/home/itadmin/it-warehouse-db-backups/it_warehouse_pre_review_migration_20261114_111141.dump,target=/verified-backup.dump,readonly \
  -e POSTGRES_PASSWORD=runtime-rehearsal-admin-only \
  -e POSTGRES_DB=itw_runtime_rehearsal postgres:17-alpine
docker exec it-warehouse-runtime-separation-db pg_isready -U postgres
~~~

Confirm readiness and PostgreSQL 17.11; the mutable image tag may resolve differently later. Run these commands only against that container:

~~~sh
docker exec it-warehouse-runtime-separation-db psql -U postgres -d itw_runtime_rehearsal \
  -v ON_ERROR_STOP=1 -c "CREATE ROLE it_warehouse NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; CREATE ROLE itw_rehearsal_migrator LOGIN PASSWORD 'migration-rehearsal-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; GRANT it_warehouse TO itw_rehearsal_migrator; ALTER DATABASE itw_runtime_rehearsal OWNER TO it_warehouse;"
docker exec it-warehouse-runtime-separation-db pg_restore --exit-on-error \
  -U postgres -d itw_runtime_rehearsal /verified-backup.dump
docker exec it-warehouse-runtime-separation-db createdb -U postgres -O it_warehouse itw_runtime_pre
docker exec it-warehouse-runtime-separation-db pg_restore --exit-on-error \
  -U postgres -d itw_runtime_pre /verified-backup.dump

docker run -d --name it-warehouse-runtime-separation-client \
  --network container:it-warehouse-runtime-separation-db \
  --mount type=bind,source=/home/itadmin/projects/it-warehouse/backend,target=/app,readonly \
  -e PYTHONDONTWRITEBYTECODE=1 -e DJANGO_SECRET_KEY=runtime-rehearsal-synthetic \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=runtime-rehearsal-admin-only \
  -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_DB=itw_runtime_rehearsal \
  it-warehouse-backend sleep infinity

docker exec -e POSTGRES_USER=itw_rehearsal_migrator \
  -e POSTGRES_PASSWORD=migration-rehearsal-only -e PGOPTIONS=-crole=it_warehouse \
  it-warehouse-runtime-separation-client python manage.py showmigrations inventory transactions
docker exec -e POSTGRES_USER=itw_rehearsal_migrator \
  -e POSTGRES_PASSWORD=migration-rehearsal-only -e PGOPTIONS=-crole=it_warehouse \
  it-warehouse-runtime-separation-client python manage.py migrate inventory 0003 --noinput
docker exec it-warehouse-runtime-separation-db createdb -U postgres -O it_warehouse \
  -T itw_runtime_rehearsal itw_runtime_gateway_auth
~~~

Run the three stages with explicit runtime credentials. The migration and application identities are distinct. Runtime receives no role memberships.

~~~sh
docker exec -e ITW_RUNTIME_REHEARSAL=1 -e POSTGRES_DB=itw_runtime_pre \
  -e POSTGRES_USER=itw_django_rehearsal -e POSTGRES_PASSWORD=runtime-rehearsal-only \
  it-warehouse-runtime-separation-client python feasibility_runtime/run.py pre
docker exec -e ITW_RUNTIME_REHEARSAL=1 -e POSTGRES_DB=itw_runtime_rehearsal \
  -e POSTGRES_USER=itw_django_rehearsal -e POSTGRES_PASSWORD=runtime-rehearsal-only \
  it-warehouse-runtime-separation-client python feasibility_runtime/run.py post
docker exec -e ITW_RUNTIME_REHEARSAL=1 -e POSTGRES_DB=itw_runtime_gateway_auth \
  -e POSTGRES_USER=itw_django_rehearsal -e POSTGRES_PASSWORD=runtime-rehearsal-only \
  it-warehouse-runtime-separation-client python feasibility_runtime/run.py gateway
~~~

Expected final counts: 12,16,18 passed respectively, no failures/errors/skips. These are 18 distinct methods across three configurations, 46 successful final-stage executions. Evidence is written inside the client at /tmp/runtime-rehearsal-pre.json, post.json and gateway.json. Capture those files before stopping the container.

The harness provisions only test ACLs/roles. Owner alias is used solely for synthetic fixture setup; assertions and application services use the real restricted default LOGIN. Each stock test rolls its transaction back. Gateway stage commits one dummy CAPTURE proof over synthetic source records; it neither verifies a workbook nor authenticates an upload. Gateway stage requires a fresh migrated clone on each run; do not reverse migrations or reuse an already transferred schema.

No extension/pip installation is needed. The existing backend image supplies Django/psycopg. All earlier committed feasibility files and application code remain unchanged. Test-only helpers reuse the synthetic proof body from feasibility_capture/common.py; that body must not become a deployed registration function.

After evidence collection:

~~~sh
docker stop it-warehouse-runtime-separation-client it-warehouse-runtime-separation-db
~~~

Only the two named new containers are stopped; tmpfs database contents disappear. Do not stop development containers or delete volumes. See [results](../../docs/runtime-role-separation-rehearsal.md) and [grant matrix](../../docs/runtime-role-grant-matrix.md) for operational blockers and configuration proposals.