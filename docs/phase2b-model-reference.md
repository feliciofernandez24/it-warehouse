# Phase 2B model reference

Generated from Django model metadata. SQL-only triggers are described in database-architecture.md. Foreign keys use PROTECT. Existing auth.User retained. reports has no table.

## accounts.AssetRecipient (accounts_assetrecipient)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| code | CharField(64) | unique |
| name | CharField(200) |  |
| description | TextField |  |
| is_active | BooleanField | default: True |
| kind | CharField(16) | choices: PERSON, DEPARTMENT, TEAM, ORGANIZATION; default: PERSON |
| user | OneToOneField | unique; nullable; FK auth.User; PROTECT |
| external_reference | CharField(200) |  |
| contact_details | TextField |  |

Constraints:

- accounts_assetrecipient_code_text: <CheckConstraint: condition=(AND: (NOT (AND: ('code', ''))), ('code__regex', '^[A-Z0-9][A-Z0-9_.-]*$')) name='accounts_assetrecipient_code_text'>
- accounts_assetrecipient_name_text: <CheckConstraint: condition=(AND: ('name__regex', '\\S')) name='accounts_assetrecipient_name_text'>
- recipient_kind_valid: <CheckConstraint: condition=(AND: ('kind__in', ['PERSON', 'DEPARTMENT', 'TEAM', 'ORGANIZATION'])) name='recipient_kind_valid'>
- recipient_user_person: <CheckConstraint: condition=(OR: ('user__isnull', True), ('kind', RecipientKind.PERSON)) name='recipient_user_person'>

Explicit indexes (FK/unique indexes are additional):

None.

## warehouse.Warehouse (warehouse_warehouse)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| code | CharField(64) | unique |
| name | CharField(200) |  |
| description | TextField |  |
| is_active | BooleanField | default: True |
| address | TextField |  |

Constraints:

- warehouse_warehouse_code_text: <CheckConstraint: condition=(AND: (NOT (AND: ('code', ''))), ('code__regex', '^[A-Z0-9][A-Z0-9_.-]*$')) name='warehouse_warehouse_code_text'>
- warehouse_warehouse_name_text: <CheckConstraint: condition=(AND: ('name__regex', '\\S')) name='warehouse_warehouse_name_text'>

Explicit indexes (FK/unique indexes are additional):

None.

## warehouse.StorageLocation (warehouse_storagelocation)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| warehouse | ForeignKey | FK warehouse.Warehouse; PROTECT |
| parent | ForeignKey | nullable; FK warehouse.StorageLocation; PROTECT |
| code | CharField(64) |  |
| name | CharField(200) |  |
| kind | CharField(16) | choices: AREA, RACK, SHELF, BIN |
| is_active | BooleanField | default: True |

Constraints:

- location_warehouse_code_unique: <UniqueConstraint: fields=('warehouse', 'code') name='location_warehouse_code_unique'>
- location_code_text: <CheckConstraint: condition=(AND: ('code__regex', '^[A-Z0-9][A-Z0-9_.-]*$')) name='location_code_text'>
- location_name_text: <CheckConstraint: condition=(AND: ('name__regex', '\\S')) name='location_name_text'>
- location_kind_valid: <CheckConstraint: condition=(AND: ('kind__in', ['AREA', 'RACK', 'SHELF', 'BIN'])) name='location_kind_valid'>
- location_not_self_parent: <CheckConstraint: condition=(NOT (AND: ('parent', F(pk)))) name='location_not_self_parent'>
- location_root_kind: <CheckConstraint: condition=(OR: ('parent__isnull', False), ('kind__in', [LocationKind.AREA, LocationKind.RACK])) name='location_root_kind'>

Explicit indexes (FK/unique indexes are additional):

- location_warehouse_parent: warehouse, parent; condition=None

## inventory.AssetCategory (inventory_assetcategory)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| code | CharField(64) | unique |
| name | CharField(200) |  |
| description | TextField |  |
| is_active | BooleanField | default: True |

Constraints:

- inventory_assetcategory_code_text: <CheckConstraint: condition=(AND: (NOT (AND: ('code', ''))), ('code__regex', '^[A-Z0-9][A-Z0-9_.-]*$')) name='inventory_assetcategory_code_text'>
- inventory_assetcategory_name_text: <CheckConstraint: condition=(AND: ('name__regex', '\\S')) name='inventory_assetcategory_name_text'>

Explicit indexes (FK/unique indexes are additional):

None.

## inventory.Manufacturer (inventory_manufacturer)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| code | CharField(64) | unique |
| name | CharField(200) |  |
| description | TextField |  |
| is_active | BooleanField | default: True |

Constraints:

- inventory_manufacturer_code_text: <CheckConstraint: condition=(AND: (NOT (AND: ('code', ''))), ('code__regex', '^[A-Z0-9][A-Z0-9_.-]*$')) name='inventory_manufacturer_code_text'>
- inventory_manufacturer_name_text: <CheckConstraint: condition=(AND: ('name__regex', '\\S')) name='inventory_manufacturer_name_text'>

Explicit indexes (FK/unique indexes are additional):

None.

## inventory.ProductModel (inventory_productmodel)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| sku_code | CharField(64) | unique |
| name | CharField(200) |  |
| category | ForeignKey | FK inventory.AssetCategory; PROTECT |
| manufacturer | ForeignKey | nullable; FK inventory.Manufacturer; PROTECT |
| model_number | CharField(160) |  |
| part_number | CharField(160) |  |
| tracking_mode | CharField(16) | choices: SERIALIZED, BULK |
| capacity_bytes | BigIntegerField | nullable |
| memory_generation | CharField(16) |  |
| interface_type | CharField(80) |  |
| speed_value | DecimalField(20,6) | nullable |
| speed_unit | CharField(24) |  |
| size_value | DecimalField(20,6) | nullable |
| size_unit | CharField(24) |  |
| port_count | PositiveIntegerField | nullable |
| description | TextField |  |
| is_active | BooleanField | default: True |

Constraints:

- product_tracking_valid: <CheckConstraint: condition=(AND: ('tracking_mode__in', ['SERIALIZED', 'BULK'])) name='product_tracking_valid'>
- product_sku_text: <CheckConstraint: condition=(AND: ('sku_code__regex', '^[A-Z0-9][A-Z0-9_.-]*$')) name='product_sku_text'>
- product_name_text: <CheckConstraint: condition=(AND: ('name__regex', '\\S')) name='product_name_text'>
- product_capacity_positive: <CheckConstraint: condition=(OR: ('capacity_bytes__isnull', True), ('capacity_bytes__gt', 0)) name='product_capacity_positive'>
- product_speed_positive: <CheckConstraint: condition=(OR: (AND: ('speed_unit', ''), ('speed_value__isnull', True)), (AND: ('speed_value__gt', 0), ('speed_value__isnull', False), (NOT (AND: ('speed_unit', ''))))) name='product_speed_positive'>
- product_size_positive: <CheckConstraint: condition=(OR: (AND: ('size_unit', ''), ('size_value__isnull', True)), (AND: ('size_value__gt', 0), ('size_value__isnull', False), (NOT (AND: ('size_unit', ''))))) name='product_size_positive'>

Explicit indexes (FK/unique indexes are additional):

- product_category_tracking: category, tracking_mode; condition=None

## inventory.SpecificationDefinition (inventory_specificationdefinition)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| code | CharField(64) | unique |
| name | CharField(200) |  |
| description | TextField |  |
| is_active | BooleanField | default: True |
| data_type | CharField(16) | choices: INTEGER, DECIMAL, TEXT, BOOLEAN |
| unit | CharField(24) |  |

Constraints:

- inventory_specificationdefinition_code_text: <CheckConstraint: condition=(AND: (NOT (AND: ('code', ''))), ('code__regex', '^[A-Z0-9][A-Z0-9_.-]*$')) name='inventory_specificationdefinition_code_text'>
- inventory_specificationdefinition_name_text: <CheckConstraint: condition=(AND: ('name__regex', '\\S')) name='inventory_specificationdefinition_name_text'>
- specification_type_valid: <CheckConstraint: condition=(AND: ('data_type__in', ['INTEGER', 'DECIMAL', 'TEXT', 'BOOLEAN'])) name='specification_type_valid'>

Explicit indexes (FK/unique indexes are additional):

None.

## inventory.Asset (inventory_asset)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| asset_tag | CharField(40) | unique; default: new_asset_tag |
| product_model | ForeignKey | FK inventory.ProductModel; PROTECT |
| device_name | CharField(200) |  |
| serial_raw | CharField(200) |  |
| serial_normalized | CharField(600) |  |
| serial_review_state | CharField(24) | choices: UNREVIEWED, VERIFIED, DUPLICATE, MISSING; default: UNREVIEWED |
| condition | CharField(24) | choices: NEW, USED, REFURBISHED, BROKEN, UNKNOWN; default: UNKNOWN |
| lifecycle_status | CharField(24) | choices: AVAILABLE, QUARANTINED, ASSIGNED, DISPOSED, LOST; default: QUARANTINED |
| current_location | ForeignKey | nullable; FK warehouse.StorageLocation; PROTECT |
| description | TextField |  |
| remarks | TextField |  |
| legacy_last_audit_date | DateField | nullable |

Constraints:

