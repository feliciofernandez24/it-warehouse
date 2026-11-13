# Phase 3A.1 review workflow

Design version: phase3a1-v1. Reference date: 2026-11-13, Asia/Tokyo. Documentation only; no schema, transaction engine, inventory or workbook changes. Source findings are confirmed from Phase 3A and a read-only XML recheck; policy choices below are proposals awaiting approval. No database state or installed migrations were queried.

## Deterministic per-row decisions

The table below assigns one initial design label to every candidate in the source hash d0c48893cc095696ada206fb4d61d80c2745d412b289e0ab754dc5bd023bc525. It is a sanitized coordinate manifest, not approval or database state. BLOCKED means unresolved identified physical/evidence conflict under exception-policy v1. All other candidates are NEEDS_CLARIFICATION because catalog/tracking/location/quantity and policy bindings are not approved. No row is READY_FOR_REVIEW or EXCLUDED_WITH_REASON initially. Technical import-posting disablement is a batch-level blocker and is not duplicated into every row label.

| Exact worksheet | BLOCKED Excel rows | NEEDS_CLARIFICATION Excel rows |
| --- | --- | --- |
| 'Rack 1769' | none | 2-5, 14-17, 19-30 |
| 'Rack 845' | 2, 24-27, 72, 83, 119, 142, 280, 315-321 | 3-23, 28-71, 73-82, 84-118, 120-141, 143-279, 281-289, 292-314, 322-353 |
| 'Rack 877' | none | 2-22, 31-37 |
| 'Rack 871' | 2, 5 | 3-4, 6-7, 14-20 |
| 'Rack 856' | 56-75 | 2-19, 28-50 |
| 'Rack 807' | 7-13, 15-21 | 2-6, 14, 22-60 |
| 'Rack 820' | 2-4, 6-8, 142 | 5, 9-141, 143-178 |
| 'Rack 669' | none | 2, 11-24 |
| 'Rack 683' | 5, 129 | 2-4, 6-128 |
| 'Rack 7' | 3-5, 7-10 | 2, 6 |
| 'LAN Cable ' | 2-3 | none |
| 'Power Supply' | 2-8 | none |
| 'Broken RAM' | 2-3 | none |
| 'Broken Controller' | 2 | none |
| 'Broken Disk' | 2-25 | 26 |

Initial reconciliation: 897 = 105 BLOCKED + 792 NEEDS_CLARIFICATION + 0 READY_FOR_REVIEW + 0 EXCLUDED_WITH_REASON. Ranges include only actual candidates and preserve blank gaps. The 21 headers and two sequence-only rows are outside this equation, classified separately with ignored reasons. These are proposed triage outcomes from deterministic rules, not owner judgments or evidence of 105 distinct physical defects.

| Exclusive review label | Rule and existing RowStatus projection |
| --- | --- |
| EXCLUDED_WITH_REASON | Only after explicit preparer proposal and reviewer-accepted nonblank reason/evidence for an out-of-scope or confirmed duplicate source entry. IGNORED; retain raw row and decision. Never exclude simply because cleanup is difficult. |
| BLOCKED | Any unresolved blocking issue, structural/integrity error, inadmissible unit/cardinality or evidence contradiction. INVALID plus full issue list. |
| NEEDS_CLARIFICATION | No unresolved blocking issue but required mapping/policy/evidence is pending. CAPTURED plus question list; not READY. |
| READY_FOR_REVIEW | All required facts/bindings accepted by preparer, validations pass, remaining nonblocking warnings explicitly acknowledged; pending independent review. READY. Not permission to post. |

Evaluation order: invalid integrity/layout prevents any selection, including exclusion; otherwise an authorized reviewed exclusion is terminal; otherwise any blocking issue -> BLOCKED; otherwise any unresolved required fact -> NEEDS_CLARIFICATION; otherwise READY_FOR_REVIEW. Unknown/unsupported inputs always yield an issue, never a fifth or null label. Recompute after each revision. Store design labels in versioned normalized_values.review metadata in the proposed artifact; do not add them to RowStatus or database enums in this phase. APPROVED/PROMOTED remain model workflow states, separate from these four triage labels.

## Preparation and approval

