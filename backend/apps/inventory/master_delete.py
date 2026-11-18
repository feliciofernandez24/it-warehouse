"""Unused master deletion only; all stock/history/review deletion is excluded."""
from django.conf import settings
from django.db import connection, transaction
from django.http import Http404
from rest_framework.exceptions import MethodNotAllowed
from apps.inventory.models import AssetCategory, Manufacturer, ProductModel
from apps.warehouse.models import Warehouse, StorageLocation
from apps.transactions.models import StockOperation
from apps.audits.models import AssetChangeLog, PhysicalInventoryAudit
from .master_service import require, snapshot, Conflict, Unavailable

ALLOWED = frozenset((AssetCategory, Manufacturer, ProductModel, Warehouse, StorageLocation))

@transaction.atomic
def remove(*, actor, model, pk, expected_version, reason):
    if model not in ALLOWED:
        raise MethodNotAllowed("DELETE")
    with connection.cursor() as c:
        c.execute("SELECT pg_advisory_xact_lock(73921,2)")
    fresh = require(actor, model, "delete")
    if not settings.MASTER_DATA_DELETE_ENABLED:
        raise Unavailable("Deletion is not enabled in this deployment. Use Edit to deactivate the record where supported.")
    try:
        record = model.objects.select_for_update().get(pk=pk)
    except (model.DoesNotExist, ValueError, TypeError, OverflowError):
        raise Http404 from None
    if record.version != expected_version:
        raise Conflict({"expected_version": "This record changed. Refresh it before deleting."})
    blocked = []
    # Check every reverse FK, including zero balances and historical evidence.
    # Existence queries expose no referenced values. FK constraints remain final authority.
    for relation in model._meta.related_objects:
        if relation.related_model._base_manager.filter(**{relation.field.attname: record.pk}).exists():
            blocked.append(str(relation.related_model._meta.verbose_name_plural))
    if model is ProductModel and StockOperation.objects.filter(
            request__lines__contains=[{"product_model_id":record.pk}]).exists():
        blocked.append("stock operation requests")
    if model is StorageLocation:
        if any(StockOperation.objects.filter(request__lines__contains=[{key:record.pk}]).exists()
               for key in ("source_location_id","destination_location_id")):
            blocked.append("stock operation requests")
        if PhysicalInventoryAudit.objects.filter(status__in=("COUNTING","SUBMITTED")).exists():
            blocked.append("active inventory audit; storage hierarchy is frozen")
    if blocked:
        raise Conflict({"dependencies": [
            "Referenced by " + ", ".join(sorted(set(blocked))) +
            ". Preserve this record; use Edit to deactivate it where supported."
        ]})
    before = snapshot(record)
    # Deliberately no ORM cascade/collector: exactly one allowlisted table/PK,
    # and all existing PostgreSQL FK/trigger protections remain enabled.
    with connection.cursor() as c:
        c.execute("DELETE FROM " + connection.ops.quote_name(model._meta.db_table) + " WHERE id=%s", [record.pk])
        if c.rowcount != 1:
            raise Conflict("Record changed; refresh before deleting.")
        c.execute("SET CONSTRAINTS ALL IMMEDIATE")
        c.execute("SET CONSTRAINTS ALL DEFERRED")
    AssetChangeLog.objects.create(
        actor=fresh, entity_kind=model._meta.label_lower, entity_pk=record.pk,
        action="MASTER_DELETE", before=before, after={}, reason=reason)
