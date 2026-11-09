# Database

PostgreSQL 17 runs as the Compose `db` service with a named volume.
There is no published database port. Use `docker compose exec db psql -U it_warehouse -d it_warehouse`.
Django migrations own schema changes. No initialization SQL or asset data is included.