1. Capture source and layout in restricted storage; verify hash and 920-row partition. Preparer starts a versioned normalization revision; no live catalog/stock effects.
2. Apply approved dictionary versions, collect restricted evidence and issue lists, then render one row decision for all 897 candidates and all excluded noncandidate rows. No hidden rows or default selections.
3. Owner resolves business policies; inspectors record actual observations with actor, timestamp, source references and evidence hash. The preparer records transformations as proposals with reasons. Physical inspection alone is not import approval.
4. READY_FOR_REVIEW rows may be proposed for selection. The reviewer sees full restricted source/proposal differences, issues, exclusions, overlaps, catalog grouping, location/condition/unit totals and scope omissions. The reviewer can return questions; changes produce a new revision and digest.
5. Freeze a complete candidate snapshot, including blocked/unselected/excluded rows and the explicit accepted subset. A distinct active reviewer with review_import signs the digest and accepted scope; reviewed_by must differ from uploaded_by AND all preparers/editors of the selected revision. No self-review through a second role. Store identity IDs privately, never names in docs.
6. Approval atomically seals an immutable snapshot and selected staging records as APPROVED with ImportBatch approval fields. Approval does not post. If any selected row is not READY, has unresolved blocking/required issues, or references expired evidence, approval fails. An empty accepted subset is not a promoted batch.
7. Later promotion needs promote_import plus receive_stock and any additional operation capabilities; revalidate under lock as defined in the import contract. Reviewer permissions/current account state must remain valid.

Use one uploader/preparer initially. If another user edits, record that identity and prohibit them from reviewing; existing uploader-only separation is insufficient. Approval records every editor/preparer and evidence version. Require a new review after any source, mapping, target-master content, selected scope, quantity, evidence or issue-disposition change. No edits to a sealed revision: supersede it with an append-only revision and approval event. A revoked or superseded approval cannot promote; its history remains immutable.

A subset can be approved only with explicit owner approval of deferred scope, full 897-row accounting and evidence that selected/deferred rows do not conceal duplicate physical stock. Whole accepted subset posts atomically. Exclusions and deferred rows remain visible; neither are implicitly cleared. The selected snapshot is consumed as a unit; later scope requires a new snapshot and the cross-batch source-consumption guard.

## Canonical bytes and preview digest v1

Canonical JSON is UTF-8 without BOM, sorted object keys, compact separators, ensure_ascii=false, no NaN/Infinity or binary floats. Strings preserve Unicode code points and raw whitespace (no Unicode normalization of source identity). Use integers for counts/row numbers, canonical fixed-point decimal strings without exponent/trailing fractional zeros (zero is 0), null for absent values, ISO dates and UTC timestamps ending Z with six fractional digits for evidence. Reject duplicate object keys. Decimal conversion uses decimal arithmetic, never floating point. Version the encoder and pin Unicode/casefold behavior in the normalization runtime.

Arrays have declared order: worksheets by workbook ordinal; rows by ordinal then numeric Excel row; cells by numeric column; issues by code/coordinate/evidence ID; dictionaries by stable entry ID; actors by ID; evidence by artifact digest and stable ID. Duplicate array identities are errors.

source_row_digest = SHA256(canonical({domain: itw.source-row.v1, workbook_sha256, worksheet_name, excel_row_number, section_header, raw_cells})). The envelope also pins the layout-manifest digest so header interpretation changes invalidate approval even if a raw data row is unchanged.

preview_digest = SHA256(canonical({domain: itw.import-preview.v1, workbook_sha256, layout_digest, manifest_digest, mapping_version, dictionary_content_digests, normalizer_version, validation_reference_date, source_timezone, revision_number, preparer_ids, rows, selected_source_keys, target_master_snapshots, evidence_digests, cutover_policy_version, planned_lines, aggregate_totals})). Each row includes its source key/digest/classification, normalized values, label, issues/dispositions, exclusion/defer reasons and evidence bindings. Planned lines are complete semantic requests with explicit values, never service defaults. Target snapshots contain IDs plus relevant field content/version; approval must fail if a master changes meaning while retaining its ID.

Exclude preview render time, random batch attempt UUID, reviewer signature, approval time, generated asset tags/PKs and posting result IDs from preview bytes. Include actual timestamps only when they are source/evidence facts. The same frozen proposal yields identical bytes; any material change yields a different digest. A changed reference date is a new validation revision; never use wall-clock now invisibly.

The immutable approval envelope stores snapshot bytes/hash, approving actor/time, roles, reason and prior revision link. SHA-256 is an integrity identifier, not authentication: restricted immutable storage, DB enforcement and authenticated approval are required. The existing StockOperation fingerprint remains its own request-payload digest; do not replace it with preview_digest. Planned receipt timestamps are truthful future execution timestamps bound by policy, not invented Excel history.

## Privacy and persistence

Raw capture, preview JSON, dictionary bindings, evidence, hashes linking private facts and approvals stay in access-controlled encrypted storage/database with least privilege and explicit retention. Do not write manifests, recipient labels, serials, host tags, photos or device-specific model bindings to Git, logs or public exception messages. Reviewer access is authenticated and audited; disable general admin edits to approved capture. Sanitized docs contain only aggregate counts, source coordinates, generic rules and redacted examples. No actual preparer or reviewer identity is assigned by this design.
