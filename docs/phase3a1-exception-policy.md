# Phase 3A.1 exception policy

Design version: phase3a1-v1. Reference date: 2026-11-13, Asia/Tokyo. Documentation only; no schema, transaction engine, inventory or workbook changes. Source findings are confirmed from Phase 3A and a read-only XML recheck; policy choices below are proposals awaiting approval. No database state or installed migrations were queried.

## Initial triage policy and inspection queue

The initial BLOCKED union contains 105 distinct candidate rows. Flag counts overlap and must not be added as row totals. Exact per-row coverage is in [review workflow](phase3a1-review-workflow.md). Detector v1 is conservative and covers confirmed Phase 3A scopes plus explicitly suspicious specification values; it is not proof that every unflagged physical fact is correct.

| Issue code | Initial flagged rows | Detection / required evidence |
| --- | --- | --- |
| SERIAL_DUPLICATE | 23 | All rows in the 11 repeated non-placeholder trim+casefold key groups. Inspect each unit/label and component role, including cross-category and copied-block conflicts. Never auto-merge. |
| PART_LIKE_ID | 11 | Serial text begins P/N, PN or DP/N with colon/space. Check label/photo for manufacturer serial versus part number. Preserve original; move only a verified part identifier into part_number. |
| HANDOVER | 27 | Actual Status = Hand Over, not merely a broken-sheet name. Verify custody, handover evidence and current physical location. No invented issue/return/disposal history. |
| FUTURE_AUDIT_DATE | 7 | Date > fixed reference date 2026-11-13 in the 1900 system. Obtain corrected dated evidence or explicit acceptance to keep untrusted legacy value only in staging. Do not adjust year automatically. |
| PACKAGE_UNIT | 8 | Qty includes Box/Plastic instead of bare integral number. Count/package contents and unit basis need evidence; a label suggesting bag contents does not verify actual contents. |
| LOCATION_CONFLICT | 28 | All seven Power Supply candidates, 20 Rack 856 supply candidates and Rack 7 row 3. Inspect inside/above-rack or proposed-move text versus actual placement. |
| SPEC_CONFLICT | 9 | Rack 845 row 2 plus all Capacity = 6GB or 6G rows. Verify SSD/rotational-speed and capacity/link-rate interpretation; these may be source errors, not automatically corrected data. |

All other candidates initially carry REQUIRED_MAPPING_PENDING and NEEDS_CLARIFICATION. Unresolved manufacturer branding, taxonomy, SKU identity, tracking, condition semantics, quantity-one interpretation and site/rack binding require owner review. Detect additional contradictions during normalization; the queue is extensible and a new issue revision invalidates prior approval where relevant.

## Identity-sensitive missing values

19 rows lack serials and 35 have placeholders (31 No SN, four N/A). These 54 facts alone do not prove missing serialized assets, and overlap other flags. Mark SERIAL_IDENTITY_PENDING with NEEDS_CLARIFICATION while tracking is undecided. If a SERIALIZED proposal requires identity verification, upgrade to BLOCKED and inspect the item; distinguish a physically missing/unreadable serial from a part number or unrecorded label. A physically verified unit may be accepted with blank serial and MISSING review state under an approved policy; generated internal asset tags distinguish units. For confirmed BULK rows, absence of serial is expected and not an exception. Do not mark serial VERIFIED just because a key is unique; DUPLICATE records review outcome, not permission to merge.

CT-prefixed, composite and numeric identifiers need lexical/precision checks. Do not strip punctuation, split composite IDs or recover numeric precision by guessing. Source presence is not proof of authentic manufacturer identity. Check duplicate keys against both this file and future live inventory read-only; matching existing serials trigger review, not updates.

## Evidence and resolution rules

| Exception | Who resolves | Admissible result |
| --- | --- | --- |
| Duplicate source record versus separate physical unit | Inspector verifies labels/units; owner decides scope; independent reviewer accepts | Separate units remain separate assets; proven redundant source row may be EXCLUDED_WITH_REASON with linked evidence, never deleted or auto-merged. |
| Manufacturer/model unknown | Owner with label/catalog evidence, inspector if label needed | Nullable manufacturer/model_number may remain absent; required product identity/grouping must be approved without asserting unknown specifications. |
| Missing quantity | Owner approves source section single-unit convention supported by item evidence, or inspector counts | No automatic default. Positive whole pieces only for first contract; serialized multi-unit rows remain blocked. |
| Package quantity | Inspector counts contents; owner approves unit/SKU policy | Verified pieces with immutable conversion evidence, or defer/exclude from accepted scope. No guessed conversion or silent package-SKU substitution. |
| Location unavailable/conflicting | Inspector observes current location; owner approves actual storage master | Use verified active location. Quarantine is a stock state, not an invented physical place. Never invent shelf/bin coordinates. |
| Good / Good-New / New Arrival condition semantics | Owner defines policy; inspector checks actual condition where needed | Map only supported facts; explicitly accepted UNKNOWN -> QUARANTINED. Quarantine does not resolve identity/quantity/location blockers. |
| Handover/current assignment | Owner and custodian verify evidence; inspector confirms current placement/absence | Confirmed on-hand receipt or separately approved custody-cutover design. No forced AVAILABLE issue of broken stock. Unproved external custody stays blocked. |
| Missing/inconsistent specs | Inspector/owner verifies dimension and evidence | Leave optional unknown values null with reason; conflicting SKU-defining values block grouping until resolved. |
| Date anomaly | Owner supplies dated evidence; reviewer accepts disposition | Correct normalization with evidence or preserve only untrusted legacy raw fact. Missing date alone need not block receipt; do not invent historical audit/custody times. |
| Exclusion | Preparer proposes; distinct reviewer accepts owner scope decision | Mandatory reason code, explanation, evidence and source key. A rejected row is not silently dropped; preserve it in totals. |

Every observation records inspector actor ID/time, source keys, method, restricted evidence hash, observed facts and uncertainty. Resolutions record preparer, approver, evidence references and superseded issue IDs. Initial facts remain in raw capture; a false-positive issue is closed with reason, never erased. Issue severities and rule versions are bound into approval. Evidence expiry or changed physical circumstances requires revalidation.

## Fail-closed cases

Unexpected section headers, missing raw cells/caches needed for mapping, source hash mismatch, reused coordinates, tampered digests, invalid enums, zero/negative/fractional movement quantities, unresolved required locations and unsupported multiple-target source rows are BLOCKED. Reviewer approval cannot waive a schema, posting, provenance or ledger invariant. Exclusion cannot conceal a failed integrity check or bypass reconciliation. Owner approval does not authorize unsupported stock movements.

## Decisions outstanding before Phase 3B

Approve source authority/reference date, raw retention/access rules, section interpretation and preparer/reviewer roles; manufacturer aliases and null policy; taxonomy and SKU grouping; SERIALIZED/BULK choices including fans/tools/modules; quantity-one evidence and package unit policy; all site/rack/area bindings; condition/status meanings and missing-serial acceptance; byte/rate/speed/form-factor conversions; future-date dispositions; physical duplicate/spec/location/quantity/custody findings; selected versus deferred scope and overlap controls. Approve immutable snapshot/consumption schema and service/guard design separately. No production promotion is authorized by these documents.
