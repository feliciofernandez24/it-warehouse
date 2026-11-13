"""Movement ledger, operation identity, approvals and recipient custody."""
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.common import TimestampedModel, check, enum_check, related_or_error, require_tracking, xor_fields
from apps.inventory.choices import Condition, LifecycleStatus, TrackingMode


class MovementType(models.TextChoices):
    STOCK_IN = "STOCK_IN", "Stock in"
    STOCK_OUT = "STOCK_OUT", "Stock out"
    TRANSFER = "TRANSFER", "Transfer"
    RETURN = "RETURN", "Return"
    ADJUSTMENT_IN = "ADJUSTMENT_IN", "Adjustment in"
    ADJUSTMENT_OUT = "ADJUSTMENT_OUT", "Adjustment out"
    DISPOSAL = "DISPOSAL", "Disposal"


class StockMovement(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    operation_key = models.UUIDField(default=uuid.uuid4)
    line_number = models.PositiveIntegerField(default=1)
    operation_type = models.CharField(max_length=24, choices=MovementType.choices)
    asset = models.ForeignKey("inventory.Asset", on_delete=models.PROTECT, null=True, blank=True, related_name="movements")
    product_model = models.ForeignKey("inventory.ProductModel", on_delete=models.PROTECT, null=True, blank=True, related_name="bulk_movements")
    quantity = models.BigIntegerField()
    source_location = models.ForeignKey("warehouse.StorageLocation", on_delete=models.PROTECT, null=True, blank=True, related_name="outgoing_movements")
    destination_location = models.ForeignKey("warehouse.StorageLocation", on_delete=models.PROTECT, null=True, blank=True, related_name="incoming_movements")
    source_balance = models.ForeignKey("inventory.StockBalance", on_delete=models.PROTECT, null=True, blank=True, related_name="debit_movements")
    destination_balance = models.ForeignKey("inventory.StockBalance", on_delete=models.PROTECT, null=True, blank=True, related_name="credit_movements")
    condition_before = models.CharField(max_length=24, choices=Condition.choices, null=True, blank=True)
    condition_after = models.CharField(max_length=24, choices=Condition.choices, null=True, blank=True)
    lifecycle_before = models.CharField(max_length=24, choices=LifecycleStatus.choices, null=True, blank=True)
    lifecycle_after = models.CharField(max_length=24, choices=LifecycleStatus.choices, null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_movements")
    occurred_at = models.DateTimeField(default=timezone.now)
    recorded_at = models.DateTimeField(default=timezone.now, editable=False)
    reason = models.TextField()
    external_reference = models.CharField(max_length=160, blank=True)
    reverses = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversal_entries")
    audit_line = models.ForeignKey("audits.AuditLine", on_delete=models.PROTECT, null=True, blank=True, related_name="correction_movements")
    import_row = models.OneToOneField("inventory.ImportStagingRecord", on_delete=models.PROTECT, null=True, blank=True, related_name="opening_movement")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["operation_key", "line_number"], name="movement_operation_line_unique"),
            check("movement_positive_quantity", Q(quantity__gt=0)),
            check("movement_positive_line", Q(line_number__gte=1)),
            check("movement_target_xor", xor_fields("asset", "product_model")),
            enum_check("movement_type_valid", "operation_type", MovementType),
            enum_check("movement_condition_before", "condition_before", Condition, nullable=True),
            enum_check("movement_condition_after", "condition_after", Condition, nullable=True),
            enum_check("movement_lifecycle_before", "lifecycle_before", LifecycleStatus, nullable=True),
            enum_check("movement_lifecycle_after", "lifecycle_after", LifecycleStatus, nullable=True),
            check("movement_reason_text", Q(reason__regex=r"\S")),
            check("movement_asset_shape", Q(asset__isnull=True) | Q(quantity=1, source_balance__isnull=True, destination_balance__isnull=True)),
            check("movement_bulk_snapshots", Q(asset__isnull=False) | Q(condition_before__isnull=True, condition_after__isnull=True, lifecycle_before__isnull=True, lifecycle_after__isnull=True)),
            check("movement_direction", (
                Q(operation_type__in=[MovementType.STOCK_IN, MovementType.RETURN, MovementType.ADJUSTMENT_IN], source_location__isnull=True, destination_location__isnull=False)
                | Q(operation_type__in=[MovementType.STOCK_OUT, MovementType.DISPOSAL, MovementType.ADJUSTMENT_OUT], source_location__isnull=False, destination_location__isnull=True)
                | Q(operation_type=MovementType.TRANSFER, source_location__isnull=False, destination_location__isnull=False)
            )),
            check("movement_bulk_source", Q(asset__isnull=False) | (Q(source_location__isnull=True, source_balance__isnull=True) | Q(source_location__isnull=False, source_balance__isnull=False))),
            check("movement_bulk_destination", Q(asset__isnull=False) | (Q(destination_location__isnull=True, destination_balance__isnull=True) | Q(destination_location__isnull=False, destination_balance__isnull=False))),
            check("movement_not_noop_transfer", ~Q(operation_type=MovementType.TRANSFER) | ~Q(source_location=F("destination_location")) | (Q(source_balance__isnull=False, destination_balance__isnull=False) & ~Q(source_balance=F("destination_balance"))) | (Q(asset__isnull=False) & (~Q(condition_before=F("condition_after")) | ~Q(lifecycle_before=F("lifecycle_after"))))),
            check("movement_not_self_reverse", ~Q(reverses=F("pk"))),
        ]
        indexes = [
            models.Index(fields=["asset", "recorded_at", "id"], name="movement_asset_recorded"),
            models.Index(fields=["product_model", "occurred_at"], name="movement_product_occurred"),
            models.Index(fields=["source_location", "occurred_at"], name="movement_source_occurred"),
            models.Index(fields=["destination_location", "occurred_at"], name="movement_dest_occurred"),
        ]
        permissions = [
            ("post_movement", "Can post stock movements"),
            ("approve_adjustment", "Can approve stock adjustments"),
            ("approve_disposal", "Can approve equipment disposal"),
        ]

    def clean(self):
        super().clean()
        if bool(self.asset_id) == bool(self.product_model_id):
            raise ValidationError("Specify exactly one serialized asset or bulk product.")
        if self.product_model_id:
            require_tracking(related_or_error(self, "product_model"), TrackingMode.BULK)
        for prefix in ("source", "destination"):
            balance = related_or_error(self, f"{prefix}_balance")
            if balance is not None and (
                balance.product_model_id != self.product_model_id
                or balance.location_id != getattr(self, f"{prefix}_location_id")
            ):
                raise ValidationError({f"{prefix}_balance": "Bucket must match movement product and location."})


