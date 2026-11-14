# Phase 3B.2B.2 security test plan

Status: tests specified, not implemented or executed in this design stage. Baseline evidence is docs/phase3b2b1-security-testing.md: 205 current tests plus 45 historical isolated tests = 250 passing, not one 250-test current-schema invocation. Preserve both runs; never reverse forward-only migrations to run historical tests.

## Environment and acceptance

Use only synthetic workbooks, users and confidential sentinel strings in disposable PostgreSQL 17 containers with explicit isolated database names, synthetic credentials, private temporary storage and no .env loading. Check database name, host/port/container identity and role before migrations; fail closed on development defaults. Historical settings have their own ITW_ISOLATED_TESTS/name restrictions. Do not reuse the B.1 SQL proof's hardcoded database fixture for operational deployment.

Future acceptance requires all 250 prior cases unchanged, new security tests passing without skips, fresh migration and synthetic upgrade through proposed 0004, makemigrations --check --dry-run, git diff --check, catalog ACL/owner inspection and independent review. Do not modify historical migrations or weaken a test to fit the design. Baseline tests were not rerun for these documentation-only changes; no claim of new runtime validation is made.

## Required adversarial cases

| Area | Cases and required outcome |
| --- | --- |
| Real runtime SQL | Connect as actual restricted nonsuperuser LOGIN, not only SET ROLE from admin. Deny review/auth/evidence SELECT, all table DML, sequences, TRUNCATE, COPY table access, schema CREATE, owner assumption, helper EXECUTE, trigger disablement and replication-role changes. Deny asset/balance/movement/operation/custody/audit mutations. Catalog-test role memberships, default ACLs, table/function owners and search_path. |
| Accidental grants | Temporarily grant nonowner review DML in isolated tests: existing owner guards still reject protected writes. Runtime function remains capture-only; no arbitrary SQL/action/status argument. Test public and temporary-schema shadow objects, overloaded helpers and hostile search_path. |
| Authentication | Anonymous/forged/unsaved/inactive/wrong-alias actors; missing CSRF/session; body actor overrides; staff/superuser without explicit grant; wrong content-type same codename; direct/group grant and revocation. All deny safely; capture does not authorize evidence reads. |
| Identity signatures | Missing/invalid/truncated signatures, wrong algorithm/key purpose/audience/deployment/database/action/actor/request/fingerprint, expired/future assertions, revoked keys, runtime-stolen credential with another user's ID or GUC. Deny before writes. Renewed valid assertion permits exact retry only. Signing service refuses arbitrary actor/manifests. |
| Verifier provenance | Caller-supplied manifest/rows, unapproved parser build, test profile overrides, substituted headers/sequence policy, wrong profile version/evidence digest, unverified profile, valid counts but wrong workbook/layout. Reject. A profile-definition attestation alone cannot establish capture provenance. |
| Canonicalization | Golden Python/SQL cross-runtime vectors: non-ASCII, combining characters, astral Unicode, escaping, negative/large integers, explicit nulls, array order and formula cache metadata. Reject floats, duplicate keys, invalid UTF-8, noncanonical bytes, excess fields/depth/nodes/length and DB column overflow. No silent Unicode normalization. |
| Tampering | Alter workbook, raw lexical value, formula/cache/style, coordinate, section, classification, layout, counts, row order, manifest, normalization dictionary/reference date/runtime, preview internal digest, artifact bytes, storage receipt/key/version. Every change must fail a binding check. Classification-only mutation must fail despite unchanged row digest. |
| Row reconciliation | Duplicate/missing/extra populated rows, duplicate coordinates, substituted digest, same serial on distinct rows, empty candidate set, excluded headers/sequence rows, nonnull promotion targets. Only exact manifest rows succeed; serial is never source identity. |
| Storage | Zip/XML bombs, traversal, external relationships, macros, source changed between hash/parse, symlink/hardlink/wrong-owner/mode files, arbitrary path/URL, disk-full/fsync failure, corrupt existing content address, malicious object version and absent durability lease. Fail closed and disclose no paths/raw data. Verify original workbook retention as well as preview. |
| Capture atomicity | Inject exception after batch, each row chunk, revision, participant, event, claim, nonce, receipt, forced constraints and commit. No committed partial batch/source/revision/event/claim/receipt/nonce; no snapshot or stock change. Allow sequence gaps. |
| Existing guards | Verify CAPTURED version 1, empty draft, sequence 1 CAPTURE and correct creator/participant; wrong actor/from-state/details digest/snapshot fails. Omitted event/participant fails deferred checks at commit. Source/profile/event/receipt edits/deletes and append after revision fail. APPROVE/REVOKE/PROMOTED remain disabled. |
| Replay | Exact authenticated retry returns byte-identical original receipt after revision advances. Actor/payload/profile/artifact/request-action mismatch conflicts. Different request for same workbook conflicts, including existing legacy batch and alternate profile. Request UUID collision with another review action conflicts. Used nonce with another request fails. Permission loss denies replay without changing history. |
| Concurrency | Two actual connections synchronize with barriers and observe pg_locks: same request once, same source/different requests once, different actor conflict, permission/group/active/key revoke ordering, collector/registration race. Winner commits atomically, waiter rereads current state. No timing-only sleep assertions. |
| Lock protocol | Verify advisory lock acquired before batch/revision/auth row locks; auth/admin/group provisioning paths included. Capture versus stock posting/audit/hierarchy waits consistently; no stock side effects. Reject unsupported isolation; recheck token expiry after lock wait; exercise bounded lock/statement timeout and sanitized deadlock errors. |
| Recovery | Kill worker before publish, after publish, during SQL and after commit before response. Test ambiguous commit exact replay, backup restoration of exact artifact versions, orphan grace/lease/reference protocol and retention holds. A committed object cannot be collected during lost acknowledgment. |
| Confidentiality | Sentinel raw values, person names, paths, tokens and SQL driver diagnostics never enter response/log/error. Capture response contains only authorized receipt metadata; denied retry does not reveal owner or evidence existence. Verify backup encryption/access and separate view-evidence authorization. |

Test verifier isolation and broker trust with a compromised web-runtime harness, not merely mocked signature success. Pin cryptographic dependency versions and run known-answer/invalid-signature tests plus parser fuzzing. Resource tests must bound database memory/CPU as well as upload size.

## Design review gates

1. Approve precise identity broker/verifier trust and key revocation procedures, SQL verifier dependency and canonical-byte interoperability.
2. Prove owner transfer/ACL boundary without granting runtime owner membership or broadening stock privileges.
3. Prove auth mutation and storage collection coordination, including administrative paths and failure windows.
4. Approve measured payload/time limits and retention/backup/recovery policy.
5. Implement and independently review forward-only 0004 and service adapter only in the next authorized stage; validate all tests before operational use.

These are implementation prerequisites, not completed controls. Secure capture is not ready for operational implementation until these blockers are resolved. This stage stops at the four design documents.