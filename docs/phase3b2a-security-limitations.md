# Phase 3B.2A security limitations

## IMPLEMENTED and TESTED

The review schema has no default CRUD permissions, no admin registration, no endpoint, no functional review/approval service and no production writer-role provisioning. Model strings/reprs contain only model and internal PK. Explicit guard errors use static codes without raw source values.

Nine fixed-search-path invoker functions protect lineage, state/event evidence, source ownership, immutable snapshots and append-only events/participants. PUBLIC EXECUTE is revoked. Tests exercise direct SQL and ORM bypasses, independent-review conflicts, inactive/unauthorized actors, signature-shaped approval attempts, rollback and nonowner DML/DDL denial.

Approval is not merely unchecked: both APPROVE events and transitions to APPROVED/REVOKED/PROMOTED are hard-rejected. There is no production key, signing action or approval issuance. Signature columns are inert future schema. Import-linked posting remains rejected by the unchanged Phase 2C guard.

## BLOCKED / NOT IMPLEMENTED controls

| Control | Current status / consequence |
| --- | --- |
| Authenticated actor attestation | BLOCKED: SQL receives actor IDs and checks active explicit grants, but cannot establish the authenticated human. Owner/compromised writer can assert another identity. No runtime approval path exists. |
| Race-safe permission changes | NOT IMPLEMENTED: no broad auth/group/permission coordination triggers or administrative procedures. Preparation checks are not a linearizable approval authorization guarantee. |
| Master-data coordination/drift | NOT IMPLEMENTED: no broad catalog/location trigger changes. Full master references/content/active ancestry checks and revocation-before-change protocol await deployment review. |
| Canonical approval encoding | BLOCKED: DB checks byte SHA-256 and JSON semantic equality/coverage, not canonical spelling, duplicate JSON keys or complete Python canonical ordering. |
| Complete source verification | NOT IMPLEMENTED for DB registration: current source reader still verifies offline files, but no authenticated register_capture service links that proof into database rows. SQL count/hash metadata cannot prove workbook authenticity. |
| Verified receipt plan | NOT IMPLEMENTED: structural snapshots can retain unresolved or deferred decisions and explicitly carry STRUCTURAL_ONLY. Full SKU/quantity/unit/condition/location/receipt/evidence policy validation is not certified. |
| Full request fingerprint | NOT IMPLEMENTED: request_id uniqueness and hex shape exist; canonical actor/action/request fingerprint recomputation and idempotent service replay do not. |
| Approval signature/key | NOT IMPLEMENTED: no HMAC generation, key loading, key custody/rotation, human signature or receipt verification service. |
| Approval/revocation workflow | BLOCKED: unconditional DB rejection, no enabled approve/revoke services/endpoints. Stored enum/columns do not authorize issuance. |
| Confidential read authorization | NOT IMPLEMENTED as a service: no evidence retrieval endpoint/permission-checking SQL reader. Raw DB access must remain restricted to trusted migration/test operators. |
| Runtime role deployment | BLOCKED: no new application grants or SECURITY DEFINER gateway. Nested private-helper EXECUTE requires future reviewed rights; never grant broadly to bypass failure. |
| Retention/purge/backup | PROPOSED: retain evidence with protected references; no runtime deletion/purge process. Organizational duration, encrypted backup and eventual archival need review. |
| Source consumption / promotion | NOT IMPLEMENTED: no cross-batch consumed-row claims or live opening movements. Import guards unchanged. |
| Tenant/warehouse scope | NOT IMPLEMENTED: design assumes a trusted organization until persisted entitlements are reviewed. |
| Owner/DDL/TRUNCATE resistance | Outside trigger guarantee: owners can alter schema or TRUNCATE. Runtime lacks these rights; tested nonowner denial is privilege enforcement, not an owner-proof trigger. |

A snapshot in READY_FOR_REVIEW in synthetic schema tests is structural evidence only. The current offline workbook candidates remain unapproved. Do not label the Stage A schema as an operational approval engine.

## Ownership, trust, grants and lock requirements before broad controls

No broad auth/master trigger or SECURITY DEFINER procedure was added. Their prerequisites remain:

1. Separate reviewed migration owner, restricted nonlogin procedure owner, review runtime and authorization administrator. The review writer must not own tables, have superuser/BYPASSRLS/CREATEROLE/schema CREATE/TRUNCATE or stock DML.
2. Authenticated service chooses actor from trusted session context, not request JSON or a custom GUC; explicit current direct/group grants and scope remain required.
3. If definer procedures are introduced, revoke PUBLIC EXECUTE atomically, use fixed qualified names, audit every callable signature and expose no dynamic SQL or arbitrary record mutation.
4. All affected review/auth/master administrators acquire advisory lock (73921,2) before row locks. Master/grant changes affecting effective approval require explicit coordinated revocation, not resurrection after regrant.
5. Resolve operational effects on Django auth/admin, group provisioning, migration/post_migrate, key access, timeouts and existing posting/audit writers, with two-connection concurrency tests.
6. Do not enable approval until server canonicalization, source/evidence/master verification and immutable signed snapshot validation have passed isolated adversarial tests.

The existing deployment-role SQL template is not applied here and is not a confidentiality or approval configuration for new tables. No runtime permissions were inferred from it.

## Confidentiality and diagnostic boundary

Raw source evidence, snapshot bytes, reasons, details, private artifact keys and future signatures are restricted data. No workbook contents, recipients or serial inventories were copied into code/docs. Fixtures are synthetic.

Static new trigger errors are safe codes, but PostgreSQL CHECK/FK/unique diagnostics may include failing-row DETAIL or bound values. They are privileged diagnostic output, not safe ordinary application exceptions. A future service must translate DB errors outside failed atomic blocks and prevent SQL parameter/traceback logging. No endpoint currently exposes those diagnostics. Hash verification does not authenticate a human or prove physical facts.

Private Phase 3B.1 files remain outside Git/public static roots. Source rows are immutable once registered, and ordinary notes do not amend source identities. Unknown manufacturers/models/serials/locations/quantities/specifications must remain unresolved; no cleanup or inference was added here.

## Required review before Phase 3B.2B

Approve the exact generated SQL and source-adoption policy; decide owner/runtime/function grants, authenticated actor gateway, canonical/full-plan verification, authorization/master locking and revocation behavior, retained key policy, confidentiality scope and evidence retention. Review the isolated historical-test strategy.

Development migration requires separate explicit authorization. Approval endpoints, signing, live import and stock posting are outside this completion.
