# Phase 3A data quality

Analysis date: 2026-11-13 (Asia/Tokyo). Source: local confidential workbook; no source upload, database connection, Django execution, importer, commit or push. Confirmed findings come from all worksheet XML and cached cell values, interpreted against repository models and migrations on develop. Proposed mappings and physical interpretations require owner approval.

## Confirmed findings

| Finding | Count / evidence | Required action |
| --- | --- | --- |
| Candidate inventory rows | 897 | Do not equate rows to physical units. |
| No serial value | 19: seven Rack 871 quantity rows, Rack 669 row 2, nine Rack 7 rows, two LAN Cable rows | Expected for some bulk; tracking review needed before calling these defective assets. |
| Serial placeholders | 35: No SN = 31 fan rows; N/A = 4 | Retain raw values; mark missing identity after reviewed normalization. |
| Repeated non-placeholder serial keys | 11 groups, 23 rows, 12 excess occurrences using trim+casefold | Review each physical unit; no merge/delete. Includes a repeated part-number group. |
| Part-number-like serial prefixes | 11 rows match P/N, PN or DP/N followed by colon/space | Validate part versus manufacturer serial. Other unprefixed part identifiers may exist. |
| Serial review limitations | CT prefixes and composite identifiers also present | Do not strip punctuation or split composite IDs without verified evidence. |
| Conditions | New 468; New Arrival 191; Used 105; Good 104; Good/New 1; Broken 28 | 296 non-enum rows need condition decisions; New/Used/Broken are direct proposed enum mappings. |
| Statuses | In Stock 869; Hand Over 27; N/A 1 | 28 ambiguous statuses block lifecycle mapping. |
| Audit dates | 896 present; 1 absent; 2026-05-16 through 2027-11-26 | Future dates must be verified against analysis date, not silently corrected. |
| Manufacturer aliases | HP/HPE, Dell/Dell EMC, SK Hynix/Sky hynix; HGST/HITACHI may reflect branding | Approve alias dictionary; no automatic corporate-brand consolidation. |
| Missing/invalid manufacturer | 26 absent after Manufacture alias; N/A 7; Mix 2; Server 2 | Keep null/unresolved; inspect source labels. |
| Classification | Server 623 plus one trailing-space variant; Storage 50; FAN 127 plus Fan 1; seven missing categories | Separate component role, host compatibility and vendor/model. |
| Recipients | One distinct Assigned To label across 897 candidates | No recipient value reproduced here; prove meaning before creating custody. |
| Source location labels | Two distinct values: 895 rows and 2 rows | Approve warehouse/rack mapping and verify physical placement. |
| Formulas | 117 location lookups, all cached | Validate location independently; no cache freshness guarantee. |

## Representative redacted examples and exact affected scopes

| Source reference | Redacted observation | Consequence |
| --- | --- | --- |
| Rack 845 rows 24, 25 | Same [SERIAL-A] | Two rows remain distinct pending physical review. |
| Rack 845 row 142; Rack 820 row 142 | Same [SERIAL-B] across disk and RAM tables | Strong classification/identity conflict; verify labels, do not select either automatically. |
| Rack 807 rows 7-13 and 15-21 | Seven paired repeated keys [SERIAL-C..I] | Possible copied block or separate units; physical review required. |
| Rack 820 rows 3, 6, 7 | Same [PART-J] in serial field | Part number reuse is not evidence of duplicate physical assets. |
| Broken Disk rows 9, 12 | Same [SERIAL-K] | Review both handover entries and custody. |
| Rack 845 row 2 | SSD label with 300GB and 10K | Rotational-speed/SSD inconsistency; no invented correction. |
| Rack 7 row 3 | Description says move to a different rack | Current versus intended location unresolved; verify actual placement. |
| Rack 7 rows 4, 5, 7-10; LAN Cable rows 2, 3 | Qty contains Box or Plastic | Eight unit-bearing quantities cannot be posted as pieces. |
| Rack 871 rows 14-20 | Quantities 7, 4, 8, 1, 5, 1, 1 without serial column | 27 nominal units, bulk/serialized policy unresolved. |
| Rack 877 row 37 | Qty 73 and placeholder serial | One row is not one serialized asset. |
| Power Supply rows 2-8; Rack 856 rows 56-75 | Device Name absent; prose distinguishes inside/above rack | Resolve display names and active locations. |
| Rack 669 rows 17, 24 | Host compatibility text contains [SERVICE-TAG] | Private identifiers can occur outside Serial Number; restrict raw descriptions/categories too. |

## Aggregate specifications

DDR3 115, DDR4 63, DDR5 1. Speed values: 10K 204, 7.2K 85, 15K 114, 12 Gbps 62, N/A 13; 419 rows lack Speed. Size values: 2.5 Inch 371, 3.5 Inch 83, LONG 4, 3 Inch 2, mixed drive/casing 13, N/A 5; 419 absent. Host Int has 18 values, including PCIe spelling variants; Ports has 17 two-connector descriptions and one N/A.

Capacity mixes disk/RAM GB/TB, seven suspicious 6GB entries, one 6G, NIC rate-like values, 128 fan 12V values, eight battery 3.7v values, six battery 96W values, one 57.6Wh and supply wattages. These are not a common measurable total. Preserve raw strings and approve dimensions/unit conversion by category.

After treating Manufacture as Manufacturer, vendor counts are Dell 301, HP 209, HPE 198, IBM 40, Lenovo 20, Seagate 23, HITACHI 14, Samsung 14, Dell EMC 14, HGST 11; remaining named labels are smaller groups. These are source-label frequencies, not canonical manufacturer decisions.

## Cleanup order

1. Approve authoritative source version and date interpretation; correct data in an owner-managed copy, preserving original bytes.
2. Approve section-aware extraction and inventory row manifest, with the two number-only rows ignored explicitly.
3. Resolve quantity units, tracking, serial conflicts and part numbers through physical checks.
4. Approve category/vendor/product and warehouse/location dictionaries; resolve description/location contradictions.
5. Approve condition/status meanings and custody interpretation, especially handover/broken rows.
6. Review restricted normalized preview and totals; leave unresolved rows blocked, never guess specifications.

Confirmed future audit-date values: 7 rows later than 2026-11-13 under the workbook date system. Future dates are a validation flag, not proof of the intended year.
