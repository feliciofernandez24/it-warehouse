# Phase 3B.2A security decisions

## Portable source-profile contract - IMPLEMENTED

ImportSourceProfile is a sensitive model with no default CRUD permissions or admin/API registration.

| Field | Type / rule |
| --- | --- |
| id | UUID PK |
| code / version | Char(64) controlled code, positive integer; unique pair |
| workbook_sha256 / layout_digest | Required lowercase SHA-256 identities |
| expected_counts | Required JSON object with exactly worksheets, populated, CANDIDATE, HEADER, SEQUENCE_ONLY |
| canonical_bytes / digest | Required bounded (1..65536 bytes) UTF-8 definition and SHA-256 of exact bytes |
| definition_verified | Boolean default false; definition attestation only |
| verification_evidence_digest | Nullable SHA-256; required iff definition_verified=true |
| registered_by / created_at | Database-assigned role name and statement timestamp, immutable |

The definition payload has domain itw.source-profile.v1, code, version, workbook_sha256, layout_digest and expected_counts. SQL checks supported shape/content, byte digest, JSON types, nonnegative integer counts, positive sheet/candidate counts and reconciliation of candidate/header/sequence totals. Ten new named profile constraints supplement trigger checks.

All profile UPDATE/DELETE attempts fail, including by the test owner. Pending definitions cannot be flipped to verified; a new reviewed version is required. A new version does not replace any existing revision binding.

Every revision requires a PROTECT FK. First capture checks the definition is verified and its workbook/layout identities match the batch/revision. Every successor must carry the same profile. The profile FK, capture identities and source rows freeze after registration. Snapshots bind the exact profile digest as well as workbook/layout/manifest/source digests. Exact counts are checked at insertion and final deferred validation, for every hash rather than one special workbook.

No operational profiles are seeded. The old 15/920/897/21/2 definition remains valid metadata that a future authenticated process must attest, not a condition embedded in SQL. Other supported definitions may have different exact counts. Unsupported, absent, unverified, malformed or mismatched profiles are rejected.

## Definition verification is not file authenticity

definition_verified is an owner-attested definition, not proof that a person uploaded the authentic file. A known hash, client digest or boolean is insufficient. No public profile-registration/capture service exists.

Raw profile insertion and review fixture mutations are allowed only to the table-owning migration principal for controlled schema tests/bootstrap. Nonowner attempts fail even with accidentally granted INSERT/UPDATE. Owner privileges are not an authentication gateway; database owners can alter DDL and remain outside runtime guarantees.

No production definition was provisioned and no real workbook was registered. Runtime profile registration, review writes and source validation remain disabled pending authenticated capture. An existing application using schema-owner credentials is not an acceptable production deployment.

## Required future authenticated integration - PROPOSED ONLY

Actor identity must come from Django request.user/session authentication, never actor_id in request JSON. The trusted service reloads the active user and explicit PostgreSQL grants (including group membership); it must not use cached has_perm, staff or superuser implication as import authority. Reviewers differ from uploader and all inherited/current contributors.

The eventual service must parse original bytes under existing limits, verify hash/layout/profile, regenerate the full row manifest and canonical payload, validate evidence/mappings, and bind authenticated user and request identity. Database helpers accepting actor IDs do not themselves establish that identity. Authorization changes need a reviewed concurrency protocol; no broad auth/master triggers were added.

If privileged SQL gateways are chosen, proposed exact signatures for review are:

    public.itw_register_source_profile(actor_id bigint, definition_bytes bytea,
        verification_evidence_digest text, request_id uuid) RETURNS uuid

    public.itw_register_verified_capture(actor_id bigint, source_profile_id uuid,
        verified_capture_envelope bytea, request_id uuid) RETURNS uuid

    public.itw_change_review_authority(admin_id bigint, subject_id bigint,
        grant_changes jsonb, request_id uuid) RETURNS void

These signatures are NOT IMPLEMENTED. Envelope schema, authenticated assertion mechanism, scope, idempotency, retained evidence and independent definition-review policy require separate review. Browser callers must never get direct SQL execution or choose an authoritative actor. SQL must not read arbitrary client paths or execute dynamic SQL. No approval gateway is proposed for activation in this stage.

The current owner-only gates deliberately prevent simply granting these hypothetical functions access. A future gate change requires a reviewed migration with an authenticated trusted gateway, not a caller-controlled SQL GUC or a blanket DML grant.

## Least-privilege role decisions

| Role | Intended authority | Current validation / status |
| --- | --- | --- |
| Migration owner | Offline DDL; never an application credential | Disposable PostgreSQL migration owner is postgres; no development/production ownership was configured. Test bootstrap DML is privileged fixture work, not an operational registry. |
| Review procedure owner | Restricted NOLOGIN, no superuser/BYPASSRLS/role administration; narrow table/function grants only | Design only, no definer procedures installed. Must not own application tables or be assumable by runtime. |
| Review runtime | Nonowner, nonsuperuser; eventually only reviewed gateway EXECUTE and scoped reads | Test capability roles are NOLOGIN and have no stock DML, immutable-table writes, sequence mutation, schema CREATE, DDL or private-function execution. No production grants applied. |
| Authorization administrator | Separate identity invoking only a reviewed authority-management gateway | Design only; no such function installed. Auth/master mutation coordination remains blocked. |

Tests inspect schema/table/sequence/function privileges, role flags, DML/TRUNCATE/ALTER/trigger-disable and private execution denial. A stronger test deliberately grants DML to a synthetic role: supplied actor IDs still cannot create captures or mutate review state/events due to owner-only gates.

## Snapshot decision

SHA-256 always binds exact stored bytes. Valid UTF-8 and JSON semantic equality do not prove canonical byte spelling. A positive regression deliberately stores noncanonical whitespace with its exact digest and confirms that digest differs from canonical encoding. Duplicate JSON-key rejection and complete canonicalization remain a future service responsibility; none of these structural snapshots is approvable.

Stock row readiness is not inferred from a structural lifecycle name. No actual source candidate was marked ready/approved. Full source authenticity, quantity/tracking/catalog/location/evidence policy and signed approval remain blocked.

## Confidentiality and deployment restrictions

All tests are synthetic; real source values, serials, recipients and manifests stay outside Git and ordinary logs. Model representations show internal identities only. Static guard codes are safe, but PostgreSQL CHECK/FK diagnostic DETAIL can include row values; future services must translate errors outside failed transactions and suppress private SQL-parameter logging.

Retention, encrypted artifacts/backups, scope entitlements, signing/key custody, production runtime accounts, gateway trust and auth/master coordination remain deployment blockers. No production signing keys or grants were created. Approval/import posting stays disabled by both new gates and unchanged Phase 2C protections.
