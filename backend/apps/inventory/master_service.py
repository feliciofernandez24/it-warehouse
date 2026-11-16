"""Atomic audited mutations, coordinated with the existing stock/hierarchy lock."""
import json
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import connection, transaction
from django.http import Http404
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from apps.audits.models import AssetChangeLog
from apps.inventory.models import Asset


class Conflict(APIException):
    status_code = 409
    default_detail = "The record conflicts with current data. Refresh and try again."
    default_code = "conflict"


class Unavailable(APIException):
    status_code = 503
    default_detail = "The change could not be saved safely. No changes were committed."
    default_code = "write_unavailable"


def require(actor, model, action, related=()):
    fresh = get_user_model().objects.filter(pk=actor.pk).first()
    opts = model._meta
    permissions = [f"{opts.app_label}.view_{opts.model_name}", f"{opts.app_label}.{action}_{opts.model_name}", *related]
    if fresh is None or not fresh.is_active or not all(fresh.has_perm(p) for p in permissions):
        raise PermissionDenied()
    return fresh


def snapshot(instance):
    # Do not copy free-form notes, addresses, serials, credentials or unrelated model fields into audit JSON.
    omitted = {"description", "remarks", "address", "serial_raw", "serial_normalized"}
    values = {field.name: getattr(instance, field.attname)
            for field in instance._meta.concrete_fields
            if field.name not in omitted and field.name not in {"created_at", "updated_at"}
            and not field.name.startswith("legacy_")}
    return json.loads(json.dumps(values, cls=DjangoJSONEncoder))


@transaction.atomic
def mutate(*, actor, model, serializer_class, data, pk=None, partial=False, related=()):
    with connection.cursor() as c:
        c.execute("SELECT pg_advisory_xact_lock(73921,2)")
    fresh = require(actor, model, "add" if pk is None else "change", related)
    instance = None
    if pk is not None:
        try:
            instance = model.objects.select_for_update().get(pk=pk)
        except (model.DoesNotExist, ValueError, TypeError, OverflowError):
            raise Http404 from None
    serializer = serializer_class(instance, data=data, partial=partial)
    serializer.is_valid(raise_exception=True)
    values = dict(serializer.validated_data)
    reason = values.pop("change_reason")
    expected = values.pop("expected_version", None)
    if instance is not None and expected != instance.version:
        raise Conflict("This record changed since it was loaded. Refresh before saving.")
    if model is Asset and instance is None:
        raise Conflict({"code": "ASSET_REGISTRATION_REQUIRES_RECEIPT",
                        "detail": "New assets require an approved ledger-backed receipt. Phase 4B cannot create stock movements."})
    before = snapshot(instance) if instance else {}
    record = instance or model()
    changed = []
    for key, value in values.items():
        field = model._meta.get_field(key)
        if getattr(record, field.attname) != (value.pk if field.is_relation and value is not None else value):
            changed.append(key)
    for key, value in values.items():
        setattr(record, key, value)
    if model is Asset and "serial_raw" in changed:
        record.serial_review_state = "UNREVIEWED"
    record.version = (instance.version + 1) if instance is not None else 0
    try:
        record.full_clean()
    except ModelValidationError as error:
        raise ValidationError(error.message_dict if hasattr(error, "message_dict") else {"detail": error.messages}) from None
    if instance is None:
        record.save()
    else:
        fields = set(changed) | {"version", "updated_at"}
        if model is Asset and "serial_raw" in changed:
            fields.add("serial_review_state")
        record.save(update_fields=fields)
    after = snapshot(record)
    after["changed_fields"] = sorted(changed)
    AssetChangeLog.objects.create(
        actor=fresh, entity_kind=model._meta.label_lower, entity_pk=record.pk,
        asset=record if model is Asset else None, action="MASTER_CREATE" if instance is None else "MASTER_UPDATE",
        before=before, after=after, reason=reason)
    # The atomic decorator commits, including deferred checks, before returning to the API.
    return record
