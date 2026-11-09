"""Catalog, serialized equipment, bulk positions and import provenance."""
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.common import NamedMaster, TimestampedModel, check, enum_check, related_or_error, require_tracking, xor_fields
from .choices import (
    BatchStatus, Condition, LifecycleStatus, RowStatus, SerialReviewState,
    SpecificationType, StockState, TrackingMode,
)


def new_asset_tag():
    return f"AST-{uuid.uuid4().hex.upper()}"


def position_checks():
    return [
        enum_check("asset_condition_valid", "condition", Condition),
        enum_check("asset_lifecycle_valid", "lifecycle_status", LifecycleStatus),
        enum_check("asset_serial_review_valid", "serial_review_state", SerialReviewState),
        check("asset_location_state", (
            Q(lifecycle_status__in=[LifecycleStatus.AVAILABLE, LifecycleStatus.QUARANTINED], current_location__isnull=False)
            | Q(lifecycle_status__in=[LifecycleStatus.ASSIGNED, LifecycleStatus.DISPOSED, LifecycleStatus.LOST], current_location__isnull=True)
        )),
        check("asset_unusable_quarantined", ~Q(condition__in=[Condition.BROKEN, Condition.UNKNOWN])
              | ~Q(lifecycle_status=LifecycleStatus.AVAILABLE)),
    ]


class AssetCategory(NamedMaster):
    pass


class Manufacturer(NamedMaster):
    pass


class ProductModel(TimestampedModel):
    sku_code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(AssetCategory, on_delete=models.PROTECT, related_name="products")
    manufacturer = models.ForeignKey(Manufacturer, on_delete=models.PROTECT, null=True, blank=True, related_name="products")
    model_number = models.CharField(max_length=160, blank=True)
    part_number = models.CharField(max_length=160, blank=True)
    tracking_mode = models.CharField(max_length=16, choices=TrackingMode.choices)
    capacity_bytes = models.BigIntegerField(null=True, blank=True)
    memory_generation = models.CharField(max_length=16, blank=True)
    interface_type = models.CharField(max_length=80, blank=True)
    speed_value = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    speed_unit = models.CharField(max_length=24, blank=True)
    size_value = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    size_unit = models.CharField(max_length=24, blank=True)
    port_count = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            enum_check("product_tracking_valid", "tracking_mode", TrackingMode),
            check("product_sku_text", Q(sku_code__regex=r"^[A-Z0-9][A-Z0-9_.-]*$")),
            check("product_name_text", Q(name__regex=r"\S")),
            check("product_capacity_positive", Q(capacity_bytes__isnull=True) | Q(capacity_bytes__gt=0)),
            check("product_speed_positive", Q(speed_value__isnull=True, speed_unit="") | (Q(speed_value__isnull=False, speed_value__gt=0) & ~Q(speed_unit=""))),
            check("product_size_positive", Q(size_value__isnull=True, size_unit="") | (Q(size_value__isnull=False, size_value__gt=0) & ~Q(size_unit=""))),
        ]
        indexes = [models.Index(fields=["category", "tracking_mode"], name="product_category_tracking")]

    def __str__(self):
        return self.sku_code


class SpecificationDefinition(NamedMaster):
    data_type = models.CharField(max_length=16, choices=SpecificationType.choices)
    unit = models.CharField(max_length=24, blank=True)

    class Meta(NamedMaster.Meta):
        constraints = NamedMaster.Meta.constraints + [
            enum_check("specification_type_valid", "data_type", SpecificationType),
        ]


