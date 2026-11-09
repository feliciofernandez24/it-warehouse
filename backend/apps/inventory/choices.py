from django.db import models


class TrackingMode(models.TextChoices):
    SERIALIZED = "SERIALIZED", "Serialized"
    BULK = "BULK", "Bulk"


class Condition(models.TextChoices):
    NEW = "NEW", "New"
    USED = "USED", "Used"
    REFURBISHED = "REFURBISHED", "Refurbished"
    BROKEN = "BROKEN", "Broken"
    UNKNOWN = "UNKNOWN", "Unknown"


class LifecycleStatus(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    QUARANTINED = "QUARANTINED", "Quarantined"
    ASSIGNED = "ASSIGNED", "Assigned"
    DISPOSED = "DISPOSED", "Disposed"
    LOST = "LOST", "Lost"


class StockState(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    QUARANTINED = "QUARANTINED", "Quarantined"


class SerialReviewState(models.TextChoices):
    UNREVIEWED = "UNREVIEWED", "Unreviewed"
    VERIFIED = "VERIFIED", "Verified"
    DUPLICATE = "DUPLICATE", "Duplicate"
    MISSING = "MISSING", "Missing"


class SpecificationType(models.TextChoices):
    INTEGER = "INTEGER", "Integer"
    DECIMAL = "DECIMAL", "Decimal"
    TEXT = "TEXT", "Text"
    BOOLEAN = "BOOLEAN", "Boolean"


class BatchStatus(models.TextChoices):
    UPLOADED = "UPLOADED", "Uploaded"
    VALIDATED = "VALIDATED", "Validated"
    IN_REVIEW = "IN_REVIEW", "In review"
    APPROVED = "APPROVED", "Approved"
    PROMOTED = "PROMOTED", "Promoted"
    FAILED = "FAILED", "Failed"
    REJECTED = "REJECTED", "Rejected"


class RowStatus(models.TextChoices):
    CAPTURED = "CAPTURED", "Captured"
    INVALID = "INVALID", "Invalid"
    READY = "READY", "Ready"
    IGNORED = "IGNORED", "Ignored"
    APPROVED = "APPROVED", "Approved"
    PROMOTED = "PROMOTED", "Promoted"
    REJECTED = "REJECTED", "Rejected"
