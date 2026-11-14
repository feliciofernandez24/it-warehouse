"""Request/session User objects only; explicit fresh grants, no permission cache."""
from dataclasses import dataclass
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.db import DEFAULT_DB_ALIAS, DatabaseError
from django.db.models import Q

from apps.inventory.models import ImportPreparationRevision, ImportRevisionParticipant
from .errors import ReviewServiceError, database_error

CAPABILITIES = frozenset("inventory." + name for name in (
    "capture_import", "prepare_import", "review_import", "approve_import",
    "revoke_import", "view_import_evidence",
))


@dataclass(frozen=True)
class Principal:
    user_id: int
    using: str


@dataclass(frozen=True)
class RevisionContext:
    revision_id: object
    batch_id: int
    version: int
    state: str


def actor_key(actor, using=DEFAULT_DB_ALIAS):
    """Type/saved-object boundary, not independent proof of human authentication.

    Trusted callers supply request.user, never construct it from body fields.
    A compromised server can forge an ORM object; that is explicitly outside
    this validation's human-identity guarantee.
    """
    if actor is None or isinstance(actor, AnonymousUser):
        raise ReviewServiceError("AUTHENTICATION_REQUIRED")
    if not isinstance(actor, get_user_model()):
        raise ReviewServiceError("INVALID_ACTOR_CONTEXT")
    if actor.is_authenticated is not True:
        raise ReviewServiceError("AUTHENTICATION_REQUIRED")
    if actor.pk is None or actor._state.adding:
        raise ReviewServiceError("INVALID_ACTOR_CONTEXT")
    if actor._state.db != using:
        raise ReviewServiceError("ACTOR_DATABASE_MISMATCH")
    return actor.pk


def require_capabilities(actor, *capabilities, using=DEFAULT_DB_ALIAS):
    key = actor_key(actor, using)
    if not capabilities or any(cap not in CAPABILITIES for cap in capabilities):
        raise ReviewServiceError("UNKNOWN_CAPABILITY")
    try:
        row = get_user_model()._default_manager.using(using).filter(pk=key).values("is_active").first()
        if row is None:
            raise ReviewServiceError("ACTOR_UNAVAILABLE")
        if not row["is_active"]:
            raise ReviewServiceError("ACTOR_INACTIVE")
        requested = {cap.split(".", 1)[1] for cap in capabilities}
        grants = set(Permission.objects.using(using).filter(
            Q(user__pk=key) | Q(group__user__pk=key),
            content_type__app_label="inventory", content_type__model="importbatch",
            codename__in=requested,
        ).values_list("codename", flat=True))
        if grants != requested:
            raise ReviewServiceError("PERMISSION_DENIED")
        return Principal(key, using)
    except DatabaseError as error:
        raise database_error(error) from None


def require_independent_reviewer(actor, revision_id, *, using=DEFAULT_DB_ALIAS):
    try:
        revision_id = uuid.UUID(str(revision_id))
    except (ValueError, TypeError, AttributeError):
        raise ReviewServiceError("INVALID_REQUEST") from None
    principal = require_capabilities(
        actor, "inventory.review_import", "inventory.view_import_evidence", using=using)
    try:
        row = ImportPreparationRevision.objects.using(using).filter(pk=revision_id).values(
            "pk", "batch_id", "batch__uploaded_by_id", "created_by_id", "version", "state",
        ).first()
        if row is None:
            raise ReviewServiceError("REVISION_NOT_FOUND")
        if principal.user_id == row["batch__uploaded_by_id"]:
            raise ReviewServiceError("SELF_REVIEW_UPLOADER")
        if principal.user_id == row["created_by_id"]:
            raise ReviewServiceError("SELF_REVIEW_CREATOR")
        if ImportRevisionParticipant.objects.using(using).filter(
                revision_id=row["pk"], user_id=principal.user_id).exists():
            raise ReviewServiceError("SELF_REVIEW_CONTRIBUTOR")
        return RevisionContext(row["pk"], row["batch_id"], row["version"], row["state"])
    except DatabaseError as error:
        raise database_error(error) from None