class Asset(TimestampedModel):
    asset_tag = models.CharField(max_length=40, unique=True, default=new_asset_tag, editable=False)
    product_model = models.ForeignKey(ProductModel, on_delete=models.PROTECT, related_name="assets")
    device_name = models.CharField(max_length=200)
    serial_raw = models.CharField(max_length=200, blank=True)
    serial_normalized = models.CharField(max_length=600, blank=True, editable=False)
    serial_review_state = models.CharField(max_length=24, choices=SerialReviewState.choices, default=SerialReviewState.UNREVIEWED)
    condition = models.CharField(max_length=24, choices=Condition.choices, default=Condition.UNKNOWN)
    lifecycle_status = models.CharField(max_length=24, choices=LifecycleStatus.choices, default=LifecycleStatus.QUARANTINED)
    current_location = models.ForeignKey("warehouse.StorageLocation", on_delete=models.PROTECT, null=True, blank=True, related_name="assets")
    description = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    legacy_last_audit_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = position_checks() + [
            check("asset_tag_text", Q(asset_tag__regex=r"\S")),
            check("asset_device_name_text", Q(device_name__regex=r"\S")),
        ]
        indexes = [
            models.Index(fields=["product_model", "lifecycle_status"], name="asset_product_lifecycle"),
            models.Index(fields=["current_location", "lifecycle_status"], name="asset_location_lifecycle"),
            models.Index(fields=["serial_normalized"], condition=~Q(serial_normalized=""), name="asset_serial_search"),
        ]

    def clean(self):
        super().clean()
        self.serial_normalized = self.serial_raw.strip().casefold()
        if self.product_model_id:
            require_tracking(related_or_error(self, "product_model"), TrackingMode.SERIALIZED)
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values_list("asset_tag", flat=True).first()
            if previous is not None and previous != self.asset_tag:
                raise ValidationError({"asset_tag": "Internal asset tags are immutable."})
        if self.current_location_id and not related_or_error(self, "current_location").is_active:
            raise ValidationError({"current_location": "Choose an active storage location."})

    def save(self, *args, **kwargs):
        self.serial_normalized = self.serial_raw.strip().casefold()
        if kwargs.get("update_fields") is not None and "serial_raw" in kwargs["update_fields"]:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"serial_normalized"}
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.asset_tag


class StockBalance(TimestampedModel):
    product_model = models.ForeignKey(ProductModel, on_delete=models.PROTECT, related_name="stock_balances")
    location = models.ForeignKey("warehouse.StorageLocation", on_delete=models.PROTECT, related_name="stock_balances")
    condition = models.CharField(max_length=24, choices=Condition.choices, default=Condition.UNKNOWN)
    stock_state = models.CharField(max_length=24, choices=StockState.choices, default=StockState.QUARANTINED)
    quantity = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product_model", "location", "condition", "stock_state"], name="stock_bucket_unique"),
            check("stock_quantity_nonnegative", Q(quantity__gte=0)),
            enum_check("stock_condition_valid", "condition", Condition),
            enum_check("stock_state_valid", "stock_state", StockState),
            check("stock_unusable_quarantined", ~Q(condition__in=[Condition.BROKEN, Condition.UNKNOWN]) | Q(stock_state=StockState.QUARANTINED)),
        ]
        indexes = [
            models.Index(fields=["location", "stock_state", "condition"], name="stock_location_state_condition"),
            models.Index(fields=["product_model", "stock_state"], name="stock_product_state"),
        ]

    def clean(self):
        super().clean()
        if self.product_model_id:
            require_tracking(related_or_error(self, "product_model"), TrackingMode.BULK)
        if self.location_id and not related_or_error(self, "location").is_active:
            raise ValidationError({"location": "Choose an active storage location."})


class StockThreshold(TimestampedModel):
    product_model = models.ForeignKey(ProductModel, on_delete=models.PROTECT, related_name="stock_thresholds")
    warehouse = models.ForeignKey("warehouse.Warehouse", on_delete=models.PROTECT, related_name="stock_thresholds")
    minimum_quantity = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product_model", "warehouse"], name="threshold_product_site_unique"),
            check("threshold_nonnegative", Q(minimum_quantity__gte=0)),
        ]

    def clean(self):
        super().clean()
        if self.product_model_id:
            require_tracking(related_or_error(self, "product_model"), TrackingMode.BULK)


class AssetSpecification(TimestampedModel):
    definition = models.ForeignKey(SpecificationDefinition, on_delete=models.PROTECT, related_name="values")
    product_model = models.ForeignKey(ProductModel, on_delete=models.PROTECT, null=True, blank=True, related_name="specifications")
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, null=True, blank=True, related_name="specifications")
    integer_value = models.BigIntegerField(null=True, blank=True)
    decimal_value = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    text_value = models.TextField(null=True, blank=True)
    boolean_value = models.BooleanField(null=True, blank=True)

    class Meta:
        constraints = [
            check("specification_owner_xor", xor_fields("product_model", "asset")),
            check("specification_one_value", (
                Q(integer_value__isnull=False, decimal_value__isnull=True, text_value__isnull=True, boolean_value__isnull=True)
                | Q(integer_value__isnull=True, decimal_value__isnull=False, text_value__isnull=True, boolean_value__isnull=True)
                | Q(integer_value__isnull=True, decimal_value__isnull=True, text_value__isnull=False, boolean_value__isnull=True)
                | Q(integer_value__isnull=True, decimal_value__isnull=True, text_value__isnull=True, boolean_value__isnull=False)
            )),
            models.UniqueConstraint(fields=["product_model", "definition"], condition=Q(product_model__isnull=False), name="specification_product_unique"),
            models.UniqueConstraint(fields=["asset", "definition"], condition=Q(asset__isnull=False), name="specification_asset_unique"),
        ]

    def clean(self):
        super().clean()
        owners = int(self.product_model_id is not None) + int(self.asset_id is not None)
        if owners != 1:
            raise ValidationError("Specify exactly one catalog or asset owner.")
        fields = {"INTEGER": "integer_value", "DECIMAL": "decimal_value", "TEXT": "text_value", "BOOLEAN": "boolean_value"}
        present = [field for field in fields.values() if getattr(self, field) is not None]
        if len(present) != 1:
            raise ValidationError("Specify exactly one typed value.")
        if self.definition_id and present[0] != fields[self.definition.data_type]:
            raise ValidationError({present[0]: "Value type must match the specification definition."})


