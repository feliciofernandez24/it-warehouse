# D.4 preparation and isolated rehearsal

This directory is not an operational review/capture feature. Read the five docs/phase3b2d4-* reports first. Never point a fixture runner at development.

Files:
- runbook.py: host CLI; audit is read-only; other development actions require explicit flag, exact environment token and approved private attestations/script hashes.
- dbcheck.py: container-side read-only snapshots, strict migration-plan checking, gated two-migration execution and preservation/read-only application checks.
- development.json: nonsecret pinned target/image/HEAD metadata. Re-review after any drift.
- approval.template.json: intentionally unsigned and false; not deployment authorization.
- rehearse.py: creates a new named tmpfs PostgreSQL cluster, restores the historical archive and runs the complete sequence.
- regressions.py: runs existing current/historical/read/runtime suites in a separate synthetic tmpfs cluster.
- failure_tests.py: eight failure/recovery methods; requires the initial rehearsal evidence and unused failure/recovery target names.
- owner_smokes.py: eight existing methods under actual superuser-owner context, disposable only; rejects the known persistent cluster and requires an exact expected disposable system identifier.
- isolation_probe.py: final-twin network and pre-migration-abort assertions.
- final_checks.py: final disposable verification, read-only persistent preservation comparison and syntax validation.
- cleanup.py: cleanup for this recorded rehearsal's explicit names and creation labels, with exclusive anonymous-volume checks. Review names before using for a new tagged run.

Reproduce from WSL on an exclusively controlled test host with existing pinned images, source checkout and verified backup; names must be unused. Source mount is read-only, PostgreSQL data uses tmpfs, no published ports. About 1 GiB tmpfs maximum per DB; run sequentially with sufficient host memory.

~~~sh
export PYTHONDONTWRITEBYTECODE=1
python3 deployment/phase3b2d4/rehearse.py
python3 deployment/phase3b2d4/regressions.py
python3 deployment/phase3b2d4/failure_tests.py
python3 deployment/phase3b2d4/rehearse.py --tag final
python3 deployment/phase3b2d4/isolation_probe.py
~~~

The owner-smoke Docker invocation is recorded in the migration runbook. Set ITW_D4_EXPECT_CLUSTER to the selected disposable DB's independently inspected system identifier. Do not use a real credential. final_checks.py additionally expects the private preparation-audit manifest captured by the read-only development audit; it is environment-specific evidence validation, not a portable baseline fixture.

The default rehearsal uses the directory ~/.local/share/it-warehouse-d4/rehearsal. Final uses .../final. These private manifests/logs must not be committed. Failure tests depend on ordered setup and intentionally leave the partial target intact until reviewed cleanup; they are integration tests, not independently reorderable unit tests.

Scripts are invoked with python3; no chmod/install step is needed. Local trust inside the DB namespace is an explicit maintenance assumption. Docker/root access remains privileged. The approval record is local change-control evidence, not independent human authentication.

No package download, production credential, historical migration edit, volume reset, operational gateway or inventory workbook is required. The previous capture feasibility suites are preserved but not rerun here.
