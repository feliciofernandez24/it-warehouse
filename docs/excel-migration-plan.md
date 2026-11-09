# Excel migration plan

Import workflow remains design only; staging schema is implemented in Phase 2B. No workbook was found in the workspace on 2026-11-09; no parser or import was run. Field names below come from the request, not observed workbook contents.

## Source capture and mapping

Retain original bytes in controlled storage outside Git; record filename, SHA-256, storage key, uploader and timestamp in ImportBatch. Inspect actual sheet names, headers, merged/hidden cells, repeated headers, totals, formulas/cached values and historical snapshots. Never execute macros or formulas. Confirm whether each sheet represents rack, broken group or standalone stock; do not assume sheet equals warehouse or every nonblank row equals inventory.

Staging retains original sheet and one-based Excel row number. raw_values is an ordered JSON cell list with column coordinate, original header, type, raw value, formula and cached value when present. This preserves duplicate headings and textual leading zeros. Dates/decimals use lossless strings plus type metadata. Source bytes retain formatting not reproduced in JSON. Stage ignored header/summary rows with reasons for completeness accounting.

| Source field | Proposed target | Validation |
| --- | --- | --- |
| Device Name | Asset.device_name / ProductModel.name | Not a unique identity |
| Device Category | AssetCategory through product | Reviewed controlled mapping |
| Manufacturer | Manufacturer through product | Explicit aliases, no fuzzy merge |
| Serial Number | serial_raw and derived search key | Preserve leading zeros/punctuation; warn on duplicates |
| Status | lifecycle_status / stock_state | Owner confirms meaning, separate from condition |
| Condition | Asset/bucket condition | Unknown/broken -> quarantine |
| Capacity | capacity_bytes or typed override | Confirm GB/GiB and category |
| Type | Category-specific typed spec/interface | No universal interpretation |
| Speed | Decimal value + unit / typed spec | Distinguish MHz, MT/s, RPM, Gbit/s |
| Size | Decimal dimension + unit / form-factor spec | Confirm length versus form factor |
| Qty | Asset count / bulk receipt quantity | Whole nonnegative units; serialized normally 1; zero reviewed, no zero movement |
| DDR | memory_generation | Validate controlled values and Type conflicts |
| Assigned To | AssetAssignment.recipient -> AssetRecipient | Explicit reviewed person/organization match; optional login link; never auto-create logins |
| Location | StorageLocation | Reconcile with worksheet-derived location |
| Last Audit Date | legacy_last_audit_date for asset; staging for bulk | Date-only if no time; not a new approved audit |
| Description | Asset/catalog description | Review unit versus shared catalog scope |
| Host Int | interface_type / host-interface spec | Confirm abbreviation with owner |
| Ports | port_count / typed connector spec | Integer only when actually a count |

Additional actual model/part-number fields may map after inspection; do not invent them. Confirm source locale, 1900/1904 date system and timestamp timezone. Ambiguous units/dates, rounded Excel numeric serials, conflicting assignment/status/location, unknown category and mixed-condition quantities block promotion or require explicit reviewed normalization. Original values remain unchanged.

## Preview and review

Batch states: UPLOADED -> VALIDATED -> IN_REVIEW -> APPROVED -> PROMOTED; FAILED/REJECTED retained. Row states CAPTURED, INVALID, READY, IGNORED, APPROVED, PROMOTED, REJECTED. Errors/warnings contain field, source coordinate, code, raw value and remediation. Raw capture immutable; normalized edits before approval generate change events. Mapping/row/target edits invalidate approval. Approved/promoted records cannot be edited in place.

Preview shows every source row, target matches, proposed catalog/locations, tracking choice, quantities by category/location/condition, duplicates, assignments, errors, warnings and ignored reasons. Reconcile source totals after identifying summaries and overlapping snapshots. Another authorized user approves a digest covering source hash, mapping version, accepted selection, normalized payload and target IDs. Promotion checks it under lock.

One accepted serialized row represents one unit. Qty>1 is blocked until a reviewed amended per-unit source/staging artifact and coordinate manifest exist; never replicate a serial or fabricate identities. Bulk rows may contribute to one bucket only for matching product/location/condition/state, retaining separate row references and receipts. Duplicate serial matches do not merge assets. Unresolved recipient identities block assigned-unit promotion; reviewed AssetRecipient records need no login account. Destination descriptions/references preserve hostnames, departments or work orders without fabricating a host inventory.

## Promotion and cutover

Before any live import: approve master-data additions, back up the database, rehearse on a disposable restore, reconcile results, and obtain explicit production preview approval and a cutover freeze. Staging itself never publishes catalog, users or stock.

Lock batch, verify status/digest/reviewer, revalidate current inventory and reject previously promoted identical source scope even in another batch. Repeated previews of the same bytes are allowed; repeated stock effects are not. New legitimate receipts need new business evidence, not re-import authorization.

Initially promote the entire accepted batch atomically through approved posting routines. Targets, opening STOCK_IN movements, logs, links and batch status commit together. Deterministic operation keys from batch/coordinates and unique StockMovement.import_row protect retries. Failure leaves no partial live stock. If too large, stop for an approved chunk/checkpoint design rather than silently permit partial import.

Already-assigned serialized stock needs a reviewed administrative cutover receipt and issue/assignment in one operation. Opening receipt is the row's unique promotion movement; paired issue shares operation_key and links through assignment/change event. Use truthful cutover timestamps and an explicitly approved transition location, retaining legacy facts in staging; do not invent historical receipts. Block these rows if this opening policy is not approved. Broken stock is quarantined regardless of sheet name.

## Reconciliation and correction

Compare accepted source counts to assets, bulk receipt quantities, assignments, location/condition totals and every target link. Reconcile ledger credits/debits with balances and asset chains/custody. Every ignored/rejected row retains a reason. Archive source, mapping, approved preview/digest, coordinate manifest and reconciliation under an approved retention policy. Restrict access to personal assignment data.

Failed transactions roll back. Committed imports are corrected through reviewed compensating movements/events, never deletion or direct quantity edits. Consider subsequent movements/custody before reversing; no negative stock. Preserve source batch/rows. Old Last Audit Date is not proof of a new PhysicalInventoryAudit.

Verify when workbook arrives: authoritative version, real layout/sheets, warehouse/rack mapping, overlapping snapshots, category/tracking choices, quantity units, serial placeholders/duplicates, model/part identities, status/condition meanings, recipients/host references, capacity/speed/size units, dates/timezone, expected totals, retention and cutover policy. No assumption above substitutes for this verification.
