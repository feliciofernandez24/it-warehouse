# Phase 3B.2D.4 final readiness

Date: 2026-11-16, Asia/Tokyo. Verified develop HEAD: ddea0f839bd49fdd5da94b39cbbb09caddcb2f71.

## Decision

**PREPARED for independent review and a separately authorized schema-only persistent development migration. Execution is NOT authorized or performed by this phase.**

The guarded sequence has been rehearsed on PostgreSQL 17.11 restored from the supplied archive, including a fresh disposable-source backup and independent restoration with owner/ACL/role/history/data checks. The exact strengthened migration sequence succeeded again on a second new restored target. Recovery tests distinguish separately atomic migrations, partial installation and ambiguous outcomes.

| Work | Decision |
| --- | --- |
| Inactive inventory.0002 + .0003 installation | PREPARED, conditional on later authorization and all window gates |
| Immediate development execution | NO-GO: this task is preparation only; approval template remains unsigned |
| Restricted runtime activation | NO-GO: final role/secret/configuration cutover and supported admin routing remain separate work |
| Operational review gateway | NO-GO: independent human identity/scope administration behind shared Django LOGIN remains unresolved |
| Secure inventory capture | NO-GO: uploader authentication, verification/byte binding, artifact lifecycle and operational gateway remain unimplemented |

## Verified prerequisites and remaining window blockers

Verified now: correct actual HEAD and unchanged immutable migration hashes; PostgreSQL 17.11; database/user/container/volume identities; original inventory.0001 and transactions through .0005; source owner/ACL/default ACL/membership inventory; sufficient observed filesystem capacity; historical archive checksum and restoration; strict two-migration dependency plan; owner-context service compatibility; inactive workflows.

Still required before execution:
- Separate deployment authorization and private approval binding reviewed script hashes, HEAD and target ID.
- Explicit written acceptance that the current Django LOGIN is a **SUPERUSER** as well as owner (CREATEDB, CREATEROLE, BYPASSRLS). Owner-only guards cannot isolate against it. If this risk is unacceptable, keep application services offline and defer their activation.
- Exclusive Docker/host administrative control, complete worker/scheduler inventory, no unrelated DB dependents, and current session/writer census. Preparation's empty census is not lasting exclusion.
- Fresh maintenance-window backup and matching independently restored proof; historical archive success is not a fresh development recovery point.
- Adequate host memory/tmpfs recovery capacity as well as disk space; re-review if database/roles/extensions/topology/images/source change.
- Operator available for forward-only recovery; separately approved durable new-target recovery design/secrets if an availability incident requires it.

These are deployment gates, not requests to bypass security controls. No runtime role, production credential or accepted approval was created.

## Rehearsal and source preservation

Historical archive: ~/it-warehouse-db-backups/it_warehouse_pre_review_migration_20261114_111141.dump, 203233 bytes, mode 0600.

SHA-256: `2dfe16325d081973a41d246a065c631dc54560d459419d411fd820f057f97697`.

Both exact-order runs used new tmpfs clusters with the actual superuser it_warehouse owner attributes, no persistent data volume and no published ports. Sequence: audit → isolate → backup → restore-check → apply → verify → resume. Each stage passed. External bridge connection denial and retained local administration were separately verified. Original running/stopped mock states were preserved, including the safe pre-migration-abort path.

29 original tables contained 165 original rows. Every original row/key was compared through server-side SHA-256 without printing raw records. Expected additions were only five permissions, five content types and two migration rows (177 rows total). The five new review tables remained empty. All original owners/ACLs/sequence state (apart from expected metadata sequences) and stock function/trigger definitions were preserved.

Verified schema: five empty tables, 63 validated constraints, two valid partial indexes, 11 owner-only invoker review functions, 18 enabled review triggers including four deferred final checks. No operational proof/capture schema or HTTP endpoint was installed.

Role/ACL restoration retained source role flags/membership and table/sequence/database/schema/default ACL/extension ownership metadata. Only the independent restore_admin was additional. Passwords, HBA/server files and WAL/PITR are outside this logical proof.

