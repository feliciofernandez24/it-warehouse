"""Physical counts and immutable change-event schema."""
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.common import TimestampedModel, check, enum_check, related_or_error, require_tracking, xor_fields
from apps.inventory.choices import Condition, StockState, TrackingMode


class AuditStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    COUNTING = "COUNTING", "Counting"
    SUBMITTED = "SUBMITTED", "Submitted"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    CANCELLED = "CANCELLED", "Cancelled"


class AuditOutcome(models.TextChoices):
    MATCH = "MATCH", "Match"
    MISSING = "MISSING", "Missing"
    EXCESS = "EXCESS", "Excess"
    DAMAGED = "DAMAGED", "Damaged"
    MISPLACED = "MISPLACED", "Misplaced"
    UNCOUNTED = "UNCOUNTED", "Uncounted"


class PhysicalInventoryAudit(TimestampedModel):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    scope_location = models.ForeignKey("warehouse.StorageLocation", on_delete=models.PROTECT, related_name="audits")
    include_descendants = models.BooleanField(default=True)
    status = models.CharField(max_length=24, choices=AuditStatus.choices, default=AuditStatus.DRAFT)
    planned_date = models.DateField()
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="performed_audits")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="approved_audits")
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            enum_check("audit_status_valid", "status", AuditStatus),
            check("audit_separate_approver", Q(approved_by__isnull=True) | ~Q(approved_by=F("performed_by"))),
            check("audit_approval_pair", Q(approved_by__isnull=True, approved_at__isnull=True) | Q(approved_by__isnull=False, approved_at__isnull=False)),
            check("audit_approved_evidence", ~Q(status=AuditStatus.APPROVED) | Q(approved_by__isnull=False, approved_at__isnull=False, submitted_at__isnull=False, started_at__isnull=False)),
            check("audit_counting_started", ~Q(status__in=[AuditStatus.COUNTING, AuditStatus.SUBMITTED]) | Q(started_at__isnull=False)),
            check("audit_submitted_time", ~Q(status=AuditStatus.SUBMITTED) | Q(submitted_at__isnull=False)),
            check("audit_submission_order", Q(submitted_at__isnull=True) | Q(started_at__isnull=False, submitted_at__gte=F("started_at"))),
            check("audit_approval_order", Q(approved_at__isnull=True) | Q(submitted_at__isnull=False, approved_at__gte=F("submitted_at"))),
        ]
        indexes = [models.Index(fields=["status", "started_at"], name="audit_status_started")]
        permissions = [("approve_audit", "Can approve another operator's audit")]


class AuditLine(TimestampedModel):
    audit = models.ForeignKey(PhysicalInventoryAudit, on_delete=models.PROTECT, related_name="lines")
    asset = models.ForeignKey("inventory.Asset", on_delete=models.PROTECT, null=True, blank=True, related_name="audit_lines")
    product_model = models.ForeignKey("inventory.ProductModel", on_delete=models.PROTECT, null=True, blank=True, related_name="audit_lines")
    stock_balance = models.ForeignKey("inventory.StockBalance", on_delete=models.PROTECT, null=True, blank=True, related_name="audit_lines")
    expected_location = models.ForeignKey("warehouse.StorageLocation", on_delete=models.PROTECT, null=True, blank=True, related_name="expected_audit_lines")
    location = models.ForeignKey("warehouse.StorageLocation", on_delete=models.PROTECT, related_name="observed_audit_lines")
    expected_quantity = models.BigIntegerField()
    observed_quantity = models.BigIntegerField(null=True, blank=True)
    expected_condition = models.CharField(max_length=24, choices=Condition.choices)
    observed_condition = models.CharField(max_length=24, choices=Condition.choices, null=True, blank=True)
    expected_stock_state = models.CharField(max_length=24, choices=StockState.choices, null=True, blank=True)
    observed_stock_state = models.CharField(max_length=24, choices=StockState.choices, null=True, blank=True)
    outcome = models.CharField(max_length=24, choices=AuditOutcome.choices, default=AuditOutcome.UNCOUNTED)
    counted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="counted_audit_lines")
    counted_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            check("audit_line_target_xor", xor_fields("asset", "product_model")),
            check("audit_line_nonnegative", Q(expected_quantity__gte=0) & (Q(observed_quantity__isnull=True) | Q(observed_quantity__gte=0))),
            check("audit_asset_counts", Q(asset__isnull=True) | (Q(expected_quantity__in=[0, 1]) & (Q(observed_quantity__isnull=True) | Q(observed_quantity__in=[0, 1])))),
            check("audit_line_bucket_type", Q(asset__isnull=True, expected_stock_state__isnull=False) | Q(stock_balance__isnull=True, expected_stock_state__isnull=True, observed_stock_state__isnull=True)),
            check("audit_line_count_evidence", Q(observed_quantity__isnull=True, counted_by__isnull=True, counted_at__isnull=True, outcome=AuditOutcome.UNCOUNTED) | (Q(observed_quantity__isnull=False, counted_by__isnull=False, counted_at__isnull=False) & ~Q(outcome=AuditOutcome.UNCOUNTED))),
            enum_check("audit_outcome_valid", "outcome", AuditOutcome),
            enum_check("audit_expected_condition", "expected_condition", Condition),
            enum_check("audit_observed_condition", "observed_condition", Condition, nullable=True),
            enum_check("audit_expected_stock_state", "expected_stock_state", StockState, nullable=True),
            enum_check("audit_observed_stock_state", "observed_stock_state", StockState, nullable=True),
            models.UniqueConstraint(fields=["audit", "asset"], condition=Q(asset__isnull=False), name="audit_asset_unique"),
            models.UniqueConstraint(fields=["audit", "stock_balance"], condition=Q(stock_balance__isnull=False), name="audit_bucket_unique"),
            models.UniqueConstraint(fields=["audit", "product_model", "location", "expected_condition", "expected_stock_state"], condition=Q(asset__isnull=True, stock_balance__isnull=True), nulls_distinct=False, name="audit_excess_bucket_unique"),
        ]

    def clean(self):
        super().clean()
        if bool(self.asset_id) == bool(self.product_model_id):
            raise ValidationError("Specify exactly one asset or bulk product.")
        if self.product_model_id:
            require_tracking(related_or_error(self, "product_model"), TrackingMode.BULK)
        if self.stock_balance_id and (
            self.stock_balance.product_model_id != self.product_model_id
            or self.stock_balance.location_id != self.expected_location_id
        ):
            raise ValidationError({"stock_balance": "Snapshot bucket must match product and expected location."})


class AssetChangeLog(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    entity_kind = models.CharField(max_length=64)
    entity_pk = models.PositiveBigIntegerField()
    asset = models.ForeignKey("inventory.Asset", on_delete=models.PROTECT, null=True, blank=True, related_name="change_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="asset_change_events")
    action = models.CharField(max_length=40)
    recorded_at = models.DateTimeField(default=timezone.now, editable=False)
    operation_key = models.UUIDField(null=True, blank=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    reason = models.TextField()

    class Meta:
        constraints = [
            check("changelog_entity_positive", Q(entity_pk__gt=0)),
            check("changelog_entity_text", Q(entity_kind__regex=r"\S")),
            check("changelog_action_text", Q(action__regex=r"\S")),
            check("changelog_reason_text", Q(reason__regex=r"\S")),
        ]
        indexes = [models.Index(fields=["entity_kind", "entity_pk", "recorded_at"], name="change_entity_time")]
