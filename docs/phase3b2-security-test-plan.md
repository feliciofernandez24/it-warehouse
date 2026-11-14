# Phase 3B.2 security and test plan

DESIGN ONLY. No tests, migrations, grants, DB connections, API endpoints or implementation changes were executed in Stage 1. The 142-test result is the existing Phase 3B.1 baseline, not a new test run.

## Threat and trust boundaries

Protect against unauthorized/inactive users, self-approval, cached permissions, client digest/actor spoofing, stale concurrent revisions, mutable source/evidence, direct runtime table writes, replay and accidental source/stock mutation. Authenticate the user at the service boundary; derive actor from the session/token, never a request body.

The trusted application principal can assert authenticated actor IDs to DB procedures. A compromised application credential capable of invoking procedures can impersonate users unless a separately designed independently verified identity gateway is deployed. A custom SQL GUC is not authentication. Database owners, migration owners, root and external signing-key compromise are outside ordinary runtime guarantees; do not claim triggers defeat table owners.

Server HMAC approval receipts are tamper-evident server attestations, not user certificates or legal nonrepudiation. Key custody, rotation, retention, backup verification and access separation need deployment review. Never store the signing key in a table, canonical payload, environment example or log.

Initial authorization scope is one trusted organization: explicit import/evidence capabilities cover its batches. No warehouse/tenant entitlement model exists. If deployment requires narrower scope, stop before interface rollout and design persisted entitlements; a hidden client batch filter is insufficient.

## Least-privilege PostgreSQL design — PROPOSED

Use a separate review connection role, not the existing broadly writable inventory runtime role.

- Migration/schema owner: offline DDL only; not application login.
- Review procedure owner: NOLOGIN, nonsuperuser, no role administration/BYPASSRLS; receives narrowly required DML on source/review tables and SELECT on auth/master tables. Does not own inventory tables or receive Asset/StockBalance/StockMovement/StockOperation DML.
- Review runtime login: CONNECT/USAGE and EXECUTE only on explicitly listed capture/edit/submit/review/approve/revoke/read procedures. No direct table INSERT/UPDATE/DELETE/TRUNCATE, sequence manipulation or schema CREATE.
- Confidential reads: permission-checking procedures, not blanket SELECT on snapshot/evidence/source tables. Sanitized metrics expose no private identifiers. Do not re-run the old SELECT ON ALL TABLES template as a privacy configuration.
- Auth/provisioning administrator: separate connection/identity and lock-first procedures. Grant assignment is deployment administration, never a review endpoint. Destructive changes affecting active approvals require explicit prior/atomic revoke.
- Existing posting role/functions remain unchanged. No review role can invoke posting to simulate import or weaken import_row/audit_line guards.

SECURITY DEFINER review procedures are needed if runtime has no table DML. They must be owned by the restricted procedure owner, schema-qualified, fixed search_path with pg_catalog first and no unsafe writable schema resolution, no dynamic SQL, and bounded input/payload sizes. Revoke EXECUTE from PUBLIC in the same deployment transaction before granting only the reviewed signatures. No ownership, TRUNCATE, DISABLE TRIGGER, session_replication_role or function replacement privilege is available to runtime.

DB guards remain a second layer: reject snapshot/event/participant UPDATE/DELETE, incomplete event/state pairs, invalid transition, actor conflicts and legacy-field tampering. Ordinary ORM save/full_clean is not the boundary. Source registration/enrollment/transition procedures authenticate authority through explicit current database grants, while human session authenticity remains the service trust boundary.

## Concurrency deployment prerequisites

All review mutations use existing transaction advisory lock (73921,2) before row locks. New auth/master coordination triggers do not replace or weaken Phase 2C guards. They must cover changes in active user state, direct/group grants and membership, group permissions, permission/content-type definitions, and all master fields captured by snapshot semantics. Administrative writers must follow the same ordering.

For active approvals, recommended master and authorization guards reject a destructive change unless affected approvals are first explicitly REVOKED/SUPERSEDED under revoke_import, in the same lock-first transaction if combined. Removing an approver's grant cannot leave a reusable approval that later revives when the grant returns. A security administrator needs the reviewed revocation path; no automatic fabricated system-user event is permitted.

