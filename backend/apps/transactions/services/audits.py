"""Safe freeze/snapshot foundation; no submitted-audit correction bypass exists."""
from django.db import transaction
from django.utils import timezone
from apps.audits.models import AuditLine, PhysicalInventoryAudit
from apps.inventory.models import Asset, StockBalance
from .exceptions import StockError
from .permissions import require
from .posting import _actor, _lock
from django.db import connection


@transaction.atomic
def start_audit(*, actor, audit_id):
    _lock()
    actor = _actor(actor)
    require(actor, "review_audit_adjustment")
    audit = PhysicalInventoryAudit.objects.select_for_update().get(pk=audit_id)
    if audit.status != "DRAFT" or audit.performed_by_id != actor.pk:
        raise StockError("Only the designated performer can start a draft audit")
    audit.status = "COUNTING"
    audit.started_at = timezone.now()
    audit.save(update_fields=["status", "started_at", "updated_at"])
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM itw_scope(%s,%s)", [audit.scope_location_id, audit.include_descendants])
        locations = [row[0] for row in cursor.fetchall()]
    for asset in Asset.objects.filter(current_location_id__in=locations).order_by("pk"):
        AuditLine.objects.create(audit=audit, asset=asset, expected_location_id=asset.current_location_id,
            location_id=asset.current_location_id, expected_quantity=1, expected_condition=asset.condition)
    for balance in StockBalance.objects.filter(location_id__in=locations).order_by("pk"):
        AuditLine.objects.create(audit=audit, product_model_id=balance.product_model_id, stock_balance=balance,
            expected_location_id=balance.location_id, location_id=balance.location_id,
            expected_quantity=balance.quantity, expected_condition=balance.condition, expected_stock_state=balance.stock_state)
    return audit


@transaction.atomic
def record_count(*, actor, line_id, quantity, condition, state=None, notes=""):
    _lock()
    actor = _actor(actor)
    require(actor, "review_audit_adjustment")
    line = AuditLine.objects.select_for_update().select_related("audit").get(pk=line_id)
    if line.audit.status != "COUNTING" or line.counted_at or type(quantity) is not int or quantity < 0:
        raise StockError("An uncounted counting-phase line and a nonnegative integer are required")
    line.observed_quantity = quantity
    line.observed_condition = condition
    line.observed_stock_state = state
    line.counted_by = actor
    line.counted_at = timezone.now()
    line.notes = notes
    line.outcome = ("MISSING" if quantity < line.expected_quantity else "EXCESS" if quantity > line.expected_quantity
        else "DAMAGED" if condition != line.expected_condition or state != line.expected_stock_state else "MATCH")
    line.full_clean()
    line.save()
    return line
