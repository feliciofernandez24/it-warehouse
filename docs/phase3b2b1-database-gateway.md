# Phase 3B.2B.1 database gateway

## Decision

Deliver an isolated executable read-only proof of concept, not an operational mutation gateway.
The existing owner-only guards remain unchanged. No inventory.0004 migration is necessary for
this proof, and none is created. No installation SQL is executed at startup or against development.

The SQL fixture refuses any database name other than test_phase3b2b1_test. Its installer is
executed inside one atomic test transaction. The fixture uses synthetic test credentials only.
Do not run it as a production role/grant script.

## Roles and privilege envelope

| Identity | Ownership and grants |
| --- | --- |
| Isolated migration/test owner | Owns application schema/tables; installs proof only in disposable tests |
| itw_review_poc_owner | NOLOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOINHERIT, NOBYPASSRLS; owns only the authorization function |
| itw_review_poc_runtime | Dedicated LOGIN with the same privilege restrictions; schema USAGE and explicit authorization-function EXECUTE only |

The schema remains owned by the installer. Temporary schema CREATE for function ownership
transfer is revoked in the creation transaction. There is no role membership allowing runtime
to assume the procedure owner. Neither proof role owns review tables.
The procedure owner receives selected-column SELECT only on auth_user, auth_permission,
django_content_type and the direct/group permission join tables. It has no review, evidence,
sequence, stock or other mutation grants. Runtime has no direct auth/evidence table reads.
Default public database access is not a production privilege-provisioning design.

Exact gateway signature:
`itw_review_gateway_poc.authorize(actor_id bigint, capability text) RETURNS text`.

The function is SECURITY DEFINER with search_path fixed to pg_catalog,pg_temp; all application
relations are qualified with public. There is no dynamic SQL. PUBLIC EXECUTE is revoked in the
same creation transaction, then EXECUTE is granted only to the dedicated runtime.
The function takes the shared advisory transaction lock before permission reads and returns only
OK or fixed denial codes. Capability input is allowlisted. It checks active status and explicit
direct/group grants, including the exact content type. It does not perform independent-review
checks, return evidence, or mutate any data. The service helper performs independence checks.

A caller-controlled actor ID is explicitly NOT human authentication. A stolen runtime credential
can ask whether another actor has a capability. Custom GUCs are ignored. This read-only proof
does not solve signed identity attestation and must not be promoted into a writable gateway.

## Locking and idempotency

The application preflight acquires pg_advisory_xact_lock(73921,2) before its revision row lock.
No file or network operations occur while it holds locks. Requests bind actor, action, revision,
expected version and canonical payload hash using the itw.review-request.v1 digest domain.
Request IDs are checked against immutable events. A mismatched actor, event kind, revision or
fingerprint is REQUEST_CONFLICT. Exact historical preflight returns the original event ID plus
current version/state; it is not an approval or an original immutable write-result snapshot.
For a new request, expected version and state must match.

No request result, event, participant or state change is persisted by the service. Therefore
there is no operational idempotent-write implementation or partial write to roll back.
Capture replay and durable original-result storage remain future contracts.
Future writes must acquire the same advisory lock first, then consistent batch/revision locks,
and atomically update state, event, participants and a durable replay result in one transaction.
They must recheck authority inside that mutation transaction. Never split preflight from posting.

## Deployment blockers

1. Decide how the gateway authenticates trusted application assertions and whether independent
   identity attestation is required under application-credential compromise.
2. Define and test permission/master-data mutation coordination; fresh permission queries alone
   are not race-safe.
3. Design narrow guard-compatible operations without granting procedure ownership of review
   tables or relaxing the current nonowner mutation ban. A writable SECURITY DEFINER function
   with existing guard checks cannot currently mutate these tables.
4. Specify verified capture/profile registration, business-valid preview verification, immutable
   result storage, request retention, safe retry policy and operational lock/statement timeouts.
5. Review production roles, database/schema default grants, credentials, deployment and rollback.
   Current development owner credentials are not a restricted runtime deployment.
6. Independently review any proposed forward migration before introducing writable gateway objects.

Approval/revocation issuance and promotion remain hard-disabled in both services and existing
database guards. Phase 2C ledger/provenance/conservation guards are unchanged.