class AssetAssignment(TimestampedModel):
    asset = models.ForeignKey("inventory.Asset", on_delete=models.PROTECT, related_name="assignments")
    recipient = models.ForeignKey("accounts.AssetRecipient", on_delete=models.PROTECT, related_name="assignments")
    destination_description = models.TextField(blank=True)
    destination_reference = models.CharField(max_length=200, blank=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="issued_assignments")
    assigned_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    returned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="returned_assignments")
    issue_movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, related_name="issued_assignment")
    return_movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, null=True, blank=True, related_name="returned_assignment")
    purpose = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["asset"], condition=Q(returned_at__isnull=True), name="assignment_one_open_asset"),
            check("assignment_due_order", Q(due_at__isnull=True) | Q(due_at__gte=F("assigned_at"))),
            check("assignment_return_order", Q(returned_at__isnull=True) | Q(returned_at__gte=F("assigned_at"))),
            check("assignment_return_fields", Q(returned_at__isnull=True, returned_by__isnull=True, return_movement__isnull=True) | Q(returned_at__isnull=False, returned_by__isnull=False, return_movement__isnull=False)),
        ]
        indexes = [models.Index(fields=["recipient", "returned_at"], name="assignment_recipient_return")]

    def clean(self):
        super().clean()
        if self.recipient_id and not related_or_error(self, "recipient").is_active:
            raise ValidationError({"recipient": "Choose an active recipient."})
        for field, expected_type in [("issue_movement", MovementType.STOCK_OUT), ("return_movement", MovementType.RETURN)]:
            movement = related_or_error(self, field)
            if movement is not None and (movement.asset_id != self.asset_id or movement.operation_type != expected_type):
                raise ValidationError({field: "Movement must match this asset and custody operation."})
        if self.issue_movement_id and (self.issue_movement.actor_id != self.issued_by_id or self.issue_movement.occurred_at != self.assigned_at):
            raise ValidationError({"issue_movement": "Issue actor/time must match assignment."})
        if self.return_movement_id and (self.return_movement.actor_id != self.returned_by_id or self.return_movement.occurred_at != self.returned_at):
            raise ValidationError({"return_movement": "Return actor/time must match assignment."})


class StockOperation(models.Model):
    """Durable complete request; committed operations and approvals are immutable."""
    operation_key = models.UUIDField(primary_key=True)
    request = models.JSONField()
    fingerprint = models.CharField(max_length=64)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_requests")
    requested_at = models.DateTimeField(default=timezone.now, editable=False)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="stock_approvals")
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_reason = models.TextField(blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            check("operation_fingerprint_valid", Q(fingerprint__regex=r"^[0-9a-f]{64}$")),
            check("operation_separate_approver", Q(approved_by__isnull=True) | ~Q(approved_by=F("requested_by"))),
            check("operation_approval_pair", Q(approved_by__isnull=True, approved_at__isnull=True, approval_reason="") | (Q(approved_by__isnull=False, approved_at__isnull=False) & Q(approval_reason__regex=r"\S"))),
            check("operation_approval_order", Q(approved_at__isnull=True) | Q(approved_at__gte=F("requested_at"))),
            check("operation_post_order", Q(posted_at__isnull=True) | Q(posted_at__gte=F("requested_at"))),
        ]
        permissions = [
            ("receive_stock", "Can receive stock"), ("issue_stock", "Can issue stock"),
            ("transfer_stock", "Can transfer or reclassify stock"), ("return_stock", "Can return stock"),
            ("request_adjustment", "Can request stock adjustments"), ("request_disposal", "Can request disposal"),
            ("review_audit_adjustment", "Can review audit adjustments"),
        ]
