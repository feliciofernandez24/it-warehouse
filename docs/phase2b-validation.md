# Phase 2B schema validation

Validated on 2026-11-09 on develop, using the existing local development Compose stack. No Phase 2C posting services were implemented.

## Results

| Check | Result |
| --- | --- |
| Runtime | Django 5.2.19, Python 3.13, PostgreSQL 17.11 |
| Django system check | No issues |
| makemigrations --check --dry-run | No changes detected |
| migrate --check and graph leaf plan | No unapplied migrations |
| Fresh-schema test migration | All framework and new migrations applied in isolated test database |
| Automated tests | 46 passed; 0 failures, errors or skips |
| Real transaction tests | Competing open assignments: one commit, one rejection; failed multi-write transaction rolls back |
| Business tables | 18 created; all verified empty in development |
| Model Meta constraints | All 102 named declarations found in live PostgreSQL catalog |
| Explicit model indexes | All 15 found; automatic PK/unique/FK indexes are additional |
| Schema triggers | 18 installed |
| Historical data | Existing users, groups, user/group permission memberships, sessions and admin rows unchanged by before/after fingerprints |
| Migration SQL review | Forward SQL additive only; no DROP, DELETE, TRUNCATE, INSERT, UPDATE or destructive ALTER statement |
| API health | Existing /api/health/ returns status ok |
| Existing configuration | README, .gitignore, Compose and base/development settings unchanged |
| Reports | No unnecessary table or migration |

Migrations create Django content types and permissions as normal post_migrate metadata; no users, recipient records, inventory, movements, audits or import rows were seeded. No production database or unrelated container was changed. Existing volumes retained; no frontend/API/import implementation, commit or push.

## Models and migrations

The [model reference](phase2b-model-reference.md) lists exact fields, FK targets, defaults, enums, constraints and indexes for every model. The [ERD](database-erd.md) shows AssetRecipient and assignment destination fields; [architecture](database-architecture.md) describes enforcement boundaries.

| Migration | Dependencies / purpose |
| --- | --- |
| accounts.0001_initial | Existing auth user; AssetRecipient |
| warehouse.0001_initial | Warehouse and location tree |
| inventory.0001_initial | Warehouse/auth; ten catalog/position/specification/staging models |
| audits.0001_initial | Inventory/warehouse/auth; audit, lines, change log |
| transactions.0001_initial | Accounts/audits/inventory/warehouse/auth; movement and recipient assignment |
| transactions.0002_schema_guards | Initial transaction/inventory/audit schemas; reversible trigger functions |

No cycle: StockMovement owns links to AuditLine and ImportStagingRecord; neither owns a reciprocal movement FK. Full inspected forward SQL is in [migration SQL](phase2b-migration-sql.md). Guard reverse SQL is supplied in the migration; it was not applied to development. No destructive schema rollback was performed.

## Automated test scope

43 schema tests in apps.inventory.tests, two PostgreSQL TransactionTestCase tests in apps.transactions.tests, and the existing health test in config.tests, for 46 total.

Tests cover:
- Valid recipient identities without logins and optional person-only unique account links.
- Unique generated tags, DB tag/catalog immutability, missing and duplicate serials with retained raw text.
- Serialized/bulk relationship triggers, referenced tracking immutability, quantity/measurement/unit constraints and immutable buckets.
- Valid racks/standalone areas, location uniqueness/root/self rules and clean()-only parent/cycle rules.
- Specification owner XOR, one typed value, owner uniqueness and clean()-only definition matching.
- Movement direction/target/quantity/retry-line uniqueness, endpoint validation and no-op transfers.
- Open assignment uniqueness, ordered return evidence, matching issue validation, immutable recipient/destination and closed episode history.
- Audit header approval/date evidence, line quantities/target/evidence/uniques and excess buckets at distinct locations.
- Source worksheet/row uniqueness, promotion target/time and batch reviewer/preview evidence.
- PROTECT on masters/users/recipients; deletion guards on all seven history/provenance tables and immutable movement/change-log updates.
- Real PostgreSQL indexes, partial unique predicates, NULLS NOT DISTINCT, installed triggers and timezone-aware timestamps.
- Explicit contract tests proving selected clean()-only invariants can still be bypassed by direct ORM writes in the isolated test database.

The test database test_it_warehouse was created and destroyed by Django; no fixtures were written into development. These tests validate schema behavior, not posting services.

## Remaining Phase 2C invariants

Not yet database/service-enforced:
- Ledger conservation, atomic posting, live quantity/asset position updates, complete custody/lifecycle agreement, reversal quantity limits and whole-operation payload idempotency.
- Race-safe hierarchy ancestry, cross-warehouse parent rules, occupancy/deactivation and audit movement freezes.
- Cross-row specification type, movement bucket matching and assignment movement actor/type/time matching (helpful clean() checks only).
- Approved audit/staging snapshot and raw-capture update immutability, audit completeness/outcome derivation, batch source duplicate prevention and target/opening movement coherence.
- Runtime posting-only privilege boundary, group provisioning, action authorization, warehouse access scopes and full approval workflows.

save() does not call full_clean(); raw SQL/bulk ORM bypass clean(). Database CHECK/UNIQUE/FK and installed triggers still apply. Trigger DELETE guards do not protect against database owners disabling triggers or TRUNCATE.

Decisions before Phase 2C: recipient matching/privacy, measurement units beyond pieces, audit freeze/staffing, restricted database roles, retention and reversal/cutover policy. AssetRecipient support resolves the previous assumption that every assignee needs a login.

## Repeatable checks

```sh
docker compose exec -T backend python manage.py check
docker compose exec -T backend python manage.py makemigrations --check --dry-run
docker compose exec -T backend python manage.py migrate --check
docker compose exec -T --user 1000:1000 backend python manage.py test --noinput --verbosity 2
```

The UID example matches this WSL workspace owner. Tests require the configured local role to create an isolated test database. Migration inspection uses sqlmigrate before migrate, not merely migrate --plan.

Phase 2B complete. Phase 2C requires separate approval.
