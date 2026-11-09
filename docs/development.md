# Phase 1 development

Run commands in Kali Linux WSL2 from `/home/itadmin/projects/it-warehouse`.
Keep the checkout in the Linux filesystem. Enable Docker Desktop WSL integration
for Kali, or use a working Docker Engine and Compose inside WSL.
Docker supplies Python 3.13, Node.js 24, and PostgreSQL 17.

## Start

```sh
cp .env.example .env
docker compose config --quiet
docker compose build
docker compose up -d db
docker compose run --rm backend python manage.py migrate
docker compose up -d
```

React: http://localhost:5173
Django: http://localhost:8000
Health: http://localhost:8000/api/health/
Admin: http://localhost:8000/admin/

The health route checks application liveness, not database connectivity.
PostgreSQL is available only to containers as `db:5432`.
Published app ports bind to localhost. This is development configuration;
Django runserver and Vite must not be used for production hosting.
The example credentials are for local development only.

```sh
docker compose exec backend python manage.py createsuperuser
docker compose logs -f
docker compose down
```

`down` retains database data. Source bind mounts support hot reload.
After changing frontend dependencies, run `docker compose run --rm frontend npm ci`
and rebuild the frontend image to refresh its named dependency volume.
Do not commit `.env`, credentials, database exports, or warehouse import files.

## Validation

```sh
docker compose config --quiet
docker compose run --rm backend python manage.py check
docker compose run --rm backend python manage.py makemigrations --check --dry-run
docker compose run --rm backend python manage.py test
docker compose run --rm frontend npm run build
curl -f http://localhost:8000/api/health/
curl -f http://localhost:5173/api/health/
```

## Structure

- `backend/config/settings/`: shared settings and development configuration
- `backend/apps/`: accounts, inventory, warehouse, transactions, audits, reports
- `frontend/`: React and Vite shell
- `database/`: database documentation and future supporting files
- `imports/`: reserved, ignored input area; no Excel data imported
- `nginx/`: reserved for future reverse proxy configuration
- `docs/`: setup and validation documentation

The six apps contain empty model and migration modules. Django's default user
model is retained for this scaffold; decide on a custom user model before adding
account features and applying migrations to a shared environment.
No inventory behavior, asset schema, import pipeline, or production deployment
configuration is implemented.