- asset_condition_valid: <CheckConstraint: condition=(AND: ('condition__in', ['NEW', 'USED', 'REFURBISHED', 'BROKEN', 'UNKNOWN'])) name='asset_condition_valid'>
- asset_lifecycle_valid: <CheckConstraint: condition=(AND: ('lifecycle_status__in', ['AVAILABLE', 'QUARANTINED', 'ASSIGNED', 'DISPOSED', 'LOST'])) name='asset_lifecycle_valid'>
- asset_serial_review_valid: <CheckConstraint: condition=(AND: ('serial_review_state__in', ['UNREVIEWED', 'VERIFIED', 'DUPLICATE', 'MISSING'])) name='asset_serial_review_valid'>
- asset_location_state: <CheckConstraint: condition=(OR: (AND: ('current_location__isnull', False), ('lifecycle_status__in', [LifecycleStatus.AVAILABLE, LifecycleStatus.QUARANTINED])), (AND: ('current_location__isnull', True), ('lifecycle_status__in', [LifecycleStatus.ASSIGNED, LifecycleStatus.DISPOSED, LifecycleStatus.LOST]))) name='asset_location_state'>
- asset_unusable_quarantined: <CheckConstraint: condition=(OR: (NOT (AND: ('condition__in', [Condition.BROKEN, Condition.UNKNOWN]))), (NOT (AND: ('lifecycle_status', LifecycleStatus.AVAILABLE)))) name='asset_unusable_quarantined'>
- asset_tag_text: <CheckConstraint: condition=(AND: ('asset_tag__regex', '\\S')) name='asset_tag_text'>
- asset_device_name_text: <CheckConstraint: condition=(AND: ('device_name__regex', '\\S')) name='asset_device_name_text'>

Explicit indexes (FK/unique indexes are additional):

- asset_product_lifecycle: product_model, lifecycle_status; condition=None
- asset_location_lifecycle: current_location, lifecycle_status; condition=None
- asset_serial_search: serial_normalized; condition=(NOT (AND: ('serial_normalized', '')))

## inventory.StockBalance (inventory_stockbalance)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| product_model | ForeignKey | FK inventory.ProductModel; PROTECT |
| location | ForeignKey | FK warehouse.StorageLocation; PROTECT |
| condition | CharField(24) | choices: NEW, USED, REFURBISHED, BROKEN, UNKNOWN; default: UNKNOWN |
| stock_state | CharField(24) | choices: AVAILABLE, QUARANTINED; default: QUARANTINED |
| quantity | BigIntegerField | default: 0 |

Constraints:

- stock_bucket_unique: <UniqueConstraint: fields=('product_model', 'location', 'condition', 'stock_state') name='stock_bucket_unique'>
- stock_quantity_nonnegative: <CheckConstraint: condition=(AND: ('quantity__gte', 0)) name='stock_quantity_nonnegative'>
- stock_condition_valid: <CheckConstraint: condition=(AND: ('condition__in', ['NEW', 'USED', 'REFURBISHED', 'BROKEN', 'UNKNOWN'])) name='stock_condition_valid'>
- stock_state_valid: <CheckConstraint: condition=(AND: ('stock_state__in', ['AVAILABLE', 'QUARANTINED'])) name='stock_state_valid'>
- stock_unusable_quarantined: <CheckConstraint: condition=(OR: (NOT (AND: ('condition__in', [Condition.BROKEN, Condition.UNKNOWN]))), ('stock_state', StockState.QUARANTINED)) name='stock_unusable_quarantined'>

Explicit indexes (FK/unique indexes are additional):

- stock_location_state_condition: location, stock_state, condition; condition=None
- stock_product_state: product_model, stock_state; condition=None

## inventory.StockThreshold (inventory_stockthreshold)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| product_model | ForeignKey | FK inventory.ProductModel; PROTECT |
| warehouse | ForeignKey | FK warehouse.Warehouse; PROTECT |
| minimum_quantity | BigIntegerField | default: 0 |

Constraints:

- threshold_product_site_unique: <UniqueConstraint: fields=('product_model', 'warehouse') name='threshold_product_site_unique'>
- threshold_nonnegative: <CheckConstraint: condition=(AND: ('minimum_quantity__gte', 0)) name='threshold_nonnegative'>

Explicit indexes (FK/unique indexes are additional):

None.

## inventory.AssetSpecification (inventory_assetspecification)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| definition | ForeignKey | FK inventory.SpecificationDefinition; PROTECT |
| product_model | ForeignKey | nullable; FK inventory.ProductModel; PROTECT |
| asset | ForeignKey | nullable; FK inventory.Asset; PROTECT |
| integer_value | BigIntegerField | nullable |
| decimal_value | DecimalField(20,6) | nullable |
| text_value | TextField | nullable |
| boolean_value | BooleanField | nullable |

Constraints:

- specification_owner_xor: <CheckConstraint: condition=(OR: (AND: ('asset__isnull', True), ('product_model__isnull', False)), (AND: ('asset__isnull', False), ('product_model__isnull', True))) name='specification_owner_xor'>
- specification_one_value: <CheckConstraint: condition=(OR: (AND: ('boolean_value__isnull', True), ('decimal_value__isnull', True), ('integer_value__isnull', False), ('text_value__isnull', True)), (AND: ('boolean_value__isnull', True), ('decimal_value__isnull', False), ('integer_value__isnull', True), ('text_value__isnull', True)), (AND: ('boolean_value__isnull', True), ('decimal_value__isnull', True), ('integer_value__isnull', True), ('text_value__isnull', False)), (AND: ('boolean_value__isnull', False), ('decimal_value__isnull', True), ('integer_value__isnull', True), ('text_value__isnull', True))) name='specification_one_value'>
- specification_product_unique: <UniqueConstraint: fields=('product_model', 'definition') name='specification_product_unique' condition=(AND: ('product_model__isnull', False))>
- specification_asset_unique: <UniqueConstraint: fields=('asset', 'definition') name='specification_asset_unique' condition=(AND: ('asset__isnull', False))>

Explicit indexes (FK/unique indexes are additional):

None.

## inventory.ImportBatch (inventory_importbatch)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| public_id | UUIDField(32) | unique; default: uuid4 |
| original_filename | CharField(255) |  |
| file_sha256 | CharField(64) |  |
| source_storage_key | CharField(255) |  |
| uploaded_by | ForeignKey | FK auth.User; PROTECT |
| uploaded_at | DateTimeField | default: now |
| mapping_version | CharField(64) |  |
| source_timezone | CharField(64) | default: Asia/Tokyo |
| status | CharField(24) | choices: UPLOADED, VALIDATED, IN_REVIEW, APPROVED, PROMOTED, FAILED, REJECTED; default: UPLOADED |
| reviewed_by | ForeignKey | nullable; FK auth.User; PROTECT |
| reviewed_at | DateTimeField | nullable |
| approved_preview_digest | CharField(64) |  |
| notes | TextField |  |

Constraints:

- batch_status_valid: <CheckConstraint: condition=(AND: ('status__in', ['UPLOADED', 'VALIDATED', 'IN_REVIEW', 'APPROVED', 'PROMOTED', 'FAILED', 'REJECTED'])) name='batch_status_valid'>
- batch_hash_valid: <CheckConstraint: condition=(AND: ('file_sha256__regex', '^[0-9a-f]{64}$')) name='batch_hash_valid'>
- batch_digest_valid: <CheckConstraint: condition=(OR: ('approved_preview_digest', ''), ('approved_preview_digest__regex', '^[0-9a-f]{64}$')) name='batch_digest_valid'>
- batch_review_pair: <CheckConstraint: condition=(OR: (AND: ('reviewed_at__isnull', True), ('reviewed_by__isnull', True)), (AND: ('reviewed_at__isnull', False), ('reviewed_by__isnull', False))) name='batch_review_pair'>
- batch_separate_reviewer: <CheckConstraint: condition=(OR: ('reviewed_by__isnull', True), (NOT (AND: ('reviewed_by', F(uploaded_by))))) name='batch_separate_reviewer'>
- batch_review_date_order: <CheckConstraint: condition=(OR: ('reviewed_at__isnull', True), ('reviewed_at__gte', F(uploaded_at))) name='batch_review_date_order'>
- batch_approval_evidence: <CheckConstraint: condition=(OR: (NOT (AND: ('status__in', [BatchStatus.APPROVED, BatchStatus.PROMOTED]))), (AND: ('reviewed_at__isnull', False), ('reviewed_by__isnull', False), (NOT (AND: ('approved_preview_digest', ''))))) name='batch_approval_evidence'>

Explicit indexes (FK/unique indexes are additional):

None.

## inventory.ImportStagingRecord (inventory_importstagingrecord)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| batch | ForeignKey | FK inventory.ImportBatch; PROTECT |
| worksheet_name | CharField(255) |  |
| excel_row_number | PositiveIntegerField |  |
| raw_values | JSONField | default: list |
| normalized_values | JSONField | default: dict |
| validation_errors | JSONField | default: list |
| validation_warnings | JSONField | default: list |
| status | CharField(24) | choices: CAPTURED, INVALID, READY, IGNORED, APPROVED, PROMOTED, REJECTED; default: CAPTURED |
| asset | ForeignKey | nullable; FK inventory.Asset; PROTECT |
| stock_balance | ForeignKey | nullable; FK inventory.StockBalance; PROTECT |
| source_row_digest | CharField(64) |  |
| promoted_at | DateTimeField | nullable |

Constraints:

- staging_source_row_unique: <UniqueConstraint: fields=('batch', 'worksheet_name', 'excel_row_number') name='staging_source_row_unique'>
- staging_row_positive: <CheckConstraint: condition=(AND: ('excel_row_number__gte', 1)) name='staging_row_positive'>
- staging_sheet_text: <CheckConstraint: condition=(AND: ('worksheet_name__regex', '\\S')) name='staging_sheet_text'>
- staging_status_valid: <CheckConstraint: condition=(AND: ('status__in', ['CAPTURED', 'INVALID', 'READY', 'IGNORED', 'APPROVED', 'PROMOTED', 'REJECTED'])) name='staging_status_valid'>
- staging_digest_valid: <CheckConstraint: condition=(AND: ('source_row_digest__regex', '^[0-9a-f]{64}$')) name='staging_digest_valid'>
- staging_target_state: <CheckConstraint: condition=(OR: (AND: ('promoted_at__isnull', False), ('status', RowStatus.PROMOTED), (OR: (AND: ('asset__isnull', False), ('stock_balance__isnull', True)), (AND: ('asset__isnull', True), ('stock_balance__isnull', False)))), (AND: (NOT (AND: ('status', RowStatus.PROMOTED))), ('asset__isnull', True), ('promoted_at__isnull', True), ('stock_balance__isnull', True))) name='staging_target_state'>

Explicit indexes (FK/unique indexes are additional):

- staging_batch_status: batch, status; condition=None

## audits.PhysicalInventoryAudit (audits_physicalinventoryaudit)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| public_id | UUIDField(32) | unique; default: uuid4 |
| scope_location | ForeignKey | FK warehouse.StorageLocation; PROTECT |
| include_descendants | BooleanField | default: True |
| status | CharField(24) | choices: DRAFT, COUNTING, SUBMITTED, APPROVED, REJECTED, CANCELLED; default: DRAFT |
| planned_date | DateField |  |
| started_at | DateTimeField | nullable |
| submitted_at | DateTimeField | nullable |
| approved_at | DateTimeField | nullable |
| performed_by | ForeignKey | FK auth.User; PROTECT |
| approved_by | ForeignKey | nullable; FK auth.User; PROTECT |
| notes | TextField |  |

Constraints:

- audit_status_valid: <CheckConstraint: condition=(AND: ('status__in', ['DRAFT', 'COUNTING', 'SUBMITTED', 'APPROVED', 'REJECTED', 'CANCELLED'])) name='audit_status_valid'>
- audit_separate_approver: <CheckConstraint: condition=(OR: ('approved_by__isnull', True), (NOT (AND: ('approved_by', F(performed_by))))) name='audit_separate_approver'>
- audit_approval_pair: <CheckConstraint: condition=(OR: (AND: ('approved_at__isnull', True), ('approved_by__isnull', True)), (AND: ('approved_at__isnull', False), ('approved_by__isnull', False))) name='audit_approval_pair'>
- audit_approved_evidence: <CheckConstraint: condition=(OR: (NOT (AND: ('status', AuditStatus.APPROVED))), (AND: ('approved_at__isnull', False), ('approved_by__isnull', False), ('started_at__isnull', False), ('submitted_at__isnull', False))) name='audit_approved_evidence'>
- audit_counting_started: <CheckConstraint: condition=(OR: (NOT (AND: ('status__in', [AuditStatus.COUNTING, AuditStatus.SUBMITTED]))), ('started_at__isnull', False)) name='audit_counting_started'>
- audit_submitted_time: <CheckConstraint: condition=(OR: (NOT (AND: ('status', AuditStatus.SUBMITTED))), ('submitted_at__isnull', False)) name='audit_submitted_time'>
- audit_submission_order: <CheckConstraint: condition=(OR: ('submitted_at__isnull', True), (AND: ('started_at__isnull', False), ('submitted_at__gte', F(started_at)))) name='audit_submission_order'>
- audit_approval_order: <CheckConstraint: condition=(OR: ('approved_at__isnull', True), (AND: ('approved_at__gte', F(submitted_at)), ('submitted_at__isnull', False))) name='audit_approval_order'>

Explicit indexes (FK/unique indexes are additional):

- audit_status_started: status, started_at; condition=None