Before approval, a grant revocation or master update that commits first makes validation fail. After approval, an uncoordinated destructive change is refused; a coordinated revocation ends approval before changing authority/master state. Read-side effective-validity checks remain defense in depth for missing external artifacts or an owner-level bypass; they never edit a historical signature.

The extra triggers/lock footprint must be reviewed with existing auth administration, group provisioning and Django startup/post_migrate. A writer holding auth/master rows and then requesting the global lock can deadlock; supported entry points acquire the global lock first. Existing coarse serialization is retained deliberately. Do not deploy a claim of race-safe permission checks without the coordination and tests.

## Future interface controls

No endpoint is implemented or required in Stage 1. Start with restricted internal services. If DRF/session endpoints are later introduced, retain SessionAuthentication/IsAuthenticated and CSRF enforcement on every mutation; do not use csrf_exempt or mutation-through-GET. Add explicit capability/evidence permission per operation and expected-version/idempotency checks. Default IsAuthenticated alone is not approval authorization.

Authenticate again for high-risk approval if organizational policy requires it; no such feature is claimed existing. Never accept actor IDs, authoritative digests, contributor lists, terminal states or signatures from browser input. GET views must not resolve evidence or create review decisions. Use no-store private responses, escaped text rendering, object-size/rate limits and generic authorization/not-found errors.

Store raw data/evidence outside public static/media routes and Git, with encrypted backups, audited confidential access and immutable content addressing. DB snapshots contain private receipt semantics and require equivalent encryption/access controls. Ordinary logs contain request IDs, static codes and aggregates only; no serials, recipients, device tags, full payloads, private storage keys or evidence contents. Data may be embedded in descriptions/category fields too.

Event reasons and details are restricted records. Evidence service verifies artifact hashes and retention availability but cannot prove physical truth from a hash. Missing, replaced, expired or retired evidence fails approval/effective validity.

## Proposed isolated test matrix

All fixtures synthetic. Use PostgreSQL 17, a fresh tmpfs-backed test container and no development volumes/credentials. Separate connections and deterministic barriers are required for races; assert final state and immutable history after commit, not timing alone.

