# Phase 3B.2B.2A feasibility results

Date: 2026-11-14. develop at c834bc3. **NOT READY to create an operational inventory.0004.** The isolated mechanisms are feasible, but ownership policy, extension qualification, canonical SQL validation and production trust/retention integration remain unresolved.

## Results

| Workstream | VERIFIED | PROPOSED / BLOCKED / NOT IMPLEMENTED |
| --- | --- | --- |
| Ownership | Six tests: scoped atomic transfer, fresh/populated schema, real definer and LOGIN denials, accidental DML grants, old-owner breakage and rollback | Proposed owner model conflicts with Phase 3B.2A policy. No production ownership/grant migration |
| Signatures | Twelve tests: pgsodium 3.1.11 on PostgreSQL 17.11, RFC vector, synthetic signatures and hostile claims | Database primitive works; extension lifecycle/native boundary require review. Independent human authentication and full canonical SQL contract not implemented |
| Authorization | Six tests: deactivation/direct/group revocations, both lock orderings and timeout | Full production administration coordination and TRUNCATE policy not implemented |
| Artifacts | Six tests: durable publication calls, exact-version digests, rollback orphan, lost acknowledgment, collector races | Local state machine only; production immutable storage, encryption, backup/restore and signed reservations not implemented |
| Canonical/timezone | Four tests, including five frozen byte/digest vectors | Encoding/linkage verified; full production schema/resource validator not implemented. Asia/Dili deployment timezone proposed only |

Detailed reports: [ownership](phase3b2b2a-ownership-feasibility.md), [signatures](phase3b2b2a-signature-verification.md), [auth locking](phase3b2b2a-auth-locking.md), [retention](phase3b2b2a-artifact-retention.md). Exact catalog ownership/ACL observations and final counts are in [evidence JSON](phase3b2b2a-feasibility-evidence.json). Candidate-source references are linked in the signature report; a passing crypto proof does not imply production certification.

| Suite | Passed | Failed/errors | Skipped |
| --- | ---: | ---: | ---: |
| Current committed baseline | 205 | 0 | 0 |
| Historical isolated registry | 45 | 0 | 0 |
| New standalone feasibility tests | 34 | 0 | 0 |
| Total | 284 | 0 | 0 |

The 205 current cases and 45 historical cases ran separately using their existing required database names/settings. The 34 feasibility cases ran afterward in clones of a disposable migrated database, not under Django's operational service interfaces. No skips or expected failures hide a missing implementation: the SQL canonical-gap test deliberately verifies the known unsafe acceptance and keeps deployment blocked.

Earlier harness runs exposed missing synthetic TimestampedModel.version SQL values and the pgsodium masking DDL hook failure. Fixture defaults were corrected. LOAD did not resolve the extension hook; an isolated session-only hook setting allowed the remaining proof while preserving the production packaging blocker. Final results above are the completed successful runs, not those intermediate failures.

Fresh migrations through inventory.0003 and transactions.0005 succeeded only in the disposable base. makemigrations --check --dry-run reports No changes detected. The baseline remains on its original table ownership; ownership-specific proofs separately exercised the proposed transfer. No claim is made that the entire Django workload is qualified under transferred ownership.

## Canonical contract and timezone findings

[canonical-vectors.json](../backend/feasibility_capture/canonical-vectors.json) freezes literal canonical JSON, UTF-8 hex and SHA-256. Expected byte spelling was constructed independently from sorted JSON field definitions, with hashes computed by .NET, then checked against the existing Python staging canonicalizer and PostgreSQL SHA-256. Ed25519 tests also sign these exact bytes and reject appended-byte changes.

The five vectors cover composed/decomposed Unicode, Japanese and astral characters, escapes, explicit nulls, integer row numbers, a large exact integer, formula/cache/type/style metadata, array ordering, a complete proposed capture envelope and a request whose envelope_digest equals that envelope's actual byte hash. Invalid UTF-8/BOM, duplicate keys, floats/exponents/nonfinite numbers, lone surrogates and noncanonical whitespace are rejected by the strict Python test parser. Source strings are never Unicode-normalized.

