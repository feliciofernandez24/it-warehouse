# Phase 3B.2D.2 security validation

Date: 2026-11-14. Branch develop, HEAD 922e84c. All new database work used disposable PostgreSQL 17.11 and synthetic fixtures only. No original workbook, backup contents or persistent development database was accessed.

## Actual final suite counts

| Suite invocation | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
| Current existing Django regression | 205 | 0 | 0 | 0 |
| Historical isolated registry | 45 | 0 | 0 | 0 |
| New read-gateway security proof | 20 | 0 | 0 | 0 |
| Existing runtime-role tests on synthetic compatibility clone | 16 | 0 | 0 | 0 |

Final nonduplicated invocations total 286 successful test-method executions. The manual shared-runtime identity-denial probe is additional evidence, not another counted test. Do not add earlier attempts or historical totals to this number.

The earlier 284-case baseline comprised 205 current +45 historical +34 capture-feasibility cases. The 34 capture/Ed25519 feasibility tests were NOT RERUN here, not counted as skipped. Their files/results remain unchanged. Likewise the earlier 46 runtime executions represented 18 methods across configurations; this phase reran only the 12 RuntimeTests +4 ReviewTests once in the final successful compatibility invocation. The earlier two write-gateway compatibility methods were not rerun, and no capture proof was enabled by this phase.

Fresh migrate through inventory.0003 and transactions.0005 succeeded in the disposable base; makemigrations --check --dry-run reported No changes detected. Git diff shows no tracked-file modifications, including historical migrations and Phase 2C service/guard source.

## New security proof coverage

Twenty methods establish:

- Scoped diagnostic metadata, exact B.1 canonical fingerprint equivalence including a Unicode payload.
- No mapped identity for shared runtime, and adapter failure before SQL by default.
- Ignored actor GUCs; no owner/other-login role assumption.
- Same ACCESS_DENIED for inaccessible and missing revisions; foreign event/actor denial.
- Uploader/creator/contributor rejection, inactive-user denial and no implicit superuser capability.
- Fresh direct/group grants and membership/permission revocations.
- Malformed UUID/version/payload/digest denial and fixed sanitized adapter responses.
- Denied direct review/source/auth/stock SELECT/DML, protected TRUNCATE/ALTER/trigger disablement, schema/temp creation, sequence use and private helper calls.
- Definer selected-column reads only: no broad event SELECT, draft/reason/details/source/snapshot access or table ownership/DML.
- Exact historical event metadata with current version/state; changed payload conflict; no confidential sentinel disclosure.
- Version/state checks, hard-disabled registration/approval/revocation/promotion, unsupported isolation denial.
- Two actual connections synchronized by an observed pg_locks advisory waiter during permission revocation, not timing-only sleeps.
- Unchanged review row counts and zero stock mutations by the read proof.

The definer's effective current_user differs from the caller's session_user; the proof deliberately trusts only the latter's administrator-installed principal binding. Synthetic LOGIN passwords are independently generated in memory and excluded from saved evidence.

## Existing runtime compatibility

runtime_regression.py creates a synthetic clone, reconstructs the prior NOLOGIN owner / separate migration LOGIN model and uses the untouched existing runtime harness/tests. Public table/function ownership adjustments occur only in that disposable clone; function bodies, guards and historical migrations are unchanged.

The actual stock/auth/session Django LOGIN receives its already tested narrow grants plus gateway EXECUTE. All 16 existing runtime methods pass: login/hash upgrade/session/logout, bulk and serialized operations, audit counting/freeze, explicit permission checks, conservation/operation/ledger safeguards, DDL/owner denials and direct-review isolation.

A separate raw Django SQL call confirms session_user=current_user=itw_django_rehearsal and returns IDENTITY_VERIFICATION_UNAVAILABLE. The original B.1 preflight still fails closed under no-evidence SELECT grants, as expected: there is no operational integration.

The first compatibility run's 16 methods passed but its additional manual assertion compared Django's raw JSONB text with a dict. The probe was corrected to decode JSON text, then rerun successfully. This was a probe-decoding defect, not an authorization bypass; only the final successful invocation is counted above.

## Role/ACL results and evidence

[Read proof evidence](phase3b2d2-read-proof-evidence.json) records selected column grants, role flags, function owner/security/search_path/ACL and unchanged row counts. [Runtime evidence](phase3b2d2-runtime-evidence.json) records final existing-suite counts, actual shared SQL identity/denial and stock runtime grant envelope.

No application table belongs to itw_read_poc_owner. It owns the two proof functions only, has selected metadata/registry SELECT, and no review/source/stock writes or sequences. Synthetic reader roles have CONNECT, private schema USAGE and exact inspect_v1 EXECUTE only, zero memberships. PUBLIC access to private functions/schema is revoked atomically; schema remains installer-owned.

