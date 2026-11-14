# Phase 3B.2A testing and isolation evidence

Date: 2026-11-13, Asia/Tokyo.

## Final TESTED results

| Suite / check | Result |
| --- | --- |
| Unchanged historical-schema cases | 45 passed, 1.295 seconds |
| Final current-schema suite | 145 passed, 21.768 seconds |
| Breakdown of final current suite | 97 original current cases + 48 new schema/concurrency cases |
| Combined preserved baseline | All original 142 cases passed across the two registries |
| Combined final cases | 190 passed; 0 failed; 0 skipped |
| Prior focused schema rerun | 47 passed, 0.884 seconds |
| Django system check | No issues |
| makemigrations --check --dry-run | No changes detected |
| Fresh migration application | All migrations through inventory.0003 applied successfully |
| Post-apply migrate --plan | No pending operations |
| sqlmigrate review | 4 new tables; 9 invoker functions; 16 triggers, 4 deferred; 9 PUBLIC EXECUTE revocations |
| Source/stock protection | Protected source hash and historical migration/service files unchanged; no development connection |

Initial focused run found one test expectation error: deleting an unreferenced source row is rejected by the existing history trigger, rather than by an ORM PROTECT relation. The test was corrected to assert the actual database guard separately. Final suites have no failures or skips.

Current tests include the existing engine's synthetic stock fixtures. New review tests never post inventory; they compare stock tables before/after schema actions. No live inventory is created. All schema/movement fixtures are confined to disposable test databases.

## Isolated environments

Dedicated container: it-warehouse-phase3b2a-test-db, postgres:17-alpine, tmpfs data (768 MiB), no persistent volume, no port publication. Runner containers join only that container's network namespace; backend mount is read-only. Development Compose containers/volume were not reused, started, connected or migrated.

Fresh migration rehearsals used phase3b2a_current and phase3b2a_fresh inside that container. Current Django tests created/destroyed test_phase3b2a_fresh. Historical tests created/destroyed test_phase3b2a_history. The dedicated container is stopped after final validation; its memory-backed data is disposable.

## Historical strategy ? IMPLEMENTED

The original 43 SchemaTests and two PostgreSQLTransactionTests still execute unchanged. Their setup intentionally migrates to transactions.0003 and restores its graph. Running those classes in the new current graph would try to unapply irreversible review schema and must not be used.

config.settings.historical_tests replaces only the inventory app config and migration namespace in its own process. Its registry removes the four new models and expires relation caches; the migration alias imports the exact original inventory.0001 Migration class. All other historical tests and migrations are unchanged.

Settings require ITW_ISOLATED_TESTS=1, POSTGRES_DB=phase3b2a_history and POSTGRES_HOST=127.0.0.1. This is a separate database/app registry, not disabling production triggers or inventing reverse SQL.

Use the partitioned commands below. An unpartitioned default manage.py test is not the supported runner for historical cases under the irreversible graph. Neither hiding historical cases as skips nor weakening reversibility is acceptable. Preserve the two command sets in CI.

## Reproduction commands

Run in WSL from /home/itadmin/projects/it-warehouse. The existing backend image contains dependencies; no system Python installation is required. Credentials below are disposable test values, not development secrets.

Create the dedicated container only if absent; if it already exists, inspect it rather than resetting anything:

    docker run -d --name it-warehouse-phase3b2a-test-db --network bridge \
      --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=768m \
      -e POSTGRES_PASSWORD=phase3b2a-isolated-test \
      -e POSTGRES_DB=phase3b2a_current postgres:17-alpine
    docker exec it-warehouse-phase3b2a-test-db pg_isready -U postgres
    docker exec it-warehouse-phase3b2a-test-db createdb -U postgres phase3b2a_fresh

Common current-schema runner, with its final command varied for checks:

    docker run --rm --network container:it-warehouse-phase3b2a-test-db \
      --mount type=bind,source=/home/itadmin/projects/it-warehouse/backend,target=/app,readonly \
      -e PYTHONDONTWRITEBYTECODE=1 -e DJANGO_SECRET_KEY=phase3b2a-test-only \
      -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=phase3b2a-isolated-test \
      -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_DB=phase3b2a_fresh \
      it-warehouse-backend python manage.py test \
      config.tests apps.inventory.test_staging apps.transactions.test_engine \
      apps.inventory.test_review_schema --noinput --verbosity 1

Executed management-command alternatives in that isolated configuration:

    python manage.py check
    python manage.py makemigrations --check --dry-run
    python manage.py migrate --noinput
    python manage.py migrate --plan
    python manage.py sqlmigrate inventory 0002_import_review_schema
    python manage.py sqlmigrate inventory 0003_import_review_guards

Historical runner:

    docker run --rm --network container:it-warehouse-phase3b2a-test-db \
      --mount type=bind,source=/home/itadmin/projects/it-warehouse/backend,target=/app,readonly \
      -e PYTHONDONTWRITEBYTECODE=1 -e DJANGO_SECRET_KEY=phase3b2a-test-only \
      -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=phase3b2a-isolated-test \
      -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_DB=phase3b2a_history \
      -e ITW_ISOLATED_TESTS=1 it-warehouse-backend python manage.py test \
      apps.inventory.tests apps.transactions.tests \
      --settings=config.settings.historical_tests --noinput --verbosity 1

Stop only the dedicated temporary container when finished:

    docker stop it-warehouse-phase3b2a-test-db

No development migrate, volume deletion/reset or signing-key operation is part of these instructions.

## New protection coverage

48 cases demonstrate capture version/actor semantics; explicit grants and inactive/superuser denial; duplicate active revisions; wrong/skipped parent/number; inherited contributors; atomic supersession; event/version/state/payload consistency; snapshot byte hash/JSON/source coverage; snapshot one-to-one and direct UPDATE/DELETE rejection; event UPDATE/DELETE rejection; source/snapshot ownership mismatch; uploader/editor independence; registered source freeze with mutable ordinary notes; unregistered behavior preservation; legacy approval adoption refusal; field/FK protections; participant freeze; sealed payload rejection; request uniqueness; rollback; no stock effects; authoritative partial-capture rejection; function ACL/search paths/deferred triggers; absent default sensitive permissions; nonowner DML/DDL/helper denial; irreversible migrations; explicit import-linked posting rejection with zero persisted stock effects; malformed JSON; terminal rejection; and competing initial revisions across separate connections.

Deferred checks are forced with SET CONSTRAINTS ALL IMMEDIATE inside tests, then restored to deferred mode; failures roll back the atomic block. The concurrency test uses committed synthetic source rows and a barrier, demonstrating exactly one committed initial revision and no stock effects.

## Not claimed

These tests do not validate external source authenticity, canonical approval encoding, complete receipt-plan correctness, an authenticated actor gateway, permission/master races, application writer grants, cryptographic signatures, production retention, or a working approval/promotion service. Those controls remain BLOCKED/NOT IMPLEMENTED and approval stays disabled.
