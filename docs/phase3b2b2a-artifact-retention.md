# Phase 3B.2B.2A artifact retention feasibility

Status: six synthetic state-machine tests VERIFIED; production storage NOT IMPLEMENTED. Date: 2026-11-14.

## VERIFIED

ArtifactTests publishes synthetic bytes under a private /tmp directory in the disposable client container, with a 0700 root and 0400 file. The filename binds SHA-256 plus a unique object-version UUID. It uses O_EXCL/O_NOFOLLOW, file fsync and directory fsync. No original workbook or existing staging artifact is opened.

A disposable SQL reservation records version/digest/expiry/state. Registration metadata and replay-result bytes commit atomically in a reference table. This is an artifact-reference simulation, not ImportBatch/source-registration implementation.

Six tests prove:

1. The exact version has the expected digest/private permissions and cannot be republished with O_EXCL.
2. Storage publication survives an injected SQL rollback, leaving no committed reference. An unexpired reservation prevents collection; after expiry an unreferenced artifact is collected.
3. A committed SQL reference survives a deliberately discarded acknowledgment. A new connection returns byte-identical receipt bytes; collection refuses the referenced version even far beyond lease expiry.
4. Changed evidence fails SHA-256 verification; missing evidence raises a controlled test failure.
5. A registration transaction holding (73921,2) causes a collector to wait. After commit the collector sees the reference and refuses retirement.
6. A collector holding the lock marks an unreferenced expired version RETIRED. A waiting registration then refuses that version, even before physical deletion completes.

Race synchronization observes actual advisory-lock waiters in pg_locks. Logical expiry values allow deterministic tests without waiting for wall-clock lease duration.

## PROPOSED

Use a durable tombstone protocol for collection, rather than holding a SQL transaction open during remote deletion:

- Upload/publish and verify bytes before registration SQL.
- Under (73921,2), registration requires a live READY reservation and writes the durable reference/receipt.
- Under the same lock, collection may retire only an expired, unreferenced version. Commit an irreversible RETIRED tombstone.
- Delete that exact storage version outside the database transaction. Retried deletion is safe; registration can never adopt the retired version. A reupload receives a new version and reservation.
- A committed reference always wins over lease expiry or lost pin acknowledgments. Keep tombstones long enough to defeat stale requests and worker retries.

This refines the earlier design's general lease/recheck requirement. It avoids the unsafe window between checking for references and deleting an object while a concurrent registration commits. The proof's reference lookup and tombstone mutation serialize under the existing global lock.

## Recovery

| Failure window | Required action |
| --- | --- |
| Publication succeeds, SQL rolls back | Preserve the reservation until expiry/grace; collect only through the coordinated tombstone path |
| SQL commits, response is lost | Reauthenticate, preserve the request identity, and replay/query the durable receipt; never assume rollback or mint a new request |
| Collector commits RETIRED then crashes | Retry deletion of the same version; deny all attempted new references to it |
| Committed artifact missing/corrupt | Block evidence use/advancement, alert with sanitized metadata, restore the exact committed version from verified backup |
| Storage or SQL temporarily unavailable | Fail closed; do not collect based on unavailable reference information |

## BLOCKED

Local permissions are not immutable storage against the same OS owner/root. The tests deliberately mutate a 0400 file as its owner and verify detection. Digest detection does not prevent damage and cannot recover missing bytes without a backup.

The test SQL state machine uses privileged synthetic administrator connections, not a production retention role/ACL design. The simple fixed expiry and byte-equality receipt simulation are not authenticated reservation attestations, full registration idempotency or a complete collector implementation.

fsync calls were executed, but power-loss durability, replication, object-store consistency, encryption, legal hold, encrypted backups, restore drills, immutable/WORM enforcement and separation of storage principals were not tested. No remote object store or signing-service trust was established.

## NOT IMPLEMENTED

No production storage settings, cleanup job, retention period or filesystem policy changed. Seven-day orphan grace and indefinite committed retention remain proposals requiring an approved policy. Production implementation needs a durable reservation/tombstone schema, authenticated storage receipts, exact-version reads, key custody, access auditing and recovery procedures integrated with the gateway.