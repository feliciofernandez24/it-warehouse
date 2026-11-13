# Phase 3B.1 operations runbook

## Preconditions

Run these commands in a Linux/WSL shell as the repository operator. They assume the existing it-warehouse-backend image and postgres:17-alpine are available locally. Do not use the development database for tests. No dependencies are installed into system Python.

    cd /home/itadmin/projects/it-warehouse
    git branch --show-current
    git status --short
    sha256sum imports/IT_Warehouse_Asset_Inventory.xlsx

Expected branch: develop. Expected workbook SHA-256:

    d0c48893cc095696ada206fb4d61d80c2745d412b289e0ab754dc5bd023bc525

A mismatch stops execution. Do not bypass hash/profile checks, edit source cells or substitute guessed inventory.

## Offline dry run

The container cannot contact any database or network service. Backend/workbook mounts are read-only, the filesystem is read-only, and the only writable ephemeral path is /tmp. Configuration values here are dummy offline settings, not deployment credentials.

    docker run --rm --network none --user 1000:1000 --read-only \
      --mount type=bind,source=/home/itadmin/projects/it-warehouse/backend,target=/app,readonly \
      --mount type=bind,source=/home/itadmin/projects/it-warehouse/imports,target=/source,readonly \
      --tmpfs /tmp -e PYTHONDONTWRITEBYTECODE=1 \
      -e DJANGO_SECRET_KEY=staging-offline-only -e POSTGRES_PASSWORD=unused \
      it-warehouse-backend python manage.py stage_inventory \
      /source/IT_Warehouse_Asset_Inventory.xlsx

Exit 0 means capture/validation/normalization completed, not that stock is import-ready. Rows may still be blocked or need clarification. Output contains sanitized counts only. There are no validate-versus-preview posting modes: this one command always validates and prepares a dry-run preview.

## Private persistent capture

Provision the dedicated root as its actual owner. The verified operator UID/GID for this workspace is 1000:1000; adjust both container user and directory ownership if deploying elsewhere. Do not run capture as root or relax permissions to make it work.

    install -d -m 700 /home/itadmin/.local/share/it-warehouse-staging
    docker run --rm --network none --user 1000:1000 --read-only \
      --mount type=bind,source=/home/itadmin/projects/it-warehouse/backend,target=/app,readonly \
      --mount type=bind,source=/home/itadmin/projects/it-warehouse/imports,target=/source,readonly \
      --mount type=bind,source=/home/itadmin/.local/share/it-warehouse-staging,target=/private \
      --tmpfs /tmp -e PYTHONDONTWRITEBYTECODE=1 \
      -e DJANGO_SECRET_KEY=staging-offline-only -e POSTGRES_PASSWORD=unused \
      it-warehouse-backend python manage.py stage_inventory \
      /source/IT_Warehouse_Asset_Inventory.xlsx --capture-root /private

This is the real capture command executed in validation. It writes a content-addressed .json file in private storage, never in imports/docs/Git. Repeating it with identical source/rules/runtime verifies the existing artifact. No filename/digest/private content is printed.

An authorized operator can inspect the JSON within restricted storage. It contains a full manifest, row proposals/issues and deterministic digests, plus approval_enabled=false and posting_enabled=false. Never redirect this full JSON to a repository path, attach it to an issue, or export it to a public viewer.

## Isolated PostgreSQL tests

Use the dedicated name only if absent. If it already exists, inspect its ownership/configuration rather than resetting another container. This dedicated container was created for Phase 3B.1, then stopped after validation; starting that known container is safe. It uses tmpfs and no persistent development volume.

    docker run -d --name it-warehouse-phase3b1-test-db \
      --network bridge --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=512m \
      -e POSTGRES_PASSWORD=phase3b1-isolated-test \
      -e POSTGRES_DB=phase3b1_test postgres:17-alpine
    docker exec it-warehouse-phase3b1-test-db pg_isready -U postgres

Run the full suite only after pg_isready succeeds:

    docker run --rm --network container:it-warehouse-phase3b1-test-db \
      --mount type=bind,source=/home/itadmin/projects/it-warehouse/backend,target=/app,readonly \
      --tmpfs /tmp -e PYTHONDONTWRITEBYTECODE=1 \
      -e DJANGO_SECRET_KEY=phase3b1-isolated-tests-only \
      -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=phase3b1-isolated-test \
      -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_DB=phase3b1_test \
      it-warehouse-backend python manage.py test --noinput --verbosity 1

For focused tests, append apps.inventory.test_staging after test. For a read-only schema drift check, replace the final management command with:

    python manage.py makemigrations --check --dry-run

These test credentials are disposable, not development secrets. Test initialization applies migrations only to Django's newly created isolated test database. Do not run migrate against development. There are no new migrations in this phase.

After testing, stop only this dedicated container:

    docker stop it-warehouse-phase3b1-test-db

Do not reset/remove volumes or change development containers. The original 105 tests and 37 new tests passed together as 142 tests.

## Recovery

HASH_MISMATCH, UNKNOWN_WORKSHEETS, UNKNOWN_SECTION, MISSING_SECTION or RECONCILIATION_MISMATCH means source/layout drift: stop and obtain a reviewed authoritative version/profile. Do not loosen counts or reinterpret columns automatically.

INVALID_ARCHIVE, UNSAFE_XML, UNSAFE_RELATIONSHIP, UNSUPPORTED_MEMBER and resource-limit errors stop before publication. Keep the source unchanged; investigate in restricted access and add only a narrowly reviewed supported structure.

Storage errors fail closed. Verify private root ownership/mode, symlinks and repository boundary. Never chmod a conflicting artifact to make it acceptable or overwrite its bytes. Preserve suspicious artifacts for restricted investigation, then use a separately provisioned private root if necessary. An interrupted pre-publication write may leave a .capture-* file; after confirming no writer is active, the operator may archive/remove only that incomplete temporary file. Do not delete completed source evidence.

Preview cannot approve, exclude, resolve evidence, create masters or fix physical facts. Corrected normalization rules require a version change, focused tests and a new preview. Keep old captures: a new digest is a new preparation artifact, not permission to replace source history.

## Decisions before Phase 3B.2

Owner approval is still needed for taxonomy, vendor aliases, SKU/product groupings, tracking (especially fans/modules/tools), quantity-one evidence, package contents/base units, condition/status meanings, physical site/rack mapping, missing-serial acceptance and dimension conversions. Physical checks remain necessary for duplicate/part-like identities, package quantities, placement conflicts, inconsistent specs, handover/custody and future-date evidence.

Authenticated preparer/reviewer identity, exclusion decisions, immutable approved revisions, source consumption and import-aware guards remain unimplemented. This phase deliberately stops with unresolved proposals and unchanged Phase 2C posting protections.
