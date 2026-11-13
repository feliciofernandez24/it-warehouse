# Phase 2C transaction engine

Implementation date: 2026-11-13 (Asia/Tokyo). No APIs, frontend, Excel execution, commit or push.

## Inspection and enforcement matrix

Read inventory models/choices, transactions models and 0002 guards, audits/accounts/warehouse/common models, settings, database architecture/ERD, Phase 2B model reference/validation and Phase 2 implementation plan before implementation. The existing migration graph is retained; 0001/0002 are not rewritten.

| Invariant | Phase 2B database | Phase 2B application | Phase 2C change |
| --- | --- | --- | --- |
| Nonnegative balances; positive movement units | CHECK | clean helpers | Conditional debit, locks, deferred ledger conservation |
| Tracking modes and immutable identities | Tracking/product/tag/bucket triggers | clean | Preserve triggers; pin their search paths |
| Movement history | Reject UPDATE/DELETE | None | Preserve guards; reject lines without an open complete operation |
| Whole request identity | Unique operation key + line | None | Durable StockOperation request JSON, version, SHA-256, owner, approval and completion |
| Asset custody | Unique open assignment, date/return checks, immutable issue identity | Movement correspondence in clean | Atomic lifecycle/custody changes, SQL evidence checks and deferred final-state agreement |
| Approval | Permission declarations only | None | Exact immutable request, independent approver, explicit current permission checks |
| Location hierarchy | Local CHECK only | Parent/cycle clean | Serialized cross-warehouse/kind/cycle/occupancy guards |
| Audit freeze/evidence | Row-local checks and protected deletes | No workflow | Recursive scopes, overlap guard, shared lock, freeze, snapshots and write-once observations |
| Reversals | FK and not-self check | None | Original row lock, cumulative quantity cap and target/direction validation |
| Restricted runtime | Development owner credentials | None | Reviewed deployment template; NOT applied to development |

## Operation header design

A line-level unique key cannot prove that all requested lines were committed or prevent later append. StockOperation therefore stores the entire normalized version-1 request, SHA-256 fingerprint, requesting actor/time, optional independent approval actor/time/reason, and posted_at. Movements retain the original operation_key/line_number design. PostgreSQL checks that a header exists, its actor and payload match each line, the operation is open, and the final line count matches the complete request. The operation key remains a UUID column; the header relationship is enforced by posting and immutable-header triggers rather than changing the existing movement field API.

The service includes every Line field, line ordering, reason and reference in canonical JSON. Same key + same payload + same actor returns the committed IDs. Changed actor, contents, quantity, reason or extra lines are rejected. Unposted approved requests are durable, but are never returned as successful postings. Failed new postings leave no header, movements, balances, asset or custody changes. A failed posting of a separately approved request leaves that approval available for a later valid retry.

## Service API

`apps.transactions.services` exports frozen `Line`, `Request`, `Result`, `request_operation`, `approve_operation`, and `post`. `custody.current_custody` returns the current recipient episode. `audits.start_audit` and `record_count` provide a limited safe counting foundation. Business logic is absent from views/serializers; no signals post stock.

```python
from uuid import uuid4
from apps.transactions.services import Line, Request, post
request = Request(uuid4(), (Line(
    operation_type="STOCK_IN", product_model_id=bulk_product.pk,
    quantity=5, destination_location_id=rack.pk,
),), reason="Supplier delivery")
result = post(actor=operator, request=request)
```

Receiving a SERIALIZED product creates a new asset with an internally generated immutable tag; quantity must be one and device_name nonblank. Manufacturer serials may be absent or duplicated. Existing serialized operations identify asset_id and omit product_model_id. Issue requires recipient_id; destination reference/description and due_at are custody evidence, never physical storage locations. due_at is an ISO-8601 aware timestamp string. A serialized return supplies assignment_id and reverses_id identifying that assignment's issue movement.

Bulk endpoints resolve by product/location/condition/state. Source uses source_condition/source_state; destination uses condition/state. Bulk returns require reverses_id identifying the original issue. Return quantity across all returns/reversals cannot exceed that issue. Zero buckets remain. Bulk issue never creates AssetAssignment.

Adjustments and disposal require `request_operation`, then `approve_operation` by another authorized user, then `post` with the exact request. No boolean approval parameter exists. Reclassify/quarantine with TRANSFER; source and destination may share a location when the bucket or serialized condition/state changes. ADJUSTMENT_OUT marks on-hand serialized equipment LOST; DISPOSAL marks it DISPOSED. Terminal assets cannot move. Reversals append new ledger entries, never rewrite originals.

## Atomicity and locking

Every operation is atomic. All engine writers first acquire PostgreSQL transaction advisory lock (73921,2). Audit, hierarchy, movement, asset, balance, assignment, operation and product-update statement triggers share that lock before row mutation locks are acquired. Services then lock assets in ascending PK order, products/buckets, original reversals and custody rows. The global lock serializes approved posting paths, including creation of missing buckets, and prevents predicate races with audit activation and hierarchy changes. Bulk debits additionally use quantity >= requested_quantity in the UPDATE. The tradeoff is one concurrent inventory writer for this deployment; scale only with a separately proved finer lock protocol.

Movement creation and inventory/custody updates share one transaction. Deferred constraint triggers validate final balances against the immutable ledger and assets against their latest movement and active custody. This permits the temporary issue/return intermediate state without weakening final-state protection. `post` forces deferred constraints before returning (and restores deferred mode); an enclosing caller transaction must still commit before external success is published. Database errors must be caught outside the failed atomic block.

## Audit foundation and limitations

COUNTING and SUBMITTED scopes are frozen. Recursive scopes include the parent itself and honor include_descendants. Active intersecting scopes cannot coexist. Hierarchy changes are conservatively blocked globally while any active audit exists. Snapshot creation and activation share the posting lock. Expected snapshots and counted observations are immutable; corrections cannot silently overwrite counts. Submitted evidence cannot be edited or unfrozen. COUNTING may be cancelled via an eventual authorized workflow; no cancellation service is exposed here.

Full completeness review, excess-item discovery, submission/cancellation authorization and approved reconciliation closing are NOT implemented. No bypass permits posting against a frozen audit or through audit_line/import_row. Submitted audits therefore require the future controlled closing workflow; do not submit operational audits until that workflow exists. The review_audit_adjustment permission is used to start/count this foundation; it does not enable correction posting.

Serialized recovery from LOST/DISPOSED, disposal of equipment still in external custody, approval rejection/revocation/expiry, measured units, import promotion and warehouse-specific access grants remain outside this service. Return issued equipment before loss/disposal processing; never invent a physical source location. No schema-owner security claim is made: see phase2c-security.md.
