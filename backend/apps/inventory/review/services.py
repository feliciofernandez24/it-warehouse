"""Fail-closed future write interfaces. No mutation or external I/O."""
import hashlib
import uuid
from django.db import connections, transaction, DatabaseError
from apps.inventory.models import ImportPreparationRevision, ImportReviewEvent
from apps.inventory.staging.common import canonical
from .authorization import require_capabilities, require_independent_reviewer
from .errors import ReviewServiceError, database_error

ACTIONS = {
    "register_verified_capture": ("capture_import", None, "CAPTURE"),
    "start_preparation": ("prepare_import", "CAPTURED", "START"),
    "edit_preparation": ("prepare_import", "PREPARING", "EDIT"),
    "submit_for_review": ("prepare_import", "PREPARING", "SUBMIT"),
    "record_review": ("review_import", "READY_FOR_REVIEW", "REVIEW_ACCEPT"),
    "return_for_correction": ("review_import", "READY_FOR_REVIEW", "RETURN"),
    "reject_revision": ("review_import", "READY_FOR_REVIEW", "REJECT"),
}
RESERVED = {"actor", "actor_id", "user_id", "created_by", "uploaded_by",
            "approved_by", "reviewed_by", "participant_ids", "signature"}


def _payload(value):
    nodes = 0
    def check(v, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 24 or nodes > 20000:
            raise ReviewServiceError("REQUEST_TOO_LARGE")
        if type(v) is dict:
            for k, item in v.items():
                if type(k) is not str or k in RESERVED or k.endswith("_by_id"):
                    raise ReviewServiceError("INVALID_REQUEST")
                check(item, depth + 1)
        elif type(v) is list:
            for item in v:
                check(item, depth + 1)
        elif type(v) is str:
            if len(v) > 32767:
                raise ReviewServiceError("REQUEST_TOO_LARGE")
        elif v is not None and type(v) not in (int, bool):
            raise ReviewServiceError("INVALID_REQUEST")
    if type(value) is not dict:
        raise ReviewServiceError("INVALID_REQUEST")
    check(value)
    try:
        data = canonical(value)
    except (ValueError, UnicodeError, OverflowError):
        raise ReviewServiceError("INVALID_REQUEST") from None
    if len(data) > 1048576:
        raise ReviewServiceError("REQUEST_TOO_LARGE")
    return data


def inspect_request(*, actor, action, request_id, revision_id=None,
                    expected_version=None, payload=None, using="default"):
    """Read-only preflight, never an authorization token or posting result.

    Existing event replay returns identifiers only, with current version/state.
    New writes always fail through execute_request, regardless of this result.
    """
    if action not in ACTIONS:
        raise ReviewServiceError("ACTION_DISABLED")
    capability, state, kind = ACTIONS[action]
    try:
        request_id = uuid.UUID(str(request_id))
        revision_id = uuid.UUID(str(revision_id)) if revision_id is not None else None
    except (ValueError, TypeError, AttributeError):
        raise ReviewServiceError("INVALID_REQUEST") from None
    if (state is None and (revision_id is not None or expected_version is not None) or
        state is not None and (revision_id is None or type(expected_version) is not int
                               or not 1 <= expected_version < 2**63)):
        raise ReviewServiceError("INVALID_REQUEST")
    data = _payload({} if payload is None else payload)
    try:
        with transaction.atomic(using=using):
            with connections[using].cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(73921,2)")
            caps = ["inventory." + capability]
            if action != "register_verified_capture":
                caps.append("inventory.view_import_evidence")
            principal = require_capabilities(actor, *caps, using=using)
            revision = None
            if revision_id:
                revision = ImportPreparationRevision.objects.using(using).select_for_update().only("id", "version", "state").filter(pk=revision_id).first()
                if revision is None:
                    raise ReviewServiceError("REVISION_NOT_FOUND")
                if capability == "review_import":
                    require_independent_reviewer(actor, revision_id, using=using)
            fingerprint = hashlib.sha256(canonical({
                "domain": "itw.review-request.v1", "actor_id": principal.user_id,
                "action": action, "revision_id": str(revision_id) if revision_id else None,
                "expected_version": expected_version,
                "payload_sha256": hashlib.sha256(data).hexdigest(),
            })).hexdigest()
            event = ImportReviewEvent.objects.using(using).filter(request_id=request_id).first()
            if event:
                if (event.actor_id != principal.user_id or event.kind != kind or
                    event.request_fingerprint != fingerprint or event.revision_id != revision_id):
                    raise ReviewServiceError("REQUEST_CONFLICT")
                return {"writes_enabled": False, "historical_event_id": str(event.pk),
                        "version": revision.version, "state": revision.state}
            if revision and revision.version != expected_version:
                raise ReviewServiceError("VERSION_CONFLICT")
            if revision and revision.state != state:
                raise ReviewServiceError("REVISION_STATE_INVALID")
            return {"writes_enabled": False, "historical_event_id": None,
                    "fingerprint": fingerprint}
    except DatabaseError as error:
        raise database_error(error) from None


def execute_request(**kwargs):
    result = inspect_request(**kwargs)
    # Even historical preflight is not presented as an operational write API.
    raise ReviewServiceError("GATEWAY_UNAVAILABLE")


def register_verified_capture(**kwargs):
    return execute_request(action="register_verified_capture", **kwargs)


def start_preparation(**kwargs):
    return execute_request(action="start_preparation", **kwargs)


def edit_preparation(**kwargs):
    return execute_request(action="edit_preparation", **kwargs)


def submit_for_review(**kwargs):
    return execute_request(action="submit_for_review", **kwargs)


def record_review(**kwargs):
    return execute_request(action="record_review", **kwargs)


def return_for_correction(**kwargs):
    return execute_request(action="return_for_correction", **kwargs)


def reject_revision(**kwargs):
    return execute_request(action="reject_revision", **kwargs)


def approve_revision(**kwargs):
    raise ReviewServiceError("ACTION_DISABLED")


def revoke_approval(**kwargs):
    raise ReviewServiceError("ACTION_DISABLED")


def promote_import(**kwargs):
    raise ReviewServiceError("ACTION_DISABLED")