This stage proposes an exact nested envelope field layout frozen by the vector: domain, profile, workbook, layout_digest, manifest, capture, parser, normalization, source_timezone, date_system, counts, source_row_set_digest, storage_receipt_id, retention_policy_version. Nested fields preserve the bindings from the B.2 architecture, including parser.configuration_digest. Synthetic component hashes are illustrative; the serialization vectors do not attest a real workbook or claim a full verifier is implemented.

Resolve the earlier request_bytes ambiguity before implementation: propose that itw.capture-request.v1 contains exactly domain, actor_id, action, request_id, revision_id, expected_version and envelope_digest. SHA256 of those canonical bytes is the request fingerprint. Transmit the separately bound envelope bytes explicitly; the eventual register_v1 signature must add envelope_bytes or specify a different transport wrapper rather than silently treating one domain as two shapes. No production function signature changed here.

Propose Asia/Dili for deployment-local Django time rendering/scheduling. Keep source_timezone explicitly bound to the workbook profile/manifest; the existing source remains Asia/Tokyo. Assertions use UTC epoch instants and database audit timestamps remain timestamptz. Asia/Dili and Asia/Tokyo both show UTC+09:00 for the tested date, but equal offsets do not justify relabeling provenance. Existing settings, source timezone defaults, normalization reference date and original design documents remain unchanged.

## Readiness gates for inventory.0004

1. Resolve and record the Phase 3B.2A prohibition on procedure ownership of application tables. Define migration/bootstrap authority and audit existing grants, including the broad Phase 2C role template.
2. Qualify a maintained Ed25519 package and its full SQL/native dependency surface. Resolve pgsodium's DDL lifecycle and signature-length boundary findings, with ACL and malformed-input review.
3. Implement independently authenticated broker and capture-verifier assertions, key custody/revocation, exact issuer/audience/deployment bindings and durable replay results. Synthetic signing of an actor ID is not an authentication system.
4. Specify and prove complete SQL canonicalization, strict field types/limits and all envelope/manifest/source/profile byte bindings. The current valid-signed noncanonical JSON acceptance is a concrete blocker.
5. Qualify all authorization writers and supported transaction contexts. Set request timeouts before gateway execution; test additional key/admin/deadlock paths.
6. Integrate durable authenticated storage reservations/tombstones, immutable version retention, confidentiality, backup restoration and uncertain-commit reconciliation.
7. Freeze the revised transport/signature/schema contract, independently review a forward migration plan, then implement/test a future migration in a separately authorized stage.

No inventory.0004 file was created. A migration may be drafted after these design gates are resolved; operational capture cannot be enabled based solely on this prototype.

## Exact files added in this stage

Documentation/evidence:

- docs/phase3b2b2a-ownership-feasibility.md
- docs/phase3b2b2a-signature-verification.md
- docs/phase3b2b2a-auth-locking.md
- docs/phase3b2b2a-artifact-retention.md
- docs/phase3b2b2a-feasibility-results.md
- docs/phase3b2b2a-feasibility-evidence.json

Standalone prototype/tests:

- backend/feasibility_capture/README.md
- backend/feasibility_capture/common.py
- backend/feasibility_capture/run.py
- backend/feasibility_capture/test_database.py
- backend/feasibility_capture/test_signature.py
- backend/feasibility_capture/test_artifacts_contract.py
- backend/feasibility_capture/canonical-vectors.json

The four existing uncommitted docs/phase3b2b2-*.md design documents were preserved, not rewritten. No tracked application file, existing migration, stock service/guard, production setting, dependency manifest or credential file changed. No commit or push occurred.

## Isolation and cleanup

Dedicated containers: it-warehouse-phase3b2b2a-test-db and it-warehouse-phase3b2b2a-client. PostgreSQL 17.11 used tmpfs at /var/lib/postgresql/data (768 MiB), no volume and no published ports. The client shared only that container's network namespace and mounted backend read-only. All PostgreSQL environment values were explicit synthetic values; .env was not loaded. Source workbook/imports/backups were not read.

Only these two new containers are stopped after evidence collection. Their stopped container layers may retain build dependencies; PostgreSQL tmpfs data disappears on stop. Existing development containers and previous test containers are left alone. No persistent volume reset or original inventory access occurred.

[Reproduction instructions](../backend/feasibility_capture/README.md) describe the disposable setup and separate baseline invocations. This stage stops at feasibility evidence and blockers.