## Regression and smoke results

Each final suite is reported separately. No aggregate unique total is claimed.

| Suite / context | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
| Existing current Django regression | 205 | 0 | 0 | 0 |
| Existing historical isolated registry | 45 | 0 | 0 | 0 |
| Existing restricted metadata-read gateway proof | 20 | 0 | 0 | 0 |
| Existing restricted runtime / stock / review suite | 16 | 0 | 0 | 0 |
| Existing owner-context application/stock/audit smokes | 8 | 0 | 0 | 0 |
| New D.4 failure/recovery integration methods | 8 | 0 | 0 | 0 |

The eight owner smokes reuse eight methods in the 16-method runtime suite under a different credential context; do not count them as new unique tests. Their final rerun with exact disposable-cluster checking passed. The existing 205+45 baseline is preserved. Historical capture-feasibility cases and the D.3 eight schema unittest methods were not rerun; they are neither claimed passed nor counted skipped here.

Owner smokes cover login/password upgrade/last_login/session update/logout/admin/health, bulk and serialized stock operations, replay/conflict, explicit capability denial, conservation, orphan-operation and immutable-posted-operation guards, and audit freeze. Fixtures/stock writes were disposable only. Final read-only health/admin routing and disabled-action/catalog checks passed on the clean migrated final twin. makemigrations --check --dry-run reported No changes detected.

The eight new methods cover six default-denied development mutation actions, empty/failed dumps, row tampering, owner/ACL/role drift, complete-outcome read verification, truncated archives, real 0003 lock-timeout rollback after committed 0002, partial-state retry refusal, and recovery into a new target. Subtests/assertions are not extra test counts.

The final backup-gate refinement additionally passed a valid retained proof and rejected separate archive, role-manifest and before-manifest tampering in temporary copies. All new Python files compiled successfully. These assertions made no database connection.

Manual stages/probes are not counted as unittest methods. Complete host/daemon failure, durable recovery cutover and post-cutover write reconciliation were documented, not fault-injected.

## Exact files added

No existing tracked file was modified.

- docs/phase3b2d4-predeployment-review.md
- docs/phase3b2d4-maintenance-and-backup.md
- docs/phase3b2d4-migration-runbook.md
- docs/phase3b2d4-recovery-runbook.md
- docs/phase3b2d4-final-readiness.md
- deployment/phase3b2d4/README.md
- deployment/phase3b2d4/approval.template.json
- deployment/phase3b2d4/development.json
- deployment/phase3b2d4/runbook.py
- deployment/phase3b2d4/dbcheck.py
- deployment/phase3b2d4/rehearse.py
- deployment/phase3b2d4/regressions.py
- deployment/phase3b2d4/failure_tests.py
- deployment/phase3b2d4/owner_smokes.py
- deployment/phase3b2d4/isolation_probe.py
- deployment/phase3b2d4/final_checks.py
- deployment/phase3b2d4/cleanup.py

[Migration runbook](phase3b2d4-migration-runbook.md) contains the exact future guarded commands, executed-command ledger and owner-smoke invocation. The isolated runners contain the exact subprocess commands for reproducible creation/restore/tests/failure injection. [Recovery runbook](phase3b2d4-recovery-runbook.md) separates A–F outcomes and the limits of executable recovery.

## Final preservation and cleanup

The final read-only comparison matched development original rows, role/membership metadata, ACLs, stock guards, sequences and migration history to the initial private audit. Inventory remains 0001 only. The container ID, persistent named-volume mounts and original networking matched; backend/frontend remained stopped.

Cleanup verified creation labels and explicit target names, then removed only the twelve D.4-created rehearsal containers, their exclusively attached anonymous mock-service volumes and two D.4-created networks. Development DB/container/volume, application containers and unrelated juice-shop were retained. Private evidence remains outside the repository under ~/.local/share/it-warehouse-d4/.

No persistent maintenance, database writes/DDL, role/ACL/credential/history changes, historical migration modifications, inventory.0004, workbook processing, operational capture/review/approval/revocation/promotion, commit or push occurred.
