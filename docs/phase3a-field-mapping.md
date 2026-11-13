# Phase 3A field mapping

Analysis date: 2026-11-13 (Asia/Tokyo). Source: local confidential workbook; no source upload, database connection, Django execution, importer, commit or push. Confirmed findings come from all worksheet XML and cached cell values, interpreted against repository models and migrations on develop. Proposed mappings and physical interpretations require owner approval.

Schema references: backend/apps/inventory/models.py and choices.py; warehouse/models.py; accounts/models.py; transactions/models.py; services/posting.py; migrations 0002, 0004 and 0005. Phase 2B model design is evaluated with the subsequent Phase 2C guards, not as a standalone bulk-load schema.

| Observed source | Proposed Django target | Decision / validation |
| --- | --- | --- |
| Device Name; Column 1 | Asset.device_name; ProductModel.name | Column 1 is an observed device-label alias only in its original sections. 27 supply rows omit Device Name; approve a category-derived display label rather than silently invent a model. |
| Device Category | AssetCategory via ProductModel; model/compatibility specification | Not consistently a category: Server/Storage, FAN and host product names coexist. Review device role separately from compatible host; redact embedded service tags in public output. |
| Manufacturer; Manufacture | Manufacturer FK | Manufacture is a spelling alias. Preserve raw text; approve vendor aliases. Server, Mix and N/A are not reliable manufacturers. |
| Serial Number | Asset.serial_raw; serial_normalized; serial_review_state | Use trim+casefold search exactly as model; no unique constraint and no auto-merge. Placeholder -> blank normalized identity only after review, raw retained in staging. P/N and DP/N candidates -> ProductModel.part_number only after validation. |
| Qty | Posting Line.quantity for BULK or one SERIALIZED receipt | Positive integer pieces required; serialize multi-unit rows only with reviewed unit evidence. Box/Plastic need explicit packaging SKU/unit policy; never assume contents. |
| Status | Asset.lifecycle_status / StockBalance.stock_state | In Stock is a proposed on-hand interpretation, not evidence of good condition; Hand Over and N/A block until clarified. |
| Condition | Asset.condition / StockBalance.condition | New -> NEW, Used -> USED, Broken -> BROKEN. Good, Good/New and New Arrival need reviewed semantics; unknown -> UNKNOWN and QUARANTINED if accepted. |
| Capacity | ProductModel.capacity_bytes or AssetSpecification | GB/TB storage/RAM conversion requires decimal/binary policy. NIC Gb/GB can mean link rate. W, V, Wh are typed electrical specs, never bytes. |
| Type | interface_type / typed specification | SAS/SATA/NVMe interfaces, CAT 6 cable grade, Single/Double fan design and FRU/DS qualifiers need category-specific mapping. |
| DDR | ProductModel.memory_generation | Observed DDR3/4/5; do not infer from serial/model. |
| Speed | speed_value + speed_unit or typed specification | 10K/15K/7.2K suggest RPM; 12 Gbps is link rate. Verify first; paired value/unit required and positive. |
| Size | size_value + size_unit / form-factor spec | Inch values can describe form factor; LONG and mixed casing sizes need separate specs, not lossy numeric extraction. |
| Host Int | interface_type or host-interface spec | Approve PCIe spelling aliases; distinguish host bus from storage/network interface. |
| Ports | port_count plus connector specification | 17 rows describe two ports/connectors; one N/A remains null. Preserve cage/adapter distinctions. |
| Assigned To | Restricted legacy staging; AssetRecipient only after identity review | Same source label on all candidates; does not establish active custody, person identity or login. AssetAssignment needs issue movement, actor and timestamp. |
| Location; sheet name; Description | Warehouse + StorageLocation mapping | Two source location labels; rack names suggest children but do not prove current placement. Broken/Power Supply/LAN Cable sheets need explicit physical locations. |
| Last Audit Date | Asset.legacy_last_audit_date; bulk staging only | 1900 date system (date1904 absent); preserve original numeric/date type and convert to date. Never create a new audit or use as movement timestamp. |
| Description | Asset.description/remarks or reviewed catalog description | Decide unit versus shared scope; sanitize recipient and identifier text before documentation. |
| No | ImportStagingRecord.raw_values | Legacy sequence only; not asset_tag, serial or primary key. |
| Source file, worksheet, row | ImportBatch + ImportStagingRecord | SHA-256, controlled storage key, uploader, mapping version, raw ordered cells, source_row_digest, worksheet_name, excel_row_number. Header/number-only rows retain ignored reasons. |

## Required target values absent from workbook

No trustworthy SKU codes, internal asset tags, master foreign keys, warehouse hierarchy, import actor/reviewer, approved preview digest, posting UUIDs or movement evidence exist in source columns. Generate internal tags through the established service; approve catalog SKU grouping and master mappings first. Manufacturer can be null; capacity and model specifications can remain unknown. Never infer missing product specifications from a similar row or automatically group by serial.

## Serialized versus bulk proposal

Disks, RAM, NICs, controllers, batteries and individually identified power supplies are serialized candidates. Missing/duplicate manufacturer serials are permitted by schema and do not change tracking automatically. Fan rows (128), quantity-managed modules/cables/tools and nonserialized parts need approved tracking decisions: fans may be serialized despite missing serials or bulk if catalog policy supports it. All 30 explicit Qty rows require a tracking/unit decision; many quantity-one controllers are still serialized. Seven Rack 871 quantity rows have no serial column. No final serialized count or bulk piece total can be stated before these decisions.

ProductModel tracking mode must agree with Asset versus StockBalance targets and cannot be casually changed after references exist. AssetSpecification supports typed product or asset values (exactly one owner and one correctly typed value); prefer an asset override when the source is unit-specific.