| Test group | Stimulus | Required result |
| --- | --- | --- |
| Identity | Uploader approves/reviews; creator/editor approves; inherited editor clones revision then approves | Denied; no approval event/state change |
| Auth | Anonymous, inactive, unauthorized, superuser without explicit grant, forged request actor | Denied; cached object flags do not grant authority |
| Capability separation | Review-only tries approve; approve-only lacks valid independent review; stock admin tries import approval | Denied |
| Scope/privacy | User without evidence permission reads raw snapshot; guessed object ID; private storage/static URL | Denied without content/existence leakage |
| Current review actor | REVIEW_ACCEPT actor becomes inactive or loses review grant before approval | Approval fails under fresh checks |
| Source tampering | Workbook hash/layout/cell/source digest changed; missing/duplicate candidate or header row | Submission/approval fails; original capture remains |
| Canonical tampering | Duplicate JSON keys, array reorder, float/NaN, Unicode/codepoint change, malformed decimal/date, tampered stored bytes/digest | Rejected or materially different digest; no rehash-in-place |
| Rules | Same version with changed dictionary bytes; changed runtime/validation date; unsigned/retired policy | New revision/review required |
| Masters | Same PK but changed tracking/capacity/category/vendor/location ancestry/active flag | Before approval: reject; after approval: guard requires revocation first |
| Reconciliation | 896/898 candidates; overlap/missing accepted/deferred/excluded membership; hidden row omitted | Reject; exact 897/920 accounting |
| Selected readiness | BLOCKED/NEEDS_CLARIFICATION selected; unknown required spec; empty selection | Reject; no blanket approval |
| Quantities | Missing inferred one, package quantity, fractional/zero/overflow, serialized Qty >1 | Reject unsupported selected plan |
| Optional unknowns | Verified allowed missing serial/manufacturer/optional spec | Null retained with explicit policy/evidence; no invented values |
| Scope decisions | Exclusion without reason/evidence; reviewer changes scope on sealed snapshot | Reject; corrections require successor |
| Receipt semantics | Defaults omitted; unknown location; broken AVAILABLE; absent provenance; custody cutover | Reject without any stock DML |
| Snapshot immutability | ORM/raw SQL UPDATE/DELETE of snapshot, source, participants or event | DB rejects even if full_clean skipped |
| Participant completeness | Edit with missing enrollment; removal; addition after seal | Rejected/enrollment required atomically |
| Transition bypass | Update state alone, append fake event, wrong owner/source/snapshot, mismatched version | Deferred/trigger/procedure rejection |
| Approval retry | Same request/actor/payload repeated, including lost response | Same receipt; one APPROVE event; response includes current state |
| Replay conflict | Same request ID with changed actor, reason, snapshot or expected version | Conflict; no new event |
| Duplicate approvals | Two authorized approvers with different keys race | Exactly one approval and signature |
| Edit vs submit/approve | Preparer edit races submission/reviewer action | One valid version wins; sealed content never changes |
| Permission race | Grant/membership removal races approval; group permission changes during review | Serialized outcome; no midway authorization gap |
| Master race | Relevant master update races submit/approve | Serialized consistent comparison; no TOCTOU acceptance |
| Return/reject | Reviewer returns or rejects then attempts approval of same revision | Terminal; only new revision may proceed |
| Supersession | Old revision approved while successor creation races; clone contributor laundering | Single active head; independence preserved |
| Revocation | Revoke races approval; grant restoration after revoked approval; repeated revoke retry | State/permission-specific result; no resurrection; original receipt preserved |
| Key/signature | Wrong MAC/key ID/receipt timestamp; rotation; missing retained key | Verification fails or original retained key validates; no silent re-sign |
| Rollback | Error after snapshot insert, signature creation or event append | Entire operation rolls back; no ghost approval or on_commit notification |
| Runtime role | Direct DML/TRUNCATE/DDL, trigger disable, function replacement/PUBLIC execution, legacy batch approve | Permission/guard denial; safe procedure still works |
| Lock discipline | Concurrent auth administration, review, master writes, posting/audit tests | No supported reverse lock order; timeout/retry whole request safely |
| No stock effect | Exercise every success/failure transition | Asset/balance/movement/operation/custody counts and contents unchanged |
| Future promotion | PROMOTED requested through service/raw SQL; linked movement attempted | Forbidden; unchanged Phase 2C import guard rejects |
| Migration safety | Fresh install, interrupted atomic migration, disposable historical restore, unsupported adoption | No data deletion/backfill/approval; fail closed |
| Confidentiality | Exceptions/HTTP/CLI/logs/SQL diagnostics tested with synthetic secrets | Static safe codes; secrets never ordinary output |

## Baseline and migration-test interaction

Preserve all 142 existing behavioral cases. Their current results are historical evidence; this design does not rerun them or claim new tests passed.

Important implementation issue: existing inventory SchemaTests and two transaction schema tests migrate back to transactions.0003 and restore the latest graph. Proposed forward-only review migrations depend on transactions.0005; that historical setup would attempt to unapply them. Do not add destructive reverse SQL merely to satisfy test setup.

Before implementing the new irreversible graph, adapt historical-schema tests to a separately initialized historical database/app registry that never received review migrations. Retain the original historical cases and run current 142 coverage plus new tests in their appropriate isolated schemas. Prove the harness separation on a disposable environment first; unresolved harness incompatibility blocks migration acceptance.

Future validation should inspect generated SQL, function ACLs/search paths and constraints; run the existing suite plus new unit/integration/concurrency tests; assert no source/model/engine drift beyond the reviewed implementation; rehearse backup/restore and key verification. No live database test or development migration belongs in this Stage 1.

## Open decisions and release gates

Review four-model scope, procedure trust boundary, signature/key policy, retention and global-organization access scope. Confirm operational ownership of authorization/master coordination triggers and explicit revocation-before-change policy. Resolve owner normalization dictionaries and physical evidence; no current row is ready.

Implement schema/invariants before authenticated services, services before interfaces, isolated adversarial tests before applying any reviewed migration to development. Keep promotion and source-consumption work deferred. No implementation follows automatically from this document.
