# Phase 2C operations runbook

Run commands from /home/itadmin/projects/it-warehouse inside WSL. Do not commit/push automatically. No APIs, Excel migration or frontend work is part of this phase.

## Deployment prerequisites

1. Repair the configured development database authentication through the approved credential-management process; do not reset its volume or change passwords to make tests pass.
2. Review the SQL from sqlmigrate for 0003, 0004 and 0005. Back up a populated deployment and rehearse on a disposable restore. 0004 intentionally refuses existing assets/movements/nonzero balances/active audits; arrange a reviewed opening-ledger cutover rather than bypassing that check.
3. Review database/phase2c-runtime-role.sql.example, owner/function/search_path/EXECUTE/public schema privileges and separate runtime/migration logins. Do not run runtime with the inspected development superuser credentials.
4. Run migrations using the deployment owner, then provision groups and explicitly review user membership. No stock fixtures belong in development.

```sh
docker compose exec -T backend python manage.py check
docker compose exec -T backend python manage.py makemigrations --check --dry-run
docker compose exec -T backend python manage.py sqlmigrate transactions 0003
docker compose exec -T backend python manage.py sqlmigrate transactions 0004
docker compose exec -T backend python manage.py sqlmigrate transactions 0005
# After SQL, backup, credential and role review:
docker compose exec -T backend python manage.py migrate
docker compose exec -T backend python manage.py migrate --check
docker compose exec -T backend python manage.py provision_stock_roles
docker compose exec -T backend python manage.py reconcile_stock
docker compose exec -T backend python manage.py test --noinput --verbosity 2
docker compose ps
docker compose exec -T backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health/').read().decode())"
```

## Disposable PostgreSQL verification

No port is published and no existing volume is mounted. The password here is a disposable test-only value.

```sh
docker run -d --rm --name it-warehouse-phase2c-test-db \
  --network it-warehouse_default --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_USER=it_warehouse -e POSTGRES_DB=it_warehouse \
  -e POSTGRES_PASSWORD=phase2c-test-only postgres:17-alpine
# Wait for pg_isready before invoking Django.
docker exec it-warehouse-phase2c-test-db pg_isready -U it_warehouse
# Repeat this environment prefix for check, migration drift, migrate --check and reconciliation.
docker compose exec -T -e POSTGRES_HOST=it-warehouse-phase2c-test-db \
  -e POSTGRES_PASSWORD=phase2c-test-only backend python manage.py test --noinput --verbosity 2
# Stop only this disposable test container after verification; --rm deletes its tmpfs data.
docker stop it-warehouse-phase2c-test-db
```

Django creates/destroys test_it_warehouse. It may replace a leftover test database after a failed test setup when --noinput is used. Never override the test database name to a real warehouse database.

## Recovery and reconciliation

Retry a timed-out request with its original operation key and exact payload. If committed, the result IDs are reused; if rolled back, posting can run again. A mismatched payload requires a new key and, where required, a new independent approval. Do not edit the header or ledger. Deferred guard/constraint errors roll back the whole operation. Log the rejected request key and error without exposing recipient private data.

Use reconcile_stock to compare every bucket with ledger credits minus debits and every asset with its latest movement/current custody. A mismatch raises CommandError and must stop operational posting for investigation. Never fix a mismatch by changing balances or deleting movements. Preserve evidence and diagnose the failing operation; post a separately approved corrective entry only when the underlying state is coherent. Restore backups only through a separately reviewed recovery procedure, preserving forensic records and preventing duplicate external effects.

Returns reference original issues and custody episodes; reversals cannot exceed the original unreversed quantity. For a transfer reversal, swap physical endpoints and source/destination bucket conditions/states, identify the original movement in reverses_id, and use a new key. Receipt reversal uses approved ADJUSTMENT_OUT; terminal serialized recovery is intentionally unsupported. No destructive automatic rollback or schema downgrade is an operational recovery tool.

COUNTING/SUBMITTED audit scopes block posting. Do not mutate hierarchy to evade a freeze or disable triggers. Submitted audits cannot be closed by this phase; full authorized reconciliation, cancellation/submission workflows, excess-line discovery and approval completeness review remain to be implemented. Use the counting foundation only in rehearsals until the closing workflow is available.