## audits.AuditLine (audits_auditline)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| audit | ForeignKey | FK audits.PhysicalInventoryAudit; PROTECT |
| asset | ForeignKey | nullable; FK inventory.Asset; PROTECT |
| product_model | ForeignKey | nullable; FK inventory.ProductModel; PROTECT |
| stock_balance | ForeignKey | nullable; FK inventory.StockBalance; PROTECT |
| expected_location | ForeignKey | nullable; FK warehouse.StorageLocation; PROTECT |
| location | ForeignKey | FK warehouse.StorageLocation; PROTECT |
| expected_quantity | BigIntegerField |  |
| observed_quantity | BigIntegerField | nullable |
| expected_condition | CharField(24) | choices: NEW, USED, REFURBISHED, BROKEN, UNKNOWN |
| observed_condition | CharField(24) | nullable; choices: NEW, USED, REFURBISHED, BROKEN, UNKNOWN |
| expected_stock_state | CharField(24) | nullable; choices: AVAILABLE, QUARANTINED |
| observed_stock_state | CharField(24) | nullable; choices: AVAILABLE, QUARANTINED |
| outcome | CharField(24) | choices: MATCH, MISSING, EXCESS, DAMAGED, MISPLACED, UNCOUNTED; default: UNCOUNTED |
| counted_by | ForeignKey | nullable; FK auth.User; PROTECT |
| counted_at | DateTimeField | nullable |
| notes | TextField |  |

Constraints:

- audit_line_target_xor: <CheckConstraint: condition=(OR: (AND: ('asset__isnull', False), ('product_model__isnull', True)), (AND: ('asset__isnull', True), ('product_model__isnull', False))) name='audit_line_target_xor'>
- audit_line_nonnegative: <CheckConstraint: condition=(AND: ('expected_quantity__gte', 0), (OR: ('observed_quantity__isnull', True), ('observed_quantity__gte', 0))) name='audit_line_nonnegative'>
- audit_asset_counts: <CheckConstraint: condition=(OR: ('asset__isnull', True), (AND: ('expected_quantity__in', [0, 1]), (OR: ('observed_quantity__isnull', True), ('observed_quantity__in', [0, 1])))) name='audit_asset_counts'>
- audit_line_bucket_type: <CheckConstraint: condition=(OR: (AND: ('asset__isnull', True), ('expected_stock_state__isnull', False)), (AND: ('expected_stock_state__isnull', True), ('observed_stock_state__isnull', True), ('stock_balance__isnull', True))) name='audit_line_bucket_type'>
- audit_line_count_evidence: <CheckConstraint: condition=(OR: (AND: ('counted_at__isnull', True), ('counted_by__isnull', True), ('observed_quantity__isnull', True), ('outcome', AuditOutcome.UNCOUNTED)), (AND: ('counted_at__isnull', False), ('counted_by__isnull', False), ('observed_quantity__isnull', False), (NOT (AND: ('outcome', AuditOutcome.UNCOUNTED))))) name='audit_line_count_evidence'>
- audit_outcome_valid: <CheckConstraint: condition=(AND: ('outcome__in', ['MATCH', 'MISSING', 'EXCESS', 'DAMAGED', 'MISPLACED', 'UNCOUNTED'])) name='audit_outcome_valid'>
- audit_expected_condition: <CheckConstraint: condition=(AND: ('expected_condition__in', ['NEW', 'USED', 'REFURBISHED', 'BROKEN', 'UNKNOWN'])) name='audit_expected_condition'>
- audit_observed_condition: <CheckConstraint: condition=(OR: ('observed_condition__in', ['NEW', 'USED', 'REFURBISHED', 'BROKEN', 'UNKNOWN']), ('observed_condition__isnull', True)) name='audit_observed_condition'>
- audit_expected_stock_state: <CheckConstraint: condition=(OR: ('expected_stock_state__in', ['AVAILABLE', 'QUARANTINED']), ('expected_stock_state__isnull', True)) name='audit_expected_stock_state'>
- audit_observed_stock_state: <CheckConstraint: condition=(OR: ('observed_stock_state__in', ['AVAILABLE', 'QUARANTINED']), ('observed_stock_state__isnull', True)) name='audit_observed_stock_state'>
- audit_asset_unique: <UniqueConstraint: fields=('audit', 'asset') name='audit_asset_unique' condition=(AND: ('asset__isnull', False))>
- audit_bucket_unique: <UniqueConstraint: fields=('audit', 'stock_balance') name='audit_bucket_unique' condition=(AND: ('stock_balance__isnull', False))>
- audit_excess_bucket_unique: <UniqueConstraint: fields=('audit', 'product_model', 'location', 'expected_condition', 'expected_stock_state') name='audit_excess_bucket_unique' condition=(AND: ('asset__isnull', True), ('stock_balance__isnull', True)) nulls_distinct=False>

Explicit indexes (FK/unique indexes are additional):

None.

## audits.AssetChangeLog (audits_assetchangelog)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| public_id | UUIDField(32) | unique; default: uuid4 |
| entity_kind | CharField(64) |  |
| entity_pk | PositiveBigIntegerField |  |
| asset | ForeignKey | nullable; FK inventory.Asset; PROTECT |
| actor | ForeignKey | FK auth.User; PROTECT |
| action | CharField(40) |  |
| recorded_at | DateTimeField | default: now |
| operation_key | UUIDField(32) | nullable |
| before | JSONField | default: dict |
| after | JSONField | default: dict |
| reason | TextField |  |

