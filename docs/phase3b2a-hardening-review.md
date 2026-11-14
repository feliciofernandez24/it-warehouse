# Phase 3B.2A hardening review

Date: 2026-11-14 (Asia/Tokyo). Actual baseline remains develop 56fb442 plus preserved uncommitted Stage A implementation. This report supersedes the earlier four-model/190-test SQL and privilege counts; those earlier reports remain historical evidence.

## Confirmed findings and corrections

| Finding | Evidence / impact | Correction |
| --- | --- | --- |
| Workbook-specific SQL branch | Only the recognized hash received exact 15/920/897/21/2 checks; another hash received generic source checks. This was not a portable verified profile contract. | Owner-attested immutable ImportSourceProfile definition plus protected revision FK; exact counts apply to every profile/hash. No profiles seeded or operational registry enabled. |
| JSON row-number coercion | A complete submitted synthetic transaction accepted excel_row_number as text because ->> compared both representations as text. Regression failed before patch. | Require object entries and JSON number type with positive integer spelling, plus string identity/digest fields. |
| Excluded scope/label mismatch | A complete synthetic transaction accepted EXCLUDED with NEEDS_CLARIFICATION and a reason. Regression failed before patch. | Enforce both directions of excluded label/scope agreement; exclusion reason must be nonblank JSON text. |
| Actor assertion exposure if DML were granted | SQL actor IDs and explicit permission checks are not session authentication. No real approval was exposed, but broad future DML could make the boundary unsafe. | Nonowner review mutations now fail closed even with accidental DML grants. Runtime profile/capture registration is explicitly disabled; authenticated gateway is deferred. |
| Unbounded deployment waits | Prior migration files did not set local DDL timeouts. | Both undeployed migrations use transaction-local lock_timeout=5s and statement_timeout=30s. Runtime timeout policy remains a deployment decision. |

The two snapshot defects were reproduced against complete transactions, including SUBMIT evidence, before correction. Earlier incomplete probes would have failed at the generic deferred evidence check and were corrected to avoid false confidence. These were structural integrity gaps, not evidence of bypassing the existing stock-posting guards or of a production approval.

## Proposed-before-implementation schema correction

The added profile registry and protected reference were described before implementation. The final narrow design puts source_profile on ImportPreparationRevision, not ImportBatch. Every successor must inherit it, so a registered batch is bound through immutable lineage without changing the historical source-envelope schema.

Only uncommitted, undeployed 0002/0003 were corrected. No historical migration was edited; no extra migration number was introduced. Django state and generated SQL match.

## Exact files changed in this hardening task

| File | Change |
| --- | --- |
| backend/apps/inventory/models.py | Export ImportSourceProfile; prior Stage A edits preserved. |
| backend/apps/inventory/review_models.py | Add immutable profile metadata model and protected required revision FK. |
| backend/apps/inventory/migrations/0002_import_review_schema.py | Regenerate additive undeployed schema with profile constraints/FK and local timeouts; preserve irreversibility and swappable auth dependency. |
| backend/apps/inventory/migrations/0003_import_review_guards.py | Generic profile validation, immutable definition binding, strict snapshot types/scope, nonowner write gates and local timeouts. |
| backend/apps/inventory/test_review_schema.py | Preserve all 48 cases; adapt synthetic fixture helpers/profile binding and expected generic errors/catalog count. |
| backend/config/historical_inventory.py | Exclude the added profile model only in the separate historical test registry. |
| backend/apps/inventory/test_review_hardening.py | New: 28 focused regressions, including observed-lock races and privilege denials. |
| docs/phase3b2a-hardening-review.md | New: this report. |
| docs/phase3b2a-security-decisions.md | New: profile/authentication/role decisions. |
| docs/phase3b2a-migration-final-review.md | New: final SQL/privilege review. |
| docs/phase3b2a-validation-results.md | New: exact isolated results and reproduction commands. |

Old Phase 3B.2 design and initial implementation documents were retained without rewriting their historical results. Phase 2C code, stock guards, ledger/audit rules, original workbook, historical migrations, existing baseline test methods and offline reader/normalizer remain intact. No profile or private manifest was generated from real inventory or added to Git.

## Implemented versus deferred

IMPLEMENTED/TESTED: immutable profile definitions; pinned revision/lineage binding; exact source counts for all hashes; strict source/candidate entry types; duplicate/missing source reconciliation; scope/label consistency; existing lineage, snapshot, participant/event and version constraints; nonowner write gates; exact-byte SHA-256; static safe guard codes; PUBLIC EXECUTE revocation and rollback.

DISABLED: runtime profile provisioning, authenticated capture registration, source-file authenticity certification, functional review gateway, approval issuance, revocation issuance and promotion.

NOT IMPLEMENTED: full canonical-byte spelling equivalence, duplicate JSON-key rejection in PostgreSQL, authenticated actor attestation, business/evidence/master verification, race-safe auth/master coordination, signed approvals and source-consumption claims. SQL-owner structural fixtures do not certify these controls.

## Validation outcome

218 cases passed across isolated PostgreSQL suites: 173 current and 45 historical, no final failures/skips. This includes all previous 190 cases and 28 additions. System, drift, plan, generated SQL, fresh migration, owner/ACL and zero-data checks passed.

The original 897 source candidates were not registered or advanced. Development PostgreSQL remained untouched. No live imports, stock movements, approvals, production keys, commit or push. Stop at hardening; deployment and Phase 3B.2B remain subject to review.
