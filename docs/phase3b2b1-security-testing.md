# Phase 3B.2B.1 security validation

Validation date: 2026-11-14. Only synthetic fixtures and PostgreSQL 17 in a disposable container
were used. No development PostgreSQL connection or source workbook parsing was needed.

## Results

| Suite | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| Current prior baseline | 173 | 0 | 0 |
| New service and gateway security tests | 32 | 0 | 0 |
| Historical isolated registry | 45 | 0 | 0 |
| Total | 250 | 0 | 0 |

The current combined run found and passed 205 cases. The 45 historical tests ran separately
under config.settings.historical_tests, with ITW_ISOLATED_TESTS=1 and its required database name.
This preserves the 218-test baseline without reversing committed forward-only migrations.

New cases cover anonymous/forged/unsaved/inactive actors, uncached current grants, direct/group
permission checks, explicit superuser denial, evidence separation, uploader/creator/current and
inherited contributor rejection, exact historical preflight replay, actor/payload conflicts,
expected versions, malformed/bounded requests, sanitized errors, rollback and disabled writes.
A real two-connection concurrency test observes the advisory-lock waiter in pg_locks and confirms
that the waiting service sees the committed current version and rejects its stale request.

The SQL proof uses an actual separate nonsuperuser LOGIN connection (not SET ROLE from a
superuser session). It verifies denied direct review DML, evidence SELECT, TRUNCATE, trigger
disablement, sequence use, private helper execution, role administration, schema CREATE,
procedure-owner assumption and writes to Asset/StockBalance/StockMovement/StockOperation.
It verifies explicit permission grant/revocation, ignored custom GUCs, fixed function search_path,
and the procedure owner's lack of inventory mutation privileges.
Existing tests additionally cover immutable participants, accidental nonowner DML grants,
hard-disabled approval/promotion and stock conservation guards.

Confirmed: fresh migration through inventory.0003 and transactions.0005 succeeded in the
disposable base database; makemigrations --check --dry-run reported No changes detected.
No new migration is present. Existing-file SHA-256 and Git whitespace checks are recorded in
the implementation report.

## Reproduction (Linux/WSL)

Use the existing it-warehouse-backend development image; no system Python installation.
Create a fresh uniquely named disposable database container with no persistent volume or published
ports. The test database names below are intentional safety guards.
Example setup from the repository root:

~~~sh
docker run -d --name it-warehouse-phase3b2b1-test-db --network bridge \
  --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=768m \
  -e POSTGRES_PASSWORD=phase3b2b1-isolated-test \
  -e POSTGRES_DB=phase3b2b1_test postgres:17-alpine
~~~

Wait for pg_isready. Run the backend image with these common arguments:

~~~sh
docker run --rm --network container:it-warehouse-phase3b2b1-test-db \
  --mount type=bind,source=/home/itadmin/projects/it-warehouse/backend,target=/app,readonly \
  -e PYTHONDONTWRITEBYTECODE=1 -e DJANGO_SECRET_KEY=phase3b2b1-test-only \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=phase3b2b1-isolated-test \
  -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_DB=phase3b2b1_test \
  it-warehouse-backend python manage.py test \
  config.tests apps.inventory.test_staging apps.transactions.test_engine \
  apps.inventory.test_review_schema apps.inventory.test_review_hardening \
  apps.inventory.test_review_services apps.inventory.test_review_gateway --noinput
~~~

For historical validation use the same common arguments but POSTGRES_DB=phase3b2a_history,
add -e ITW_ISOLATED_TESTS=1 before the image name, and replace the manage.py arguments with:

~~~sh
test apps.inventory.tests apps.transactions.tests --settings=config.settings.historical_tests --noinput
~~~

For fresh migration/drift validation use the current common arguments and respectively
`migrate --noinput` and `makemigrations --check --dry-run`.
Stop only this disposable container after validation. Never substitute the compose database,
mount a persistent database volume or reverse inventory.0002/0003.

## Evidence limits

Passing tests demonstrate the tested read-only privilege envelope and application checks.
They do not certify a writable gateway, human attestation, concurrent grant/master changes,
production role provisioning, verified source capture or business-valid review snapshots.
No test signs an approval, enables revocation, promotes inventory or processes original candidates.
