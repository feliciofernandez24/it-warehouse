# Phase 3B.2D.5 development schema deployment result

**STOPPED ? SAFETY GATE FAILED**

Authorization is complete, but the independent-restore stage failed before provisioning. The private orchestration wrapper supplied an itw-d5-* container name; the unchanged reviewed runbook requires itw-d4-*. The exact error was DISPOSABLE_NAME_REQUIRED. This was an orchestration mistake, not an authorization deficiency. No migration ran.

## Authorization and source

- Operator, approver and designated recovery operator: itadmin, explicitly confirmed by the user.
- Four maintenance/risk attestations: true based on explicit user confirmation, not an independent cryptographic signature.
- Approval: /home/itadmin/it-warehouse-db-backups/phase3b2d5_20261116T013810Z/approval.json.
- Authorization/recovery evidence: /home/itadmin/it-warehouse-db-backups/phase3b2d5_20261116T013810Z/authorization-and-recovery.json.
- Existing private candidate updated as requested; tracked template unchanged.
- develop HEAD: f059d114ccbd6e94d053b3236e9c69342e67668f.
- External configuration: /home/itadmin/.local/share/it-warehouse-d4/rebaseline-f059d114ccbd6e94d053b3236e9c69342e67668f/development.json.
- Config SHA-256: 96e611ff56d946c98848d6d77bc254fde3ddb5af177826bb67cd1b9359dae7b9.
- runbook.py SHA-256: e0b0574f8b9044afe32573c5f6743cec875ce7b98343271093761bb043bb09b0.
- dbcheck.py SHA-256: 8992307b87230370004d904e9b7835fdf5e39cca854bfba84907b140fed9ffbd.
- Tracked worktree/index unchanged; this preexisting untracked report was updated. No commit/push.

## Stage log

| Stage | Actual result |
| --- | --- |
| audit | exit 0; full recorded baseline matches, strict plan exactly inventory.0002 then .0003 |
| isolate | exit 0; DB networks detached; same container/volume; apps stayed stopped |
| backup | exit 0; nonempty private custom archive, role metadata and archive listing verified |
| restore-check | exit 1; DISPOSABLE_NAME_REQUIRED before any disposable target creation |
| apply | NOT RUN |
| verify | NOT RUN |
| pre-migration abort resume | exit 0; reviewed --allow-pre-migration-abort preservation checks passed; original network/IP/aliases restored |
| post-abort audit | exit 0; original database and relevant target observations match |

Exact stage output/error logs, audit-command.json, approval, recovery evidence, before-manifest and backup manifest remain under /home/itadmin/it-warehouse-db-backups/phase3b2d5_20261116T013810Z. No unsafe substitute migration or validator override was used.

Capacity precheck passed: about 947 GiB backup filesystem free and over 6 GiB host memory available. No observed clients or writer state contradicted the administrator's attestations.

## Fresh backup and restore verification

- File: /home/itadmin/it-warehouse-db-backups/phase3b2d5_20261116T013810Z/backup.dump.
- Bytes: 203233.
- SHA-256: 6486509382e62921de88b27df052cead197483c80cb400d886b95ebc69843b76.
- Role metadata: /home/itadmin/it-warehouse-db-backups/phase3b2d5_20261116T013810Z/roles-no-passwords.sql (no password hashes).
- Role metadata SHA-256: 13733bc027b441ea32c84554fb3ca561b688652fbddd9f2118d26780b53ee9ce.
- Before-manifest SHA-256: ce28b4eb3b8b49989a5b0d23cca18185a3a7bfce1f9de2b330c9b7bb7abf6d35.
- pg_restore --list / nonempty / final checksum: PASS.
- Independent restoration: NOT RUN; name rejected before container creation.
- No restore.json success marker exists. This archive is not claimed independently restore-verified.
- Original historical backup preserved.

## Final schema, records and service state

| Item | Final observation |
| --- | --- |
| PostgreSQL / database | 17.11, healthy / it_warehouse |
| System identifier | 7706069425466331170 |
| Container ID | 06a763552cf644ecb68efa4873bb00b978c7a4970acc7586a8eacf3cec035c11 |
| Persistent volume | it-warehouse_postgres_data, same data mount |
| Inventory history | 0001_initial only |
| Transactions history | 0001_initial through 0005_serialized_reclassification |
| Original tables / rows / migration rows | 29 / 165 / 27, unchanged |
| New five-table / eleven-function / eighteen-trigger schema | NOT INSTALLED; no migration attempted |
| Stock function/trigger definitions and enabled states | unchanged |
| Owners/ACLs, role flags/memberships, sequences and recorded schema metadata | unchanged |
| Other DB clients at final audit | zero |
| Backend/frontend | both stopped throughout |
| Runtime role or credential changes | none |

Every captured original key/row hash, table owner/ACL, sequence, role/membership, database/schema/default ACL/extension metadata, function, trigger, constraint/index and migration-history observation matched after abort recovery. Container ID, mounts, image, ports, database running state, network ID, IP, gateway, DNS names and aliases also match.

Docker reconnect appropriately generated a new endpoint ID/MAC and explicit IPv4 IPAM configuration. An additional comparison initially rejected byte-for-byte network metadata equality; inspection confirmed these expected reconnect differences, with the promised network/IP/aliases restored. No reviewed guard was changed or weakened.

## Recovery and remaining blocker

The workflow stopped at the failed guard as instructed. Reviewed pre-migration abort recovery verified unchanged history/records/metadata before reconnecting only the original DB networking. The DB container was not recreated or restarted; both applications remained stopped. No reverse migration, history faking, trigger disabling or volume deletion occurred.

The private wrapper prefix was corrected to itw-d4-d5-restore-* for a future attempt; the failed stage was not retried in this window. A subsequent attempt needs a NEW maintenance state directory and the entire audit/isolate/fresh-backup/restore-check sequence, with a valid new disposable name, before apply. Preserve this failed window's journal. Do not reuse its state.json as a fresh isolation journal.

Authorization and operator identity are no longer blockers. No repeated attestation questions are required. Revalidate current HEAD/hashes/target before a new attempt. If this report is committed first, account for the new HEAD through reviewed rebaseline.

No fixture-writing tests ran on persistent development, and earlier test counts are not claimed as new deployment tests. No inventory.0004, workbook processing, operational capture/review/approval/revocation/promotion, runtime-role provisioning, application startup, historical migration edit, automatic commit or push occurred.
