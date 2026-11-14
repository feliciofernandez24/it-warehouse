# Isolated capture feasibility harness

This directory is test-only. It does not install a gateway at application startup, add a migration or expose an endpoint. Its synthetic SQL functions do not authenticate real uploaders or register warehouse workbooks. Never install its objects or credentials in a development/production database.

Use fresh disposable PostgreSQL 17 and a separate runner. No .env, compose database, original source workbook or persistent volume is needed. run.py requires ITW_CAPTURE_FEASIBILITY=1, the documented synthetic base database/password and loopback host. It validates PostgreSQL major version and only permits its base or phase3b2b2a_* clones. Network namespace isolation, not the database-name check alone, guarantees the host is disposable.

## Tested setup

Run from /home/itadmin/projects/it-warehouse in Linux/WSL. These names must be unused for a fresh run; do not reset an existing volume or replace an existing database. The examples are isolated test commands, not a production deployment script.

~~~sh
docker run -d --name it-warehouse-phase3b2b2a-test-db --network bridge \
  --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=768m \
  -e POSTGRES_PASSWORD=phase3b2b2a-isolated-only \
  -e POSTGRES_DB=phase3b2b1_test postgres:17-alpine
docker exec it-warehouse-phase3b2b2a-test-db pg_isready -U postgres

docker run -d --name it-warehouse-phase3b2b2a-client \
  --network container:it-warehouse-phase3b2b2a-test-db \
  --mount type=bind,source=/home/itadmin/projects/it-warehouse/backend,target=/app,readonly \
  -e PYTHONDONTWRITEBYTECODE=1 -e DJANGO_SECRET_KEY=phase3b2b2a-synthetic \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=phase3b2b2a-isolated-only \
  -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_DB=phase3b2b1_test \
  it-warehouse-backend sleep infinity
~~~

Wait for successful readiness before continuing. The existing backend image supplies Django/psycopg; no host Python install is needed. The tested PostgreSQL image resolved to 17.11, not a claim that the mutable tag always selects that version.

## Baseline, before extension experiments

~~~sh
docker exec it-warehouse-phase3b2b2a-client python manage.py test \
  config.tests apps.inventory.test_staging apps.transactions.test_engine \
  apps.inventory.test_review_schema apps.inventory.test_review_hardening \
  apps.inventory.test_review_services apps.inventory.test_review_gateway --noinput
docker exec -e POSTGRES_DB=phase3b2a_history -e ITW_ISOLATED_TESTS=1 \
  it-warehouse-phase3b2b2a-client python manage.py test \
  apps.inventory.tests apps.transactions.tests \
  --settings=config.settings.historical_tests --noinput
docker exec it-warehouse-phase3b2b2a-client python manage.py migrate --noinput
docker exec it-warehouse-phase3b2b2a-client python manage.py makemigrations --check --dry-run
~~~

These passed 205 current +45 historical cases, fresh migration and model-drift checks. Historical tests use a separate registry/database; never reverse the current migrations.

## Crypto build in the disposable container only

~~~sh
docker exec it-warehouse-phase3b2b2a-test-db apk add --no-cache build-base libsodium-dev git
docker exec it-warehouse-phase3b2b2a-test-db git clone --depth 1 --branch v3.1.11 \
  https://github.com/michelp/pgsodium.git /tmp/pgsodium
docker exec -w /tmp/pgsodium it-warehouse-phase3b2b2a-test-db git rev-parse HEAD
~~~

Verify the resolved commit is a8b8a2739bab1f7a07445b1c911e2bd1abf67784 before building.

~~~sh
docker exec -w /tmp/pgsodium it-warehouse-phase3b2b2a-test-db make with_llvm=no
docker exec -w /tmp/pgsodium it-warehouse-phase3b2b2a-test-db make install with_llvm=no
docker exec it-warehouse-phase3b2b2a-test-db psql -U postgres -d phase3b2b1_test \
  -c 'CREATE EXTENSION pgsodium;'
docker exec it-warehouse-phase3b2b2a-client pip install --no-cache-dir cryptography==50.0.2
docker exec -e ITW_CAPTURE_FEASIBILITY=1 it-warehouse-phase3b2b2a-client \
  python feasibility_capture/run.py
docker exec it-warehouse-phase3b2b2a-client cat /tmp/itw-feasibility-evidence.json
~~~

Actual installed libsodium was 1.0.22-r0. Package repositories and Docker tags are mutable; report resolved versions on every reproduction. The extension is administrator-owned. No shared-preload/root-key setup is added. Its unrelated masking DDL hook fails ownership ALTERs without its setting; common.connect sets pgsodium.enable_event_trigger=off only for isolated administrator sessions. This is a documented packaging blocker, not an inventory guard bypass or approved production configuration.

The final suite passes 34 methods: ownership 6, signatures 12, auth locking 6, artifact retention 6 and canonical/timezone 4. It leaves isolated clone databases/roles in the disposable cluster for inspection; reruns create fresh uniquely named clones. Same-cluster role reuse is for test convenience only. Artifacts use temporary directories removed by test cleanup.

The SQL functions use static synthetic fixtures/claims, not live sessions or verified workbook content. Signature tests keep ephemeral private keys in the synthetic client only. Runtime tests use actual nonsuperuser LOGIN connections. SQL canonical-byte enforcement is deliberately absent and tested as a BLOCKER; do not infer readiness from a green suite. See [results](../../docs/phase3b2b2a-feasibility-results.md).

After collecting evidence, stop only the two new containers. Stopping the database discards tmpfs data; do not restart the proof against any persistent database.

~~~sh
docker stop it-warehouse-phase3b2b2a-client
docker stop it-warehouse-phase3b2b2a-test-db
~~~