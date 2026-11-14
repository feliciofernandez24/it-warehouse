# Phase 3B.2D.2 isolated review read proof

Synthetic-only prototype. No application startup installer, migration, endpoint or production identity service. Never install gateway.sql or its synthetic principal/login mapping in development/production.

The gateway's NOLOGIN owner has selected metadata-column reads only and no application-table ownership or DML. Real proof LOGINs are bound through session_user, with administrator-controlled batch scopes. This is not human authentication behind shared Django credentials. The adapter is disabled by default and the actual shared runtime remains unmapped/denied.

## Reproduction

From /home/itadmin/projects/it-warehouse in Linux/WSL, use fresh unused container names. Do not reuse a persistent volume or load .env. The existing it-warehouse-backend image supplies Django and psycopg; no package installation or backup/source workbook is needed.

~~~sh
docker run -d --name it-warehouse-phase3b2d2-db --network bridge \
  --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=768m \
  -e POSTGRES_PASSWORD=phase3b2d2-synthetic-only -e POSTGRES_DB=phase3b2b1_test postgres:17-alpine
docker exec it-warehouse-phase3b2d2-db pg_isready -U postgres

docker run -d --name it-warehouse-phase3b2d2-client \
  --network container:it-warehouse-phase3b2d2-db \
  --mount type=bind,source=/home/itadmin/projects/it-warehouse/backend,target=/app,readonly \
  -e PYTHONDONTWRITEBYTECODE=1 -e DJANGO_SECRET_KEY=phase3b2d2-synthetic-only \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=phase3b2d2-synthetic-only \
  -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_DB=phase3b2b1_test it-warehouse-backend sleep infinity
~~~

Wait for readiness and verify PostgreSQL major 17 before continuing. The tested image resolved to 17.11; mutable tags may differ later. Run existing regressions first:

~~~sh
docker exec it-warehouse-phase3b2d2-client python manage.py test \
  config.tests apps.inventory.test_staging apps.transactions.test_engine \
  apps.inventory.test_review_schema apps.inventory.test_review_hardening \
  apps.inventory.test_review_services apps.inventory.test_review_gateway --noinput
docker exec -e POSTGRES_DB=phase3b2a_history -e ITW_ISOLATED_TESTS=1 \
  it-warehouse-phase3b2d2-client python manage.py test apps.inventory.tests apps.transactions.tests \
  --settings=config.settings.historical_tests --noinput

docker exec it-warehouse-phase3b2d2-client python manage.py migrate --noinput
docker exec -e ITW_REVIEW_READ_PROOF=1 it-warehouse-phase3b2d2-client python feasibility_review_read/run.py
docker exec it-warehouse-phase3b2d2-client cat /tmp/phase3b2d2-evidence.json
~~~

Expected: 205 current +45 historical +20 new proof methods, all passing. run.py validates the explicit isolation environment and server major, then uses existing owner-only test fixtures to seed synthetic metadata. Fixtures use CAPTURE/START/EDIT/SUBMIT/REVIEW_ACCEPT solely for test setup; the new gateway itself performs no mutations. It has no registration/approval/revocation/promotion action.

The script installs proof objects in an atomic test transaction and uses independently generated ephemeral passwords for actual nonowner LOGIN connections. No passwords are written to evidence. Tests verify metadata-only output, ACL denials, batch/actor isolation, current authority, sanitized errors and a real advisory-lock revocation race.

## Existing runtime compatibility, after proof evidence is collected

~~~sh
docker exec -e ITW_REVIEW_READ_PROOF=1 it-warehouse-phase3b2d2-client \
  python feasibility_review_read/runtime_regression.py
docker exec it-warehouse-phase3b2d2-client cat /tmp/phase3b2d2-runtime-evidence.json
docker exec -e POSTGRES_PASSWORD=runtime-rehearsal-admin-only \
  it-warehouse-phase3b2d2-client python manage.py makemigrations --check --dry-run
~~~

runtime_regression.py creates a fresh SYNTHETIC clone named itw_runtime_rehearsal and reconstructs the previous owner/migration/runtime role model. It does not restore a backup. It explicitly changes that clone's public object ownership for the test and changes only this disposable cluster's postgres password to the older harness's synthetic expected value. Consequently run this last; fresh setup is required for a full reproduction.

It reuses the untouched existing feasibility_runtime files and runs RuntimeTests (12) +ReviewTests (4), all passing. It additionally checks the actual shared Django LOGIN identity and its IDENTITY_VERIFICATION_UNAVAILABLE result after granting read-gateway EXECUTE, without adding a principal mapping. That manual assertion is not counted as another test.

A troubleshooting-only --existing-clone option can rerun these tests on the already provisioned disposable clone. It must never be used to target a live/restored development database. The original runtime probe compared raw Django JSONB text with a dict; the corrected script decodes it, and the successful final rerun passed.

Evidence remains in the client /tmp directory. Copy/retrieve it before cleanup; no private keys, real workbook cells or original inventory data exist in this proof. Credentials in fixture code are synthetic only.

~~~sh
docker stop it-warehouse-phase3b2d2-client it-warehouse-phase3b2d2-db
~~~

Stop only these two new containers; their database tmpfs contents disappear. No previous test/development container or volume should be touched.

See [architecture](../../docs/phase3b2d2-review-read-gateway.md), [security results](../../docs/phase3b2d2-security-validation.md), [future deployment plan](../../docs/phase3b2d2-role-and-migration-deployment-plan.md) and [NO-GO decision](../../docs/phase3b2d2-readiness-decision.md). Existing B.1 service code remains unchanged and unready for operational shared-runtime reads until trusted human identity and scope management are implemented.