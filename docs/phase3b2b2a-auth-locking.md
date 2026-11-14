# Phase 3B.2B.2A authorization locking

Status: six isolated tests VERIFIED; production coordination NOT IMPLEMENTED. Date: 2026-11-14.

## VERIFIED

AuthLockTests uses a separate cloned PostgreSQL 17 database and real separate connections. The synthetic authorization query checks current auth_user.is_active and direct/group capture_import permission on the exact inventory/importbatch content type. No cached Django grants or implicit staff/superuser authority are used.

Test-only BEFORE STATEMENT triggers acquire pg_advisory_xact_lock(73921,2) on user, direct permissions, group membership, group permissions, permission, group and content-type mutations. They exist only in the disposable auth-proof clone. They do not authorize administration or grant permissions.

| Race | Observed result |
| --- | --- |
| User deactivation commits first | Capture waiter sees inactive and denies |
| Direct permission deletion commits first | Capture waiter sees revocation and denies |
| Group membership removal commits first | Capture waiter sees removal and denies |
| Group permission removal commits first | Capture waiter sees revocation and denies |
| Capture holds lock first | All four administration cases wait; capture's current grant remains valid until its transaction releases the lock, then revocation commits |
| Bounded lock wait | Competing UPDATE produces SQLSTATE 55P03 with lock_timeout=250ms; no partial deactivation persists |

Synchronization is based on observing the waiter's actual ungranted advisory lock in pg_locks and checking the worker future is unfinished. A polling interval is used only to inspect catalog state under a deadline; no correctness assertion relies on a fixed sleep.

The four capture-first variations are subcases within one test method. Counts are six test methods, with nine ordering/timeout scenarios, not nine additional cases added to the baseline. All pass without skips.

## PROPOSED

Keep READ COMMITTED and acquire (73921,2) before any auth, batch or revision row locks. Execute fresh permission queries after lock acquisition. Existing Phase 2C and review triggers use this lock, preserving the existing conservative global ordering. A future capture function must not start with stock, auth-user or revision SELECT FOR UPDATE and request the global lock afterward.

Place lock_timeout/statement_timeout on the transaction/connection BEFORE issuing the gateway SELECT. Do not assume a SET statement_timeout executed inside an already running function retroactively bounds its outer statement. This proof sets the timeout before the waiting UPDATE; it does not certify in-function timeout setup from the earlier design.

All administration paths need the same ordering: Django admin/provisioning code, explicit SELECT FOR UPDATE, group cascades, bulk updates, key/policy revocation and any direct SQL. A BEFORE STATEMENT trigger guards ordinary DML ordering but cannot undo a row lock a caller acquired in an earlier statement. This earlier-lock case must be eliminated by service design/review.

## BLOCKED

The production authority-management API, admin transaction audit and full trigger/TRUNCATE policy are unresolved. Proof triggers cover an isolated schema only; their TRUNCATE event acquires a lock but does not implement the production prohibition or administrative authorization. Superusers, owners and trigger bypass remain trusted administrative risks.

Fresh reads alone remain unsafe against uncoordinated revocations. Noncooperating auth writers or REPEATABLE READ snapshots invalidate the tested guarantee. Production rollout must gate all mutation routes and reject unsupported transaction contexts before enabling capture.

These tests do not verify end-to-end authenticated capture, key-revocation races, long-lived sessions or deadlock recovery across every ORM administration path. Existing B.1 preflight remains read-only and cannot serve as a mutation authorization token.

## NOT IMPLEMENTED

No production auth trigger, permission-provisioning gateway or inventory.0004 was installed or created. Existing Phase 2C services/guards remain unchanged. Deployment must qualify this protocol with authenticated broker/verifier checks and the chosen ownership model before source registration becomes writable.