# Phase 3B.1 staging architecture

Implemented 2026-11-13 (Asia/Tokyo). Preparation only: no approval, catalog creation, inventory posting, public endpoint or React interface.

## Components

The local operator command stage_inventory calls pure modules in apps.inventory.staging: reader verifies/captures, normalization creates unresolved proposals/issues, and storage optionally publishes a restricted file. Standard output is sanitized aggregate JSON. Default execution is a dry run without persistence.

Python standard-library ZIP/XML/decimal/hash tools are sufficient; no dependencies or Kali system packages were installed. Archive members are never extracted; formulas and links are never executed. The command disables Django database checks and imports no ORM/posting services. Local OS access is the authorization boundary; the documented container has no network.

## Existing models and storage choice

ImportBatch already records source hash/storage key, mapping version, uploader, reviewer/digest and status. ImportStagingRecord already records unique batch/sheet/row, raw/normalized JSON, source digest, validation arrays, state and target links. Their current constraints do not enforce immutable capture or approved revisions, and reviewer separation covers uploader rather than every preparer.

This phase therefore uses private file capture rather than pretending those database protections exist. No model edits, migrations or database staging rows are necessary. No identities or approvals are invented. A future adapter can reuse existing JSON and CAPTURED/INVALID/READY states, but must implement immutable capture/revision and identity controls before approval.

## Manifest

The structural profile contains only reviewed hash, worksheet names, section headers and expected counts, derived from sanitized Phase 3A documentation. The production CLI has no profile/hash override. Alternate keyword-only profiles are internal synthetic-test inputs.

Each populated row retains workbook SHA-256, exact worksheet name, one-based Excel row, section identity, ordered raw cells, classification and source digest. Cells preserve coordinate, XML type/style, lexical numeric/shared-string index, resolved text, header, formula/cache/type and explicit nulls through section width. Numeric serials never pass through floating point.

Known sections are identified explicitly. Missing/unknown sheets/headers, duplicate or unordered coordinates and unexpected populated columns fail closed. Hidden rows are inspected and recorded. Blank intervals and merged ranges are layout metadata; empty formatting is not inventory.

Canonical JSON is UTF-8, sorted compact objects, unchanged Unicode/source whitespace and no binary floats. Source-row payload domain is itw.source-row.v1. Manifest/layout digests are separate; normalization verifies row/layout digests and unique identities before use.

Preparation domain is itw.preparation-preview.v1, with source/layout/manifest/dictionary digests, fixed validation date, rule and Python/Unicode runtime versions, every proposal/issue, and approval_enabled/posting_enabled false. The digest excludes itself. It is deliberately distinct from a future approved import-plan digest: no selected set, reviewer, target IDs or requests exist. Reproduction requires identical source, layout, rules, reference date and runtime.

## Normalization

Versioned dictionaries propose exact brand/category aliases without fuzzy merges. Brands remain distinct; one documented spelling correction is a proposal. Unknown manufacturer/category stays null. Component role is separate from host compatibility.

Product model/SKU and physical master bindings remain null because no approved dictionary exists. Tracking is a SERIALIZED candidate for recognized component roles; fans and other unresolved roles remain undecided. No BULK catalog binding is fabricated.

Finite positive integral quantities become integer PIECE proposals. Missing Qty stays null; no default one. Packages and invalid quantities block. New/Used/Broken map to enum proposals; other labels remain unresolved. Broken proposes QUARANTINED; usable In Stock may propose AVAILABLE. None authorize operations.

Warehouse/location remain unresolved. Typed proposals distinguish electrical values, DDR, rotational/link rates, simple form factor and port counts. GB/TB is not converted without dimension/unit approval. Missing optional specs remain null with reasons.

Blocking issues dominate clarification, otherwise READY_FOR_REVIEW. EXCLUDED_WITH_REASON is reserved; exclusion requests are rejected in this phase. Headers/sequence-only rows retain structural classifications, not automatic inventory exclusion.

## Confirmed reconciliation

| Metric | Count |
| --- | ---: |
| Worksheets | 15 |
| Populated rows | 920 |
| Candidates | 897 |
| Section headers | 21 |
| Sequence-only rows | 2 |
| BLOCKED | 105 |
| NEEDS_CLARIFICATION | 792 |
| READY_FOR_REVIEW / EXCLUDED_WITH_REASON | 0 / 0 |
| Approved / posting outcomes | 0 / 0 |

These reproduce Phase 3A.1 and are not physical-unit totals.

## Storage

The optional canonical preview includes its restricted manifest and is stored outside Git. Filename is SHA-256 of complete artifact bytes, distinct from internal preview_digest. Root must exist, be absolute, owned by the operator, mode 0700 and free of symlink aliases. Exclusive temporary write, fsync and atomic no-replace publication produce a 0400 file. Replay verifies bytes/owner/mode/link count rather than overwriting.

No model/schema change is proposed by this implementation. Future authenticated capture, approval snapshots and source-consumption guards remain separate work. See security and operations documents for limits.
