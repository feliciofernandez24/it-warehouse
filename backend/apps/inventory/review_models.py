"""Sensitive review schema only. Approval is disabled by database guards."""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Now
from django.db.models.lookups import Exact, GreaterThan, LessThanOrEqual

from apps.common import check, enum_check


class RevisionState(models.TextChoices):
    CAPTURED = "CAPTURED"
    PREPARING = "PREPARING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    RETURNED_FOR_CORRECTION = "RETURNED_FOR_CORRECTION"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


class ReviewEventKind(models.TextChoices):
    CAPTURE = "CAPTURE"
    START = "START"
    EDIT = "EDIT"
    EVIDENCE = "EVIDENCE"
    SUBMIT = "SUBMIT"
    REVIEW_ACCEPT = "REVIEW_ACCEPT"
    RETURN = "RETURN"
    REJECT = "REJECT"
    APPROVE = "APPROVE"
    SUPERSEDE = "SUPERSEDE"
    REVOKE = "REVOKE"


def object_check(field):
    return Exact(models.Func(F(field), function="jsonb_typeof",
                             output_field=models.CharField()), Value("object"))


def byte_length(field):
    return models.Func(F(field), function="octet_length", output_field=models.IntegerField())


class SensitiveReviewModel(models.Model):
    class Meta:
        abstract = True
        default_permissions = ()

    def __str__(self):
        return f"{type(self).__name__}:{self.pk or 'unsaved'}"



