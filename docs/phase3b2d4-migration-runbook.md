# Phase 3B.2D.4 guarded migration runbook

**Prepared for independent review and later explicit authorization. No command in the development execution block was executed during preparation.** Scope: additive inactive schema only, inventory.0002 then .0003. No role transition, capture, review gateway or stock promotion.

## Gates before authorization

1. Review [predeployment findings](phase3b2d4-predeployment-review.md), including actual superuser privileges and stopped application state.
2. Reconfirm exclusive Docker-host control, all background writers stopped, no unrelated DB dependents, adequate disk/memory, correct commit/images/container/volume and no unexplained source changes.
3. Accept continued development superuser-owner risk in writing. Otherwise keep applications offline; do not claim restricted-runtime security.
4. Review every new D.4 file. Historical migration hashes must match. The unsigned approval template intentionally has null approver/hashes and false attestations. Preparation supplies no signed/accepted deployment approval.
5. If HEAD, image, source population, extension/role topology, service inventory or target identity changes, stop and re-review. Updating a pin is a review operation, not an automatic workaround.
6. Keep a separate authorized operator available for recovery. No concurrent migrations or privilege/DDL administration.

The host driver invokes SQL only through pinned one-off clients with explicit connection values and read-only mounts. It never reads .env. Local trust is used only within the verified DB namespace; no production password is provisioned.

## Exact future authorized execution

The following is a WSL Bash sequence. Every command must succeed before the next; no automation should continue after a nonzero exit. The preparation runner did NOT export this authorization variable or create an accepted approval.

~~~sh
set -euo pipefail
umask 077
cd /home/itadmin/projects/it-warehouse
git rev-parse HEAD
git status --short
git diff --exit-code
git diff --cached --exit-code
python3 deployment/phase3b2d4/runbook.py --help

install -d -m 700 /home/itadmin/it-warehouse-db-backups
d4_state=$(mktemp -d /home/itadmin/it-warehouse-db-backups/phase3b2d4_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX)
d4_approval="$d4_state/approval.json"
cp deployment/phase3b2d4/approval.template.json "$d4_approval"
chmod 600 "$d4_approval"
sha256sum deployment/phase3b2d4/runbook.py deployment/phase3b2d4/dbcheck.py
~~~

STOP here for the separately authorized operator to fill approver, exact HEAD/container ID, reviewed script hashes and four true attestations in the private approval file. Do not turn false flags true automatically. The JSON is a local change-control record protected by host permissions, not a cryptographic identity service.

Only after that authorization, in the same shell:

~~~sh
export ITW_D4_AUTHORIZE_PERSISTENT='ddea0f839bd49fdd5da94b39cbbb09caddcb2f71:06a763552cf644ecb68efa4873bb00b978c7a4970acc7586a8eacf3cec035c11'
d4_config=/home/itadmin/projects/it-warehouse/deployment/phase3b2d4/development.json
d4_runner=/home/itadmin/projects/it-warehouse/deployment/phase3b2d4/runbook.py
d4_restore="itw-d4-window-$(date -u +%Y%m%d%H%M%S)"

python3 "$d4_runner" audit --config "$d4_config" --state "$d4_state"
python3 "$d4_runner" isolate --config "$d4_config" --state "$d4_state" --execute-development --approval "$d4_approval"
python3 "$d4_runner" backup --config "$d4_config" --state "$d4_state" --execute-development --approval "$d4_approval"
python3 "$d4_runner" restore-check --config "$d4_config" --state "$d4_state" --restore-name "$d4_restore" --execute-development --approval "$d4_approval"
python3 "$d4_runner" apply --config "$d4_config" --state "$d4_state" --execute-development --approval "$d4_approval"
python3 "$d4_runner" verify --config "$d4_config" --state "$d4_state" --execute-development --approval "$d4_approval"
python3 "$d4_runner" resume --config "$d4_config" --state "$d4_state" --execute-development --approval "$d4_approval"
unset ITW_D4_AUTHORIZE_PERSISTENT
~~~

Do not run this block as an unattended paste: inspect each pass gate and retain the maintenance journal. The driver uses no `compose up/down` and cannot remove/recreate the DB or its volume. Baseline backend/frontend are stopped, so resume restores networking but starts neither. A later decision to activate them is separate authorization.

## What apply actually does

- Enforces flag + exact environment opt-in + private approval attestations/script hashes; default rejection occurs before maintenance or SQL writes. Rehearsal mode cannot target a named-volume DB.
- Checks actual HEAD/clean tracked diff and both immutable migration hashes; pinned container ID, database name, volume and images.
- Requires private state, same DB system identifier/mounts, no networks and zero other clients.
- Requires fresh nonempty backup, matching restore proof/before-manifest, and age under two hours.
- Rechecks inventory.0001 only, transactions through .0005, original source rows/ACLs/owners/sequences/roles/guards, expected extensions and no preexisting review objects.
- Computes targeted AND global pending plans through Django MigrationExecutor. Both must be exactly inventory.0002, inventory.0003. No other pending application migration is accepted.
- Runs `call_command("migrate","inventory","0002",interactive=False)`, then the corresponding 0003 call in the same maintenance process, each with its own atomic transaction. Lock timeout is 5 seconds and statement timeout 60 seconds. A timeout is a cancellation, not permission to disable guards.
- Does not fake migrations, seed profiles, configure gateways, process artifacts or call stock services.

## Verification and exit gates

Read-only verification requires:

| Gate | Expected result |
| --- | --- |
| History | inventory 0001,0002,0003; original history rows unchanged |
| Original source | all 165 original rows unchanged by server-side row/key SHA-256; no changes to original table ACL/owner or stock definitions |
| Controlled metadata additions | exactly +5 auth permissions, +5 content types, +2 migration rows; total rows 177 for this baseline |
| New tables | exactly five, empty, owner it_warehouse, no explicit broad ACL |
| Constraints/indexes | 63 validated records; two valid partial unique indexes |
| Functions | 11 review functions, invoker, owner it_warehouse, owner-only EXECUTE |
| Triggers | 18 enabled review triggers; four initially deferred final-state checks |
| Stock guards | original non-review function hashes and trigger definitions/states unchanged |
| Application smoke | read-only health 200, anonymous admin 302, only admin/health top-level routes; reserved APPROVE/REVOKE/PROMOTE raise ACTION_DISABLED |
| No operational installation | no proof/capture gateway schemas; no operational endpoint/source processing |

The helper snapshots PostgreSQL catalogs and source hashes inside read-only repeatable-read transactions. Hash manifests are confidential inspection evidence and remain outside Git. They do not represent canonical workbook digests.

The eight existing authentication/session/stock/audit smoke tests were executed on the disposable migrated restore under a real superuser it_warehouse LOGIN. They create only synthetic fixtures, with per-test stock operations rolled back. Do not execute that fixture runner in persistent development. The runtime verifier uses anonymous GETs/read-only checks, not login/logout or stock writes. A health response alone is not database readiness.

Resume re-verifies the migrated schema before reconnection, checks the same ID/mounts, reconnects recorded networks/IP/aliases and starts only originally running application IDs. If an IP is occupied, a container was recreated, verification fails or service start fails, stop and follow recovery; do not recreate the DB or blindly rerun a partially completed resume. Record every completed reconnect/start and inspect actual state.

## Reproduction and executed command ledger

All preparation commands ran from the repository using WSL `kali-linux`; host files were written with approved PowerShell WriteAllText. Meaningful executed commands:

~~~sh
git status --short
git rev-parse HEAD
# Read-only source: Get-Content of the six required reports, migrations,
# settings, compose.yaml, review modules and existing feasibility harnesses.
docker ps -a --format '{{.Names}} {{.Status}}'
# SELECT-only psql inspection with default_transaction_read_only=on:
# identity, role flags/memberships, owners/ACLs/default ACLs, history,
# counts, pg_stat_activity, pg_hba_file_rules, extensions and system ID.
sha256sum /home/itadmin/it-warehouse-db-backups/it_warehouse_pre_review_migration_20261114_111141.dump
df -Pk /home/itadmin/it-warehouse-db-backups
docker exec it-warehouse-db-1 df -Pk /var/lib/postgresql/data
python3 deployment/phase3b2d4/runbook.py audit --config deployment/phase3b2d4/development.json --state /home/itadmin/.local/share/it-warehouse-d4/preparation-audit
python3 deployment/phase3b2d4/rehearse.py
python3 deployment/phase3b2d4/regressions.py
python3 deployment/phase3b2d4/failure_tests.py
python3 deployment/phase3b2d4/rehearse.py --tag final
python3 deployment/phase3b2d4/isolation_probe.py
python3 deployment/phase3b2d4/final_checks.py
~~~

The exact Docker commands for creation, restore, backup, migrations, suites and failure injection are reproducible in those small scripts; none selects the persistent DB for writes. Private stage logs/manifests are under `~/.local/share/it-warehouse-d4/`. The owner smoke invocation was:

~~~sh
docker run --rm --network container:itw-d4-rehearsal-db \
  --mount type=bind,source=/home/itadmin/projects/it-warehouse/backend,target=/app,readonly \
  --mount type=bind,source=/home/itadmin/projects/it-warehouse/deployment/phase3b2d4,target=/runbook,readonly \
  -e PYTHONDONTWRITEBYTECODE=1 -e DJANGO_SECRET_KEY=d4-smokes-only \
  -e POSTGRES_HOST=127.0.0.1 -e POSTGRES_DB=it_warehouse \
  -e POSTGRES_USER=it_warehouse -e POSTGRES_PASSWORD=d4-disposable-only \
  -e ITW_D4_OWNER_SMOKES=DISPOSABLE_ONLY -e ITW_D4_EXPECT_CLUSTER=7708553989956337705 it-warehouse-backend python /runbook/owner_smokes.py
~~~

The expected-cluster value above is the recorded disposable system identifier, not the development identifier. For a new rehearsal independently inspect its new identifier; the runner rejects the known persistent identifier.

Six development mutation commands were deliberately invoked WITHOUT opt-in by failure_tests; all returned LATER_DEVELOPMENT_AUTHORIZATION_REQUIRED before database writes or isolation. One earlier no-opt-in apply probe did the same. Windows Git refused dubious ownership and was replaced by Linux Git without changing safe.directory. A host Docker-root df and a quoted WSL rg probe failed; corrected read-only commands were used. These were inspection troubleshooting, not database failures.

A final private check_backup_gate.py probe (run with PYTHONPATH pointing at deployment/phase3b2d4) validated the retained fresh proof, rejected three separately tampered temporary file copies and compiled every new Python file. It performed no database operation. The final apply gate rehashes archive, role metadata and before-manifest.

Only D.4-created labeled resources may be cleaned up; see cleanup.py. No existing container/network/volume is a cleanup target.