sha256_validator = RegexValidator(r"^[0-9a-f]{64}$", "Use a lowercase SHA-256 hex digest.")


class ImportBatch(TimestampedModel):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    original_filename = models.CharField(max_length=255)
    file_sha256 = models.CharField(max_length=64, validators=[sha256_validator], db_index=True)
    source_storage_key = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="inventory_imports")
    uploaded_at = models.DateTimeField(default=timezone.now)
    mapping_version = models.CharField(max_length=64)
    source_timezone = models.CharField(max_length=64, default="Asia/Tokyo")
    status = models.CharField(max_length=24, choices=BatchStatus.choices, default=BatchStatus.UPLOADED)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="reviewed_inventory_imports")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_preview_digest = models.CharField(max_length=64, blank=True, validators=[sha256_validator])
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            enum_check("batch_status_valid", "status", BatchStatus),
            check("batch_hash_valid", Q(file_sha256__regex=r"^[0-9a-f]{64}$")),
            check("batch_digest_valid", Q(approved_preview_digest="") | Q(approved_preview_digest__regex=r"^[0-9a-f]{64}$")),
            check("batch_review_pair", Q(reviewed_by__isnull=True, reviewed_at__isnull=True) | Q(reviewed_by__isnull=False, reviewed_at__isnull=False)),
            check("batch_separate_reviewer", Q(reviewed_by__isnull=True) | ~Q(reviewed_by=F("uploaded_by"))),
            check("batch_review_date_order", Q(reviewed_at__isnull=True) | Q(reviewed_at__gte=F("uploaded_at"))),
            check("batch_approval_evidence", ~Q(status__in=[BatchStatus.APPROVED, BatchStatus.PROMOTED]) | (Q(reviewed_by__isnull=False, reviewed_at__isnull=False) & ~Q(approved_preview_digest=""))),
        ]
        permissions = [("review_import", "Can review import previews"), ("promote_import", "Can promote approved imports")]


class ImportStagingRecord(TimestampedModel):
    batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, related_name="rows")
    worksheet_name = models.CharField(max_length=255)
    excel_row_number = models.PositiveIntegerField()
    raw_values = models.JSONField(default=list, blank=True)
    normalized_values = models.JSONField(default=dict, blank=True)
    validation_errors = models.JSONField(default=list, blank=True)
    validation_warnings = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=24, choices=RowStatus.choices, default=RowStatus.CAPTURED)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, null=True, blank=True, related_name="import_rows")
    stock_balance = models.ForeignKey(StockBalance, on_delete=models.PROTECT, null=True, blank=True, related_name="import_rows")
    source_row_digest = models.CharField(max_length=64, validators=[sha256_validator])
    promoted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["batch", "worksheet_name", "excel_row_number"], name="staging_source_row_unique"),
            check("staging_row_positive", Q(excel_row_number__gte=1)),
            check("staging_sheet_text", Q(worksheet_name__regex=r"\S")),
            enum_check("staging_status_valid", "status", RowStatus),
            check("staging_digest_valid", Q(source_row_digest__regex=r"^[0-9a-f]{64}$")),
            check("staging_target_state", (
                Q(status=RowStatus.PROMOTED, promoted_at__isnull=False) & xor_fields("asset", "stock_balance")
                | (~Q(status=RowStatus.PROMOTED) & Q(promoted_at__isnull=True, asset__isnull=True, stock_balance__isnull=True))
            )),
        ]
        indexes = [models.Index(fields=["batch", "status"], name="staging_batch_status")]