The private scope/principal tables belong to the trusted installer and are not writable/readable by callers. They are a synthetic policy mechanism, not a production broker. Actual shared credentials deliberately have no mapping. No SQL path accepts actor_id or trusts custom GUCs as identity.

The test database used tmpfs at /var/lib/postgresql/data with a 768 MiB limit, no volume and no published ports. Client source was mounted read-only. Existing development and previous-test containers were not changed. Only the two new phase3b2d2 containers are stopped after evidence collection.

## Commands executed

Read-only inspection used Get-Content for the requested evidence, review modules/migrations, runtime harness/tests, compose.yaml and base.py; git status --short, branch --show-current, log -1 --oneline, find .. -name AGENTS.md, docker image ls and docker inspect for tmpfs/ports. New-file writes used explicit-path PowerShell .NET WriteAllText only; existing work was not overwritten.

The complete reproducible container commands are in [prototype README](../backend/feasibility_review_read/README.md). Principal executed commands were:

~~~sh
docker run -d --name it-warehouse-phase3b2d2-db --network bridge \
  --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=768m \
  -e POSTGRES_PASSWORD=phase3b2d2-synthetic-only -e POSTGRES_DB=phase3b2b1_test postgres:17-alpine
docker run -d --name it-warehouse-phase3b2d2-client \
  --network container:it-warehouse-phase3b2d2-db \
  --mount type=bind,source=/home/itadmin/projects/it-warehouse/backend,target=/app,readonly \
  -e PYTHONDONTWRITEBYTECODE=1 -e DJANGO_SECRET_KEY=phase3b2d2-synthetic-only \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=phase3b2d2-synthetic-only \
  -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_DB=phase3b2b1_test it-warehouse-backend sleep infinity

docker exec it-warehouse-phase3b2d2-client python manage.py test \
  config.tests apps.inventory.test_staging apps.transactions.test_engine \
  apps.inventory.test_review_schema apps.inventory.test_review_hardening \
  apps.inventory.test_review_services apps.inventory.test_review_gateway --noinput
docker exec -e POSTGRES_DB=phase3b2a_history -e ITW_ISOLATED_TESTS=1 \
  it-warehouse-phase3b2d2-client python manage.py test apps.inventory.tests apps.transactions.tests \
  --settings=config.settings.historical_tests --noinput
docker exec it-warehouse-phase3b2d2-client python manage.py migrate --noinput
docker exec -e ITW_REVIEW_READ_PROOF=1 it-warehouse-phase3b2d2-client python feasibility_review_read/run.py
docker exec -e ITW_REVIEW_READ_PROOF=1 it-warehouse-phase3b2d2-client python feasibility_review_read/runtime_regression.py
docker exec -e ITW_REVIEW_READ_PROOF=1 it-warehouse-phase3b2d2-client \
  python feasibility_review_read/runtime_regression.py --existing-clone
docker exec -e POSTGRES_PASSWORD=runtime-rehearsal-admin-only \
  it-warehouse-phase3b2d2-client python manage.py makemigrations --check --dry-run
~~~

The compatibility fixture internally creates a synthetic clone and roles, explicitly transfers its public test objects to the reconstructed owner, then changes only the disposable postgres password to the older harness's synthetic value. It performs no pg_restore, live-data read or persistent provisioning. --existing-clone was the JSON-probe troubleshooting rerun; on a fresh run the corrected script needs only its normal invocation.

Evidence was retrieved with docker exec ... cat /tmp/phase3b2d2-evidence.json and /tmp/phase3b2d2-runtime-evidence.json. Final Git/whitespace checks and docker stop it-warehouse-phase3b2d2-client it-warehouse-phase3b2d2-db complete the record. No command from the future persistent deployment plan was executed.

## Exact files added in this phase

- backend/feasibility_review_read/README.md
- backend/feasibility_review_read/gateway.sql
- backend/feasibility_review_read/adapter.py
- backend/feasibility_review_read/run.py
- backend/feasibility_review_read/tests.py
- backend/feasibility_review_read/runtime_regression.py
- docs/phase3b2d2-review-read-gateway.md
- docs/phase3b2d2-role-and-migration-deployment-plan.md
- docs/phase3b2d2-security-validation.md
- docs/phase3b2d2-readiness-decision.md
- docs/phase3b2d2-read-proof-evidence.json
- docs/phase3b2d2-runtime-evidence.json

All prior backend/feasibility_runtime files and runtime-role documentation/evidence remain unmodified and uncommitted. No operational module, existing migration, .env, Compose file, stock guard/service, production deployment script or inventory.0004 changed. No commit/push occurred.