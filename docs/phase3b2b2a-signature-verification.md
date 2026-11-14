# Phase 3B.2B.2A signature verification feasibility

Status: real cryptographic primitive verified; production verifier and independent identity authentication blocked. Date: 2026-11-14.

## Candidate evaluation

| Implementation | Evidence and decision |
| --- | --- |
| PostgreSQL 17 pgcrypto/core | Core SHA-256 binds bytes, but the documented pgcrypto interfaces do not provide the required detached Ed25519 assertion verifier. Do not substitute a digest or HMAC for independent signatures. [Official pgcrypto documentation](https://www.postgresql.org/docs/17/pgcrypto.html). |
| pgsodium 3.1.11 | Selected for isolated compatibility proof; tagged upstream release from June 2026 indicates recent maintenance activity. Uses libsodium and PostgreSQL extension packaging, with a fixed pgsodium schema. Requires libsodium >=1.0.18 and PostgreSQL >=14 per upstream. [Upstream project](https://github.com/michelp/pgsodium), [versioned package](https://www.pgxn.org/dist/pgsodium/3.1.11/). |
| cardano-community/pg_ed25519 1.0 SQL interface | An alternative C/ref10 extension with bytea verify/sign functions. Current maintenance assurance and PostgreSQL 17 qualification were not established; not installed or selected. [Primary repository](https://github.com/cardano-community/pg_ed25519). |
| Custom PL/Python/C/OpenSSL wrapper | Adds privileged-language or native-code maintenance and packaging responsibilities; NOT IMPLEMENTED. No success-returning stub exists. |

These are candidate assessments, not a claim that all candidates were built or audited.

## VERIFIED

Twelve SignatureTests passed using real pgsodium.crypto_sign_verify_detached(bytea,bytea,bytea) calls. Detached Ed25519 verifies exact message bytes; multipart Ed25519ph is a different protocol and is not substituted. [libsodium signature documentation](https://doc.libsodium.org/public-key_cryptography/public-key_signatures).

Tested build:

- PostgreSQL 17.11, x86_64 musl, Alpine 3.24.4.
- pgsodium v3.1.11, resolved commit a8b8a2739bab1f7a07445b1c911e2bd1abf67784.
- libsodium package 1.0.22-r0; GCC 15.2.0, PGXS/server headers from this PostgreSQL image; make with_llvm=no.
- Proof shared-library SHA-256: 9ed18f5859e01461a092a02c86b4dc0f2feab79a81042c918bee53a15ec710c2. This is a local build artifact identity, not upstream reproducible-build certification.
- Synthetic client signer: cryptography 50.0.2 on Python 3.13; ephemeral keys generated in the test runner, never sent to PostgreSQL. SQL receives only public keys, message bytes and signatures.
- Extension owned by postgres; separate NOLOGIN assertion-wrapper owner and actual restricted LOGIN. Runtime has no pgsodium schema access, key-table SELECT or owner membership. Only wrapper EXECUTE is exposed.

Positive proof includes RFC 8032's empty-message known-answer vector, independently generated signatures for identity/verifier purposes and all five frozen canonical vectors (Unicode, formula metadata, arrays, envelope and request). Changing a single trailing byte makes the signature fail.

Negative proof rejects invalid/short/null signatures, wrong key/purpose, wrong audience/actor/request/fingerprint/action/domain/algorithm, future/expired assertions, revoked public keys, duplicate JSON keys, null protocol fields, extra fields and replayed nonce/request. Rolled-back nonce consumption can be retried. Keys are purpose-separated. Claim checks and nonce consumption are synthetic SQL proof objects, not new application models.

## BLOCKED

Two concrete integration findings prevent production certification:

1. Installing pgsodium without shared_preload_libraries made its masking DDL hook fail ALTER TABLE with an unrecognized pgsodium.enable_event_trigger setting. LOAD alone did not fix this: the versioned source defines that setting only during shared preload. Proof administrator connections explicitly set enable_event_trigger=off to avoid the unrelated masking hook. A production decision must qualify the extension lifecycle, event hooks, grants, upgrades and recovery; do not silently add root-key management/preloading. [Versioned initialization source](https://raw.githubusercontent.com/michelp/pgsodium/v3.1.11/src/pgsodium.c).
2. The detached verification C wrapper checks public-key size but does not itself check signature byte length before calling libsodium. The proof checks exactly 64 signature bytes before entering native code and denies direct runtime helper access. This narrow review finding requires an upstream/security review and verified ACL containment; malformed native calls were not deliberately used to crash a backend. [Versioned signature source](https://raw.githubusercontent.com/michelp/pgsodium/v3.1.11/src/sign.c).

The SQL proof intentionally demonstrates that correctly signed whitespace-formatted JSON passes native signature verification even though the strict Python canonical-byte checker rejects it. Duplicate-key detection via PostgreSQL IS JSON WITH UNIQUE KEYS is proven; a complete SQL canonical re-encoder, shape/depth/resource validator and envelope-to-source validator are NOT IMPLEMENTED. Signed-byte integrity is not canonical-contract enforcement.

A broker signing whatever actor ID a caller requests does not independently authenticate that person. Tests use synthetic claims and keys, not a live session/IdP broker. Neither a validated Django User nor the proof's expected-actor parameter proves a human login. A real broker must validate the session independently, bind action/request/envelope/deployment/database, protect its signer from the web runtime, and enforce current key/session revocation. Its implementation and abuse testing remain blocked.

## PROPOSED / NOT IMPLEMENTED

Propose a reviewed public-key-only PostgreSQL verifier wrapper around a pinned, audited dependency, with bounded messages, strict algorithm/purpose/audience allowlists, exact byte contracts, current-key checks under shared locking and durable nonce/receipt bindings. Review all extension-created roles, PUBLIC ACLs and dependencies; the proof does not audit the entire pgsodium surface.

No production signing material, broker, verifier/storage service, HSM/KMS integration, operational assertion gateway or deployment package exists. The cryptographic primitive is feasible; a safe complete capture verifier is not yet proven.