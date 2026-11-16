# Phase 3B.2D.4 predeployment review

Date: 2026-11-16, Asia/Tokyo. **Preparation only. No development maintenance, migration, data/role/ACL/history change or service restart was performed.**

## Source and prior evidence

Actual develop HEAD is `ddea0f839bd49fdd5da94b39cbbb09caddcb2f71`, not the earlier 7bb8e09. The worktree was initially clean. New D.4 files are uncommitted. Read in full: D.3 schema decision; D.2 role/migration plan, readiness and security validation; runtime-role rehearsal and grant matrix. Also inspected both migrations, settings, Compose, schema/runtime/read feasibility harnesses, review services and URLs.

The historical migrations remain unchanged:

| Migration | SHA-256 |
| --- | --- |
| 0002_import_review_schema.py | 0a9028ef00485e0048cbb21b9e8011a707cbd2380a404a6ca7974f141a06133c |
| 0003_import_review_guards.py | 58fff9f1844291019ef8f55497b547d7d19968b440dcd273c414b96f4fa5e879 |

0002 depends on inventory.0001, the swappable user and transactions.0005. Both the targeted and entire pending migration plans must equal exactly 0002 followed by 0003. Each migration is atomic separately. 0002 is explicitly irreversible; 0003 supplies no reverse SQL.

## Read-only development inventory

Inspections used SELECTs with `PGOPTIONS=-cdefault_transaction_read_only=on`; the new audit helper additionally uses a repeatable-read read-only transaction. No .env values, passwords, user records, workbook cells or stock records were printed.

| Item | Observed |
| --- | --- |
| Container | it-warehouse-db-1; ID 06a763552cf644ecb68efa4873bb00b978c7a4970acc7586a8eacf3cec035c11 |
| Cluster system identifier | 7706069425466331170 |
| Server / database / effective LOGIN | 17.11 / it_warehouse / it_warehouse |
| Persistent storage | it-warehouse_postgres_data, rw at /var/lib/postgresql/data |
| Network / published ports | it-warehouse_default, 172.19.0.2, aliases db and container name; no published DB ports |
| PG image | sha256:3540c0362c809df084ffac0ae69fe794515f9de92692f02178bcdce0ef0302ac |
| Backend image | sha256:35edbfd842667a865b801832e4ba66760a54f5b13c1c6ad5ca53fc88c71f3f65 |
| Application services | backend and frontend already exited (255); neither started/stopped by this phase |
| Migration history | 27 rows; inventory.0001 only; transactions.0001–0005 |
| Original public objects | 29 tables, 27 sequences, all owned by it_warehouse, null explicit relation ACLs |
| Database / default ACLs | owner it_warehouse, null database ACL; no default ACL entries |
| Role memberships | none |
| Extension | plpgsql 1.0, owned by it_warehouse |
| Sessions | inspection session only at sampled times; no other clients/transactions observed |
| Capacity | roughly 948 GiB available on backup filesystem; roughly 952 GiB available on DB storage; database about 10 MiB |
| Business data | asset, balance, movement, operation, assignment, audit, auditline, importbatch and staging counts all zero |
| Workflows | URLs only admin/ and api/health/; no capture/review endpoint; reserved actions remain disabled |

**Critical correction:** the live it_warehouse role is SUPERUSER, CREATEDB, CREATEROLE, INHERIT and BYPASSRLS. It is not merely an ordinary table owner. D.3 deliberately rehearsed an ordinary owner and did not query live flags. D.4 reproduced the actual superuser context on a disposable restored cluster and reran eight application smokes. This does not make the credential least privileged.

Local/loopback HBA is trust; other host connections use SCRAM. No password or HBA changes were made. A privileged Docker user can enter the namespace or use local trust; maintenance requires exclusive administrative control of that host, not an assertion that connection limits constrain a superuser.

Current-user crontab produced no entries. Inspected system timers were OS maintenance timers; no app-specific timer was observed. The Compose stack defines DB/backend/frontend, with no worker service. This census cannot exclude another user’s jobs, host scripts, external dependencies or a future connection. Operator attestation remains mandatory before isolation.

## Conflicts resolved in the new runbooks

- D.3 pins an older commit. The new configuration pins the actual HEAD and migration hashes; a future commit requires renewed review and updated approval.
- D.3's separate nonsuper migration member could SET ROLE an ordinary owner. That is not a valid way to assume the actual superuser owner. D.4 schema-only rehearsal uses the existing owner context under exclusive maintenance. A future role separation rollout is separate work.
- `compose stop` and one session census do not prevent reconnects. The gated runbook disconnects the DB's recorded bridge networks while keeping the DB and volume intact and retaining local migration access.
- `compose up -d backend frontend` would start services currently stopped and can recreate containers. D.4 restores only recorded networks and previously running application container IDs, never the database service.
- A successful dump checksum is insufficient. Fresh backup, archive-list verification, separate role metadata and a restore with owner/ACL/data/history comparisons are required.
- `--no-owner/--no-acl` cannot prove recovery. Neither is used here. Passwordless roles metadata is deliberately not a recoverable credential store.
- The old feasibility_schema harness migrates, seeds fixtures and probes DDL. It must never be used as a live verifier. D.4 separates read-only inspection from a separately gated apply operation.
- A targeted Django migrate command can run dependencies. The code checks both complete and targeted plans before any migration.
- Health is process liveness. Read-only identity/catalog checks and disposable authentication/session/stock tests provide the additional evidence.

## Remaining security boundaries

Schema-only readiness does not activate restricted runtime, a read gateway or capture. Shared superuser operation permits deliberate guard bypass, arbitrary DDL, privilege changes and identity fabrication. Existing Phase 2C guards still enforce normal service operations when intact; they do not isolate against that credential. Written acceptance of this temporary development risk is required, or applications must remain offline.

The prior restricted-runtime grant matrix remains evidence, not deployment SQL. Do not apply the broad phase2c runtime SQL example to confidential review tables. No role transition, new migration, operational endpoint or gateway is included.
