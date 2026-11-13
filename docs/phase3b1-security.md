# Phase 3B.1 security

## Boundaries

Staging imports no ORM/posting services and creates no catalog, database staging, Asset, StockBalance or StockMovement records. No approval/exclusion/promotion path or public endpoint exists. Phase 2C guards are unchanged; no migration was created or applied to development.

The production command pins the reviewed source byte hash and structural profile. Source drift fails HASH_MISMATCH; changing a profile requires review, never disabling verification.

| Control | Limit / behavior |
| --- | --- |
| Archive size | 16 MiB bounded read |
| Total expansion | 64 MiB declared total |
| Per member | 8 MiB bounded read |
| Archive members | 256; case-insensitive duplicate rejection |
| XML nodes | 500,000 per part |
| Coordinates | Row 10,000; column 64 maximum |
| Cells | 250,000 including formatting; source contains 191,897 |
| String length | 32,767 per text/attribute/resolved cell |
| Shared strings | 50,000 |
| Compression | ZIP stored/deflated only; no encryption |
| XML | Reject DTD/entity declarations and NUL/UTF-16 before parsing |
| Paths | Reject absolute/traversal/backslash/drive archive names and symlink entries; never extract |
| Parts | Explicit supported-part allowlist; reject macros, embedded objects and external-link parts |
| Relationships | Supported internal types only; no external modes/URLs; targets must remain in supported package |
| Workbook | Exact visible sheet order, strict sections, ordered unique coordinates and expected accounting |
| Formulas | Preserve/cache only; reject shared/array formula structures; missing cache blocks |
| Defined names | Only inert built-in filter metadata supported |
| Hidden rows | Inspect and preserve metadata |
| Errors | Static codes; never raw values or source/storage paths |

Style/table/drawing/person parts are parsed as inert supported metadata; unrelated author/person details are not copied into the inventory preview. Formula caches do not establish current physical location.

## Restricted files and limitations

Linux/POSIX storage requires a trusted operator-owned 0700 root outside the repository. Symlink aliases, insecure modes/ownership, nonregular existing artifacts and unexpected hard links fail closed. New final files are 0400 and never overwritten; replay compares canonical bytes. Failure before publication cleans its own temporary file and never publishes partial JSON.

These are filesystem controls, not immutability against root or a malicious owner who can chmod/remove data. Hashes detect mismatch but do not authenticate approval. Use restricted encrypted storage/backups and an approved retention policy. The directory and ancestors must not be movable by untrusted users during capture. No public endpoint accepts paths. Concurrent publication can fail closed during an integrity check; retry without replacing evidence.

Source/preview manifests, private dictionary bindings, serials, recipients, host tags, photos and private digest-linked data must stay outside Git and general logs. Identifiers can occur in category/description fields too. The command prints aggregate counts/codes only; downstream viewers must treat JSON text as untrusted data, never executable markup.

Synthetic test identifiers are invented. The source remains Git-ignored, and real artifacts are outside Git. No upload, staging in Git, commit or push was performed.

## Remaining work

Authenticated preparer tracking, independent review, append-only decisions, immutable approved snapshots, cross-batch source-consumption claims and import-aware provenance enforcement remain future work. The unchanged PostgreSQL guard still rejects import-linked movements; unlinked STOCK_IN is not a workaround.
