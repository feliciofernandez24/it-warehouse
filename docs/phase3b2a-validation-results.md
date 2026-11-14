# Phase 3B.2A validation results

Date: 2026-11-14, Asia/Tokyo. All database execution used a dedicated disposable PostgreSQL 17 container; development was not contacted.

## Final results

| Check | Result |
| --- | --- |
| Current-schema regression suite | 173 passed, 23.508 seconds |
| Historical-schema suite | 45 passed, 1.137 seconds |
| Final combined cases | 218 passed, 0 failed, 0 skipped |
| Previous cases preserved | All 190, with fixture-only profile adaptation in Stage A schema tests |
| New focused hardening cases | 28 |
| Earlier focused hardening run before final write-gate test | 27 passed, 0.867 seconds |
| System checks | No issues |
| Migration drift | No changes detected |
| Pre-apply plan | Expected original graph followed by corrected inventory.0002/.0003 |
| Generated SQL | 5 tables, 11 invoker functions, 18 triggers, 4 deferred guards, 11 PUBLIC revocations |
| Fresh apply | Successful through inventory.0003 |
| Post-apply plan | No pending operations |
| Owner/ACL query | Test migration owner postgres; 11 private non-definer functions |
| Rehearsal data | Profiles/revisions/snapshots/events/assets/balances/movements/operations all zero |

The final current suite comprises 97 original current cases, 48 Stage A schema cases and 28 hardening cases. The separate historical registry contributes 43 inventory-schema plus two PostgreSQL transaction cases. No cases were hidden as skips or removed. Original test method coverage is preserved; synthetic helper data now carries an immutable profile.

## Confirmed pre-correction failures

Two completed-transaction regressions failed as expected against the pre-hardening SQL because it accepted a text row number and inconsistent excluded scope/label. They pass after correction.

Initial probe instrumentation was corrected to include SUBMIT event evidence; otherwise an unrelated deferred failure could mask the defect. Profile fixtures were refreshed from the current database hash to test count failure rather than stale binding. The forged-actor test explicitly grants SELECT for INSERT RETURNING so it reaches the new write gate instead of stopping at a table ACL error. These were test-fixture corrections, not weakened protections.

## New cases

The 28 additions cover:

- Missing/unverified/unsupported definitions, malformed/exact counts for arbitrary hashes, workbook/layout/profile digest bindings.
- Profile byte digest/contract, immutable update/delete, duplicate code/version, replacement refusal and server-assigned registrar.
- Runtime profile/capture denial even with DML, and forged actor IDs unable to authorize review mutation.
- Duplicate/missing source/candidate entries, strict numeric row identities, excluded scope/label/reason type agreement.
- Invalid UTF-8, exact-byte SHA-256 versus noncanonical whitespace, rollback after deferred failure and zero stock effects.
- Least-privilege role flags, table/sequence/schema/function inspection, DML/TRUNCATE/DDL/trigger/private-function denial.
- Three observed-lock races: registration first, profile-relevant source change first, and stale concurrent revision/event mutation.

Existing cases retain snapshot/event/participant immutability, lineage/version constraints, active revision uniqueness, reviewer independence, approval/promotion rejection, irreversible migrations and unchanged import-posting rejection.

## Exact environment

Dedicated container: it-warehouse-hardening-test-db, postgres:17-alpine, tmpfs /var/lib/postgresql/data (768 MiB), no volume or host port. No development mounts/network/credentials were used. Runner backend mount is read-only.

Fresh rehearsal database: phase3b2a_hardening. Current tests create/destroy test_phase3b2a_hardening. Historical configuration creates/destroys test_phase3b2a_history in the same disposable server using its separate app registry. Test roles and extra grants exist only inside rolled-back test transactions.

The server is stopped after validation. Existing development PostgreSQL remained stopped; its persistent data and credentials were neither queried nor changed.

## Reproduction

Run from /home/itadmin/projects/it-warehouse in WSL. Values below are disposable test configuration, not production secrets. Existing images provide Python dependencies; nothing is installed into Kali system Python.

Create the dedicated container only if absent; inspect an existing one rather than resetting volumes:

    docker run -d --name it-warehouse-hardening-test-db --network bridge \
      --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=768m \
      -e POSTGRES_PASSWORD=hardening-isolated-test \
      -e POSTGRES_DB=phase3b2a_hardening postgres:17-alpine
    docker exec it-warehouse-hardening-test-db pg_isready -U postgres

Current regression command:

    docker run --rm --network container:it-warehouse-hardening-test-db \
      --mount type=bind,source=/home/itadmin/projects/it-warehouse/backend,target=/app,readonly \
      -e PYTHONDONTWRITEBYTECODE=1 -e DJANGO_SECRET_KEY=hardening-test-only \
      -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=hardening-isolated-test \
      -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_DB=phase3b2a_hardening \
      it-warehouse-backend python manage.py test config.tests \
      apps.inventory.test_staging apps.transactions.test_engine \
      apps.inventory.test_review_schema apps.inventory.test_review_hardening \
      --noinput --verbosity 1

Historical command:

    docker run --rm --network container:it-warehouse-hardening-test-db \
      --mount type=bind,source=/home/itadmin/projects/it-warehouse/backend,target=/app,readonly \
      -e PYTHONDONTWRITEBYTECODE=1 -e DJANGO_SECRET_KEY=hardening-test-only \
      -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=hardening-isolated-test \
      -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_DB=phase3b2a_history -e ITW_ISOLATED_TESTS=1 \
      it-warehouse-backend python manage.py test apps.inventory.tests apps.transactions.tests \
      --settings=config.settings.historical_tests --noinput --verbosity 1

In the current disposable configuration, these alternatives were also executed:

    python manage.py check
    python manage.py makemigrations --check --dry-run
    python manage.py migrate --plan
    python manage.py sqlmigrate inventory 0002_import_review_schema
    python manage.py sqlmigrate inventory 0003_import_review_guards
    python manage.py migrate --noinput
    python manage.py migrate --plan

Stop only this dedicated container:

    docker stop it-warehouse-hardening-test-db

No unpartitioned historical test run, reverse review migration, development migrate or volume reset is part of the procedure.

## Limits of validation

These results demonstrate schema, profile metadata, privilege and tested locking behavior, not authenticated source truth or full business approval. SQL-owner fixtures are not a production capture gateway. Canonical byte spelling, duplicate JSON-key rejection, signed actor/evidence assertions, master/permission coordination and source consumption remain blocked. Approval and promotion are still disabled. No real candidate was marked ready or approved.
