# Phase 2C validation evidence

Date: 2026-11-13, Asia/Tokyo. Tests use real Django 5.2.19/Python 3.13 and PostgreSQL 17.11, not SQLite. All inventory fixtures are confined to Django's test_it_warehouse on an isolated memory-backed PostgreSQL container. No live stock, production inventory or permanent role grants are created.

## Executed evidence

- First 50 current-schema tests: PASS (17.000 seconds).
- Expanded full suite: 103 tests PASS (20.353 seconds); zero failures/errors/skips.
- Final suite/check results are recorded below after the final security changes.

Coverage includes serialized receipt/issue/return/transfer/loss/disposal, duplicate/terminal issue rejection, recipient/current custody and history, missing/duplicate serials and immutable tags; bulk receipt/issue/return/transfer/quarantine/adjustment/disposal; bucket identity, zero/invalid quantities, unavailable stock, insufficient stock and no serialized bulk assignments; immutable headers/approval/ledger, identical/changed retries, extra-line rejection, exact approved payload, current approver permissions, self-approval and superuser-without-grants rejection; atomic multiline success/failure, reconciliation and direct balance/asset mutation rejection; active audit parent/descendant scope, no-descendant scope, overlap, hierarchy freeze and immutable evidence.

TransactionTestCase uses separate connections and synchronized worker starts for competing withdrawals, serialized issues, identical retries, cumulative return limits, and simultaneous audit activation/posting. Assertions verify committed quantities, assignment count, request/result identity and ledger reconciliation; thread connections are closed. The shared writer lock serializes competing calls; insufficient/duplicate requests roll back. Non-owner role tests exercise real invoker triggers and denied DDL/TRUNCATE/trigger disable.

The original 43 inventory schema tests and two schema concurrency tests are explicitly historical Phase 2B contracts. In the isolated test database only, their class setup removes the new guards and reverts the reclassification CHECK, retaining the empty operation-header table for current ORM relationship compatibility. Class teardown restores all migrations. Those tests intentionally demonstrate Phase 2B clean-only gaps and direct-write fixtures; they are not cited as current-schema protection tests. 59 separate current-schema tests validate Phase 2C with guards enabled. No production/runtime code disables triggers. The existing health unit test is retained.

## Environment limitations

The pre-existing development PostgreSQL rejects the configured password. No credentials were reset. A dedicated it-warehouse-phase2c-test-db container, postgres:17-alpine, uses tmpfs data and no persistent warehouse volume. Runtime checks/migrations on that disposable database are reported separately from development. Existing DB/backend containers were started; no frontend/unrelated container or existing PostgreSQL volume was reset.

The HTTP health view is process liveness only. Django runserver currently fails its startup database check, so its HTTP port refuses connections; the passing unit health test does not prove development Compose health. See final recorded outputs and runbook. Never mark an unexecuted or blocked development migration/health check as passed.

## Final verification results

| Check | Result |
| --- | --- |
| Django system checks | PASS: no issues |
| makemigrations --check --dry-run | PASS: no changes detected |
| Full PostgreSQL suite after function hardening | PASS: 105 tests, 21.223 seconds, no failures/errors/skips |
| Fresh disposable-schema migrate | PASS: all migrations through transactions.0005 applied |
| Disposable migrate --check | PASS: exit 0 |
| Disposable reconcile_stock | PASS: ledger/balances/positions/custody reconcile |
| SQL review | 0003 creates header/constraints; 0004 adds guards and search paths with fail-closed preflight; 0005 atomically replaces one CHECK; no stock DML or table deletion |
| Development migrate --check | BLOCKED: configured password rejected; no development migrations applied |
| Compose health | Existing db healthy; existing backend unhealthy due startup database authentication; HTTP connection refused |
| Git whitespace check | PASS |

Final statement-lock validation: all 105 tests passed in 22.336 seconds. A second fresh database test_phase2c_validation successfully applied the final SQL through 0005; migrate --check, migration drift and reconciliation passed again. The disposable test container is stopped after validation. Persistent development data, credentials, role privileges, remote and branch are unchanged.

## Changed-file inventory

Created transactions/services/{__init__,posting,permissions,exceptions,custody,audits}.py; management command packages with provision_stock_roles.py and reconcile_stock.py; migrations 0003_stockoperation.py, 0004_posting_guards.py, 0005_serialized_reclassification.py; test_engine.py; database/phase2c-runtime-role.sql.example; and the four phase2c-*.md documents.

Modified transactions/models.py; inventory/tests.py and transactions/tests.py (historical migration test setup/restore); docs/database-architecture.md, docs/database-erd.md and docs/phase2-implementation-plan.md. No existing migration, settings, Compose configuration, credential file, frontend, API or Git remote was changed.