class ImportSourceProfile(SensitiveReviewModel):
    """Immutable owner-attested definition; not authenticated source capture."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64)
    version = models.PositiveIntegerField()
    workbook_sha256 = models.CharField(max_length=64)
    layout_digest = models.CharField(max_length=64)
    expected_counts = models.JSONField()
    canonical_bytes = models.BinaryField()
    digest = models.CharField(max_length=64)
    definition_verified = models.BooleanField(default=False)
    verification_evidence_digest = models.CharField(max_length=64, null=True, blank=True)
    registered_by = models.CharField(max_length=128, default="", editable=False)
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta(SensitiveReviewModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="review_profile_version_unique"),
            check("review_profile_code_valid", Q(code__regex=r"^[A-Z0-9][A-Z0-9_.-]*$")),
            check("review_profile_version_positive", Q(version__gt=0)),
            check("review_profile_workbook_hash", Q(workbook_sha256__regex=r"^[0-9a-f]{64}$")),
            check("review_profile_layout_hash", Q(layout_digest__regex=r"^[0-9a-f]{64}$")),
            check("review_profile_digest_valid", Q(digest__regex=r"^[0-9a-f]{64}$")),
            check("review_profile_counts_object", object_check("expected_counts")),
            check("review_profile_bytes_nonempty", GreaterThan(byte_length("canonical_bytes"), Value(0))),
            check("review_profile_bytes_bounded", LessThanOrEqual(byte_length("canonical_bytes"), Value(65536))),
            check("review_profile_verification_shape",
                  Q(definition_verified=False, verification_evidence_digest__isnull=True) |
                  Q(definition_verified=True, verification_evidence_digest__isnull=False,
                    verification_evidence_digest__regex=r"^[0-9a-f]{64}$")),
        ]


class ImportPreparationRevision(SensitiveReviewModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey("inventory.ImportBatch", on_delete=models.PROTECT,
                              related_name="preparation_revisions")
    source_profile = models.ForeignKey(ImportSourceProfile, on_delete=models.PROTECT,
                                       related_name="revisions")
    revision_number = models.PositiveBigIntegerField()
    parent = models.OneToOneField("self", on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="successor")
    state = models.CharField(max_length=24, choices=RevisionState.choices,
                             default=RevisionState.CAPTURED)
    version = models.PositiveBigIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="created_import_revisions")
    created_at = models.DateTimeField(db_default=Now(), editable=False)
    layout_digest = models.CharField(max_length=64)
    manifest_digest = models.CharField(max_length=64)
    capture_storage_key = models.CharField(max_length=255)
    capture_artifact_digest = models.CharField(max_length=64)
    draft_payload = models.JSONField(default=dict)

    class Meta(SensitiveReviewModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["batch", "revision_number"],
                                    name="review_revision_number_unique"),
            models.UniqueConstraint(fields=["batch"],
                                    condition=Q(state__in=["CAPTURED", "PREPARING",
                                                          "READY_FOR_REVIEW", "APPROVED"]),
                                    name="review_one_active_revision"),
            check("review_revision_number_positive", Q(revision_number__gt=0)),
            check("review_revision_version_positive", Q(version__gt=0)),
            enum_check("review_revision_state_valid", "state", RevisionState),
            check("review_revision_parent_shape",
                  Q(revision_number=1, parent__isnull=True) |
                  Q(revision_number__gt=1, parent__isnull=False)),
            check("review_revision_layout_hash", Q(layout_digest__regex=r"^[0-9a-f]{64}$")),
            check("review_revision_manifest_hash", Q(manifest_digest__regex=r"^[0-9a-f]{64}$")),
            check("review_revision_capture_hash", Q(capture_artifact_digest__regex=r"^[0-9a-f]{64}$")),
            check("review_revision_storage_text", Q(capture_storage_key__regex=r"\S")),
            check("review_revision_payload_object", object_check("draft_payload")),
        ]


class ImportRevisionParticipant(SensitiveReviewModel):
    revision = models.ForeignKey(ImportPreparationRevision, on_delete=models.PROTECT,
                                  related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="import_preparation_participations")
    first_seen_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta(SensitiveReviewModel.Meta):
        constraints = [models.UniqueConstraint(fields=["revision", "user"],
                                               name="review_participant_unique")]


class ImportPreviewSnapshot(SensitiveReviewModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    revision = models.OneToOneField(ImportPreparationRevision, on_delete=models.PROTECT,
                                    related_name="preview_snapshot")
    canonical_bytes = models.BinaryField()
    digest = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta(SensitiveReviewModel.Meta):
        constraints = [
            check("review_snapshot_hash_valid", Q(digest__regex=r"^[0-9a-f]{64}$")),
            check("review_snapshot_bytes_nonempty", GreaterThan(byte_length("canonical_bytes"), Value(0))),
            check("review_snapshot_bytes_bounded",
                  LessThanOrEqual(byte_length("canonical_bytes"), Value(32 * 1024 * 1024))),
        ]


class ImportReviewEvent(SensitiveReviewModel):
    revision = models.ForeignKey(ImportPreparationRevision, on_delete=models.PROTECT,
                                  related_name="review_events")
    sequence = models.PositiveBigIntegerField()
    request_id = models.UUIDField(unique=True)
    request_fingerprint = models.CharField(max_length=64)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                               related_name="import_review_events")
    recorded_at = models.DateTimeField(db_default=Now(), editable=False)
    kind = models.CharField(max_length=24, choices=ReviewEventKind.choices)
    from_state = models.CharField(max_length=24, choices=RevisionState.choices)
    to_state = models.CharField(max_length=24, choices=RevisionState.choices)
    snapshot = models.ForeignKey(ImportPreviewSnapshot, on_delete=models.PROTECT,
                                 null=True, blank=True, related_name="review_events")
    source_row = models.ForeignKey("inventory.ImportStagingRecord", on_delete=models.PROTECT,
                                   null=True, blank=True, related_name="review_events")
    reason_code = models.CharField(max_length=64)
    reason = models.TextField()
    details = models.JSONField(default=dict)
    review_event = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="approval_events")
    signature_algorithm = models.CharField(max_length=32, null=True, blank=True)
    signing_key_id = models.CharField(max_length=128, null=True, blank=True)
    signature = models.BinaryField(null=True, blank=True)

    class Meta(SensitiveReviewModel.Meta):
        indexes = [models.Index(fields=["revision", "recorded_at", "id"],
                                name="review_event_time")]
        constraints = [
            models.UniqueConstraint(fields=["revision", "sequence"], name="review_event_sequence_unique"),
            models.UniqueConstraint(fields=["revision"], condition=Q(kind="APPROVE"),
                                    name="review_one_approval_event"),
            check("review_event_sequence_positive", Q(sequence__gt=0)),
            check("review_event_fingerprint_hash", Q(request_fingerprint__regex=r"^[0-9a-f]{64}$")),
            enum_check("review_event_kind_valid", "kind", ReviewEventKind),
            enum_check("review_event_from_valid", "from_state", RevisionState),
            enum_check("review_event_to_valid", "to_state", RevisionState),
            check("review_event_reason_code_text", Q(reason_code__regex=r"\S")),
            check("review_event_reason_text", Q(reason__regex=r"\S")),
            check("review_event_details_object", object_check("details")),
            check("review_event_signature_shape",
                  Q(kind="APPROVE", snapshot__isnull=False, review_event__isnull=False,
                    signature_algorithm="HMAC-SHA256-v1", signature_algorithm__isnull=False,
                    signing_key_id__isnull=False, signing_key_id__regex=r"\S",
                    signature__isnull=False) |
                  (~Q(kind="APPROVE") & Q(review_event__isnull=True, signature_algorithm__isnull=True,
                                        signing_key_id__isnull=True, signature__isnull=True))),
            check("review_event_signature_size",
                  Q(signature__isnull=True) | Exact(byte_length("signature"), Value(32))),
        ]