Constraints:

- changelog_entity_positive: <CheckConstraint: condition=(AND: ('entity_pk__gt', 0)) name='changelog_entity_positive'>
- changelog_entity_text: <CheckConstraint: condition=(AND: ('entity_kind__regex', '\\S')) name='changelog_entity_text'>
- changelog_action_text: <CheckConstraint: condition=(AND: ('action__regex', '\\S')) name='changelog_action_text'>
- changelog_reason_text: <CheckConstraint: condition=(AND: ('reason__regex', '\\S')) name='changelog_reason_text'>

Explicit indexes (FK/unique indexes are additional):

- change_entity_time: entity_kind, entity_pk, recorded_at; condition=None

## transactions.StockMovement (transactions_stockmovement)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| public_id | UUIDField(32) | unique; default: uuid4 |
| operation_key | UUIDField(32) | default: uuid4 |
| line_number | PositiveIntegerField | default: 1 |
| operation_type | CharField(24) | choices: STOCK_IN, STOCK_OUT, TRANSFER, RETURN, ADJUSTMENT_IN, ADJUSTMENT_OUT, DISPOSAL |
| asset | ForeignKey | nullable; FK inventory.Asset; PROTECT |
| product_model | ForeignKey | nullable; FK inventory.ProductModel; PROTECT |
| quantity | BigIntegerField |  |
| source_location | ForeignKey | nullable; FK warehouse.StorageLocation; PROTECT |
| destination_location | ForeignKey | nullable; FK warehouse.StorageLocation; PROTECT |
| source_balance | ForeignKey | nullable; FK inventory.StockBalance; PROTECT |
| destination_balance | ForeignKey | nullable; FK inventory.StockBalance; PROTECT |
| condition_before | CharField(24) | nullable; choices: NEW, USED, REFURBISHED, BROKEN, UNKNOWN |
| condition_after | CharField(24) | nullable; choices: NEW, USED, REFURBISHED, BROKEN, UNKNOWN |
| lifecycle_before | CharField(24) | nullable; choices: AVAILABLE, QUARANTINED, ASSIGNED, DISPOSED, LOST |
| lifecycle_after | CharField(24) | nullable; choices: AVAILABLE, QUARANTINED, ASSIGNED, DISPOSED, LOST |
| actor | ForeignKey | FK auth.User; PROTECT |
| occurred_at | DateTimeField | default: now |
| recorded_at | DateTimeField | default: now |
| reason | TextField |  |
| external_reference | CharField(160) |  |
| reverses | ForeignKey | nullable; FK transactions.StockMovement; PROTECT |
| audit_line | ForeignKey | nullable; FK audits.AuditLine; PROTECT |
| import_row | OneToOneField | unique; nullable; FK inventory.ImportStagingRecord; PROTECT |

Constraints:

- movement_operation_line_unique: <UniqueConstraint: fields=('operation_key', 'line_number') name='movement_operation_line_unique'>
- movement_positive_quantity: <CheckConstraint: condition=(AND: ('quantity__gt', 0)) name='movement_positive_quantity'>
- movement_positive_line: <CheckConstraint: condition=(AND: ('line_number__gte', 1)) name='movement_positive_line'>
- movement_target_xor: <CheckConstraint: condition=(OR: (AND: ('asset__isnull', False), ('product_model__isnull', True)), (AND: ('asset__isnull', True), ('product_model__isnull', False))) name='movement_target_xor'>
- movement_type_valid: <CheckConstraint: condition=(AND: ('operation_type__in', ['STOCK_IN', 'STOCK_OUT', 'TRANSFER', 'RETURN', 'ADJUSTMENT_IN', 'ADJUSTMENT_OUT', 'DISPOSAL'])) name='movement_type_valid'>
- movement_condition_before: <CheckConstraint: condition=(OR: ('condition_before__in', ['NEW', 'USED', 'REFURBISHED', 'BROKEN', 'UNKNOWN']), ('condition_before__isnull', True)) name='movement_condition_before'>
- movement_condition_after: <CheckConstraint: condition=(OR: ('condition_after__in', ['NEW', 'USED', 'REFURBISHED', 'BROKEN', 'UNKNOWN']), ('condition_after__isnull', True)) name='movement_condition_after'>
- movement_lifecycle_before: <CheckConstraint: condition=(OR: ('lifecycle_before__in', ['AVAILABLE', 'QUARANTINED', 'ASSIGNED', 'DISPOSED', 'LOST']), ('lifecycle_before__isnull', True)) name='movement_lifecycle_before'>
- movement_lifecycle_after: <CheckConstraint: condition=(OR: ('lifecycle_after__in', ['AVAILABLE', 'QUARANTINED', 'ASSIGNED', 'DISPOSED', 'LOST']), ('lifecycle_after__isnull', True)) name='movement_lifecycle_after'>
- movement_reason_text: <CheckConstraint: condition=(AND: ('reason__regex', '\\S')) name='movement_reason_text'>
- movement_asset_shape: <CheckConstraint: condition=(OR: ('asset__isnull', True), (AND: ('destination_balance__isnull', True), ('quantity', 1), ('source_balance__isnull', True))) name='movement_asset_shape'>
- movement_bulk_snapshots: <CheckConstraint: condition=(OR: ('asset__isnull', False), (AND: ('condition_after__isnull', True), ('condition_before__isnull', True), ('lifecycle_after__isnull', True), ('lifecycle_before__isnull', True))) name='movement_bulk_snapshots'>
- movement_direction: <CheckConstraint: condition=(OR: (AND: ('destination_location__isnull', False), ('operation_type__in', [MovementType.STOCK_IN, MovementType.RETURN, MovementType.ADJUSTMENT_IN]), ('source_location__isnull', True)), (AND: ('destination_location__isnull', True), ('operation_type__in', [MovementType.STOCK_OUT, MovementType.DISPOSAL, MovementType.ADJUSTMENT_OUT]), ('source_location__isnull', False)), (AND: ('destination_location__isnull', False), ('operation_type', MovementType.TRANSFER), ('source_location__isnull', False))) name='movement_direction'>
- movement_bulk_source: <CheckConstraint: condition=(OR: ('asset__isnull', False), (AND: ('source_balance__isnull', True), ('source_location__isnull', True)), (AND: ('source_balance__isnull', False), ('source_location__isnull', False))) name='movement_bulk_source'>
- movement_bulk_destination: <CheckConstraint: condition=(OR: ('asset__isnull', False), (AND: ('destination_balance__isnull', True), ('destination_location__isnull', True)), (AND: ('destination_balance__isnull', False), ('destination_location__isnull', False))) name='movement_bulk_destination'>
- movement_not_noop_transfer: <CheckConstraint: condition=(OR: (NOT (AND: ('operation_type', MovementType.TRANSFER))), (NOT (AND: ('source_location', F(destination_location)))), (AND: ('destination_balance__isnull', False), ('source_balance__isnull', False), (NOT (AND: ('source_balance', F(destination_balance)))))) name='movement_not_noop_transfer'>
- movement_not_self_reverse: <CheckConstraint: condition=(NOT (AND: ('reverses', F(pk)))) name='movement_not_self_reverse'>

Explicit indexes (FK/unique indexes are additional):

- movement_asset_recorded: asset, recorded_at, id; condition=None
- movement_product_occurred: product_model, occurred_at; condition=None
- movement_source_occurred: source_location, occurred_at; condition=None
- movement_dest_occurred: destination_location, occurred_at; condition=None

## transactions.AssetAssignment (transactions_assetassignment)

| Field | Type | Properties |
| --- | --- | --- |
| id | BigAutoField | PK; unique |
| created_at | DateTimeField |  |
| updated_at | DateTimeField |  |
| version | PositiveBigIntegerField | default: 0 |
| asset | ForeignKey | FK inventory.Asset; PROTECT |
| recipient | ForeignKey | FK accounts.AssetRecipient; PROTECT |
| destination_description | TextField |  |
| destination_reference | CharField(200) |  |
| issued_by | ForeignKey | FK auth.User; PROTECT |
| assigned_at | DateTimeField | default: now |
| due_at | DateTimeField | nullable |
| returned_at | DateTimeField | nullable |
| returned_by | ForeignKey | nullable; FK auth.User; PROTECT |
| issue_movement | OneToOneField | unique; FK transactions.StockMovement; PROTECT |
| return_movement | OneToOneField | unique; nullable; FK transactions.StockMovement; PROTECT |
| purpose | TextField |  |

Constraints:

- assignment_one_open_asset: <UniqueConstraint: fields=('asset',) name='assignment_one_open_asset' condition=(AND: ('returned_at__isnull', True))>
- assignment_due_order: <CheckConstraint: condition=(OR: ('due_at__isnull', True), ('due_at__gte', F(assigned_at))) name='assignment_due_order'>
- assignment_return_order: <CheckConstraint: condition=(OR: ('returned_at__isnull', True), ('returned_at__gte', F(assigned_at))) name='assignment_return_order'>
- assignment_return_fields: <CheckConstraint: condition=(OR: (AND: ('return_movement__isnull', True), ('returned_at__isnull', True), ('returned_by__isnull', True)), (AND: ('return_movement__isnull', False), ('returned_at__isnull', False), ('returned_by__isnull', False))) name='assignment_return_fields'>

Explicit indexes (FK/unique indexes are additional):

- assignment_recipient_return: recipient, returned_at; condition=None
