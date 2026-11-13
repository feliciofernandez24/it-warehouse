"""Explicit atomic posting. All callers (including future admin/jobs) use this boundary."""
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.accounts.models import AssetRecipient
from apps.inventory.models import Asset, ProductModel, StockBalance
from apps.inventory.choices import Condition, LifecycleStatus, StockState
from apps.transactions.models import AssetAssignment, MovementType, StockMovement, StockOperation
from apps.warehouse.models import StorageLocation
from .exceptions import IdempotencyConflict, StockError
from .permissions import CAPABILITIES, require


@dataclass(frozen=True)
class Line:
    operation_type: str
    quantity: int = 1
    asset_id: int | None = None
    product_model_id: int | None = None
    source_location_id: int | None = None
    destination_location_id: int | None = None
    source_condition: str = "NEW"
    source_state: str = "AVAILABLE"
    condition: str = "NEW"
    state: str = "AVAILABLE"
    device_name: str = ""
    serial_raw: str = ""
    recipient_id: int | None = None
    assignment_id: int | None = None
    destination_reference: str = ""
    destination_description: str = ""
    purpose: str = ""
    due_at: str | None = None
    reverses_id: int | None = None


@dataclass(frozen=True)
class Request:
    operation_key: UUID
    lines: tuple[Line, ...]
    reason: str
    external_reference: str = ""


@dataclass(frozen=True)
class Result:
    operation_key: UUID
    movement_ids: tuple[int, ...]
    asset_ids: tuple[int, ...]


def _lock():
    # Coarse global ordering also coordinates audit/hierarchy trigger writers.
    # Deliberately trade throughput for a small, provable locking surface.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(73921, 2)")


def _payload(request):
    if not isinstance(request.operation_key, UUID) or not request.lines or not request.reason.strip():
        raise StockError("UUID operation key, at least one line and a reason required")
    payload = asdict(request)
    payload.pop("operation_key")
    payload["version"] = 1
    payload = json.loads(json.dumps(payload, sort_keys=True, allow_nan=False))
    for line in request.lines:
        if line.operation_type not in CAPABILITIES or type(line.quantity) is not int or line.quantity <= 0:
            raise StockError("Known movement type and positive integer quantity required")
        if line.condition not in Condition.values or line.source_condition not in Condition.values:
            raise StockError("Unknown condition")
        if line.state not in StockState.values or line.source_state not in StockState.values:
            raise StockError("Unknown stock state")
        if line.condition in ("BROKEN", "UNKNOWN") and line.state != "QUARANTINED":
            raise StockError("Unusable stock must be quarantined")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return payload, digest


def _actor(actor):
    # Do not trust caller-mutated is_active/is_superuser attributes.
    return get_user_model().objects.get(pk=actor.pk)


def _prepare(actor, request):
    payload, digest = _payload(request)
    for line in request.lines:
        require(actor, CAPABILITIES[line.operation_type])
    operation, created = StockOperation.objects.get_or_create(
        operation_key=request.operation_key,
        defaults=dict(request=payload, fingerprint=digest, requested_by=actor),
    )
    if operation.fingerprint != digest or operation.request != payload or operation.requested_by_id != actor.pk:
        raise IdempotencyConflict("Operation key already belongs to a different complete request")
    return operation


@transaction.atomic
def request_operation(*, actor, request: Request):
    _lock()
    return _prepare(_actor(actor), request)


@transaction.atomic
def approve_operation(*, actor, operation_key: UUID, reason: str):
    _lock()
    actor = _actor(actor)
    operation = StockOperation.objects.select_for_update().get(pk=operation_key)
    if operation.requested_by_id == actor.pk:
        raise StockError("Self approval is prohibited")
    if not reason.strip() or operation.posted_at or operation.approved_at:
        raise StockError("Approval requires a reason and an unapproved, unposted request")
    kinds = {line["operation_type"] for line in operation.request["lines"]}
    required = set()
    if kinds & {"ADJUSTMENT_IN", "ADJUSTMENT_OUT"}:
        required.add("approve_adjustment")
    if "DISPOSAL" in kinds:
        required.add("approve_disposal")
    if not required:
        raise StockError("This request does not require approval")
    for capability in required:
        require(actor, capability)
    operation.approved_by = actor
    operation.approved_at = timezone.now()
    operation.approval_reason = reason
    operation.save(update_fields=["approved_by", "approved_at", "approval_reason"])
    return operation


def _result(operation):
    movements = list(StockMovement.objects.filter(operation_key=operation.pk).order_by("line_number"))
    return Result(operation.pk, tuple(m.pk for m in movements), tuple(m.asset_id for m in movements if m.asset_id))


@transaction.atomic
def post(*, actor, request: Request) -> Result:
    _lock()
    actor = _actor(actor)
    operation = _prepare(actor, request)
    if operation.posted_at:
        return _result(operation)
    kinds = {line.operation_type for line in request.lines}
    approval_permissions = set()
    if kinds & {"ADJUSTMENT_IN", "ADJUSTMENT_OUT"}:
        approval_permissions.add("approve_adjustment")
    if "DISPOSAL" in kinds:
        approval_permissions.add("approve_disposal")
    if approval_permissions:
        if not operation.approved_at or operation.approved_by_id == actor.pk:
            raise StockError("Durable separate approval required before posting")
        approver = _actor(operation.approved_by)
        for capability in approval_permissions:
            require(approver, capability)
    # Lock all existing assets in increasing PK order, before line-level buckets/custody.
    asset_ids = sorted({line.asset_id for line in request.lines if line.asset_id})
    assets = {a.pk: a for a in Asset.objects.select_for_update().filter(pk__in=asset_ids).order_by("pk")}
    moment = timezone.now()
    for number, line in enumerate(request.lines, 1):
        _post_line(actor, operation, number, line, assets, moment)
    operation.posted_at = moment
    operation.save(update_fields=["posted_at"])
    # Force final-state guards here even when caller wraps post in an outer atomic().
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("SET CONSTRAINTS ALL DEFERRED")
    return _result(operation)


def _bucket(product_id, location_id, condition, state):
    bucket, _ = StockBalance.objects.get_or_create(
        product_model_id=product_id, location_id=location_id, condition=condition, stock_state=state,
    )
    return StockBalance.objects.select_for_update().get(pk=bucket.pk)


def _post_line(actor, operation, number, line, assets, moment):
    kind = line.operation_type
    incoming = kind in ("STOCK_IN", "RETURN", "ADJUSTMENT_IN")
    outgoing = kind in ("STOCK_OUT", "ADJUSTMENT_OUT", "DISPOSAL")
    if (incoming and (line.source_location_id or not line.destination_location_id)
        or outgoing and (not line.source_location_id or line.destination_location_id)
        or kind == "TRANSFER" and (not line.source_location_id or not line.destination_location_id)):
        raise StockError("Invalid movement endpoints")
    locations = {line.source_location_id, line.destination_location_id} - {None}
    if StorageLocation.objects.filter(pk__in=locations, is_active=True, warehouse__is_active=True).count() != len(locations):
        raise StockError("Active warehouse locations required")
    values = dict(operation_key=operation.pk, line_number=number, operation_type=kind,
        quantity=line.quantity, actor=actor, occurred_at=moment, reason=operation.request["reason"],
        external_reference=operation.request["external_reference"], source_location_id=line.source_location_id,
        destination_location_id=line.destination_location_id, reverses_id=line.reverses_id)
    assignment = None
    asset = assets.get(line.asset_id) if line.asset_id else None
    if line.asset_id and asset is None:
        raise StockError("Asset does not exist")
    if asset:
        if line.product_model_id or line.quantity != 1 or kind == "STOCK_IN":
            raise StockError("Existing serialized assets require quantity one and no bulk product")
    else:
        if not line.product_model_id:
            raise StockError("Product required for a receipt or bulk movement")
        product = ProductModel.objects.select_for_update().get(pk=line.product_model_id)
        if not product.is_active:
            raise StockError("Product is inactive")
        if product.tracking_mode == "SERIALIZED":
            if kind != "STOCK_IN" or line.quantity != 1 or not line.device_name.strip():
                raise StockError("New serialized assets require a named single-unit receipt")
            asset = Asset.objects.create(product_model=product, device_name=line.device_name,
                serial_raw=line.serial_raw, condition=line.condition,
                lifecycle_status=line.state, current_location_id=line.destination_location_id)
        elif product.tracking_mode != "BULK":
            raise StockError("Unknown product tracking mode")
    if asset:
        if kind != "STOCK_IN":
            if asset.lifecycle_status in ("LOST", "DISPOSED"):
                raise StockError("Terminal assets cannot move")
            if asset.current_location_id != line.source_location_id:
                raise StockError("Asset source does not match current position")
            if kind == "STOCK_OUT" and asset.lifecycle_status != "AVAILABLE":
                raise StockError("Only available assets can be issued")
        values.update(asset=asset, condition_before=None if kind == "STOCK_IN" else asset.condition,
            lifecycle_before=None if kind == "STOCK_IN" else asset.lifecycle_status,
            condition_after=line.condition if not outgoing else asset.condition,
            lifecycle_after=("ASSIGNED" if kind == "STOCK_OUT" else "DISPOSED" if kind == "DISPOSAL"
                else "LOST" if kind == "ADJUSTMENT_OUT" else line.state))
        if kind == "ADJUSTMENT_IN":
            raise StockError("Serialized increases use receipt; terminal recovery requires a separate workflow")
        if kind == "TRANSFER" and line.source_location_id == line.destination_location_id and (asset.condition, asset.lifecycle_status) == (line.condition, line.state):
            raise StockError("No-op transfer")
        if kind == "RETURN":
            if asset.lifecycle_status != "ASSIGNED" or not line.assignment_id:
                raise StockError("Return must identify current custody")
            assignment = AssetAssignment.objects.select_for_update().get(pk=line.assignment_id, asset=asset, returned_at__isnull=True)
            if line.reverses_id != assignment.issue_movement_id:
                raise StockError("Return must reference the assignment issue movement")
        if kind == "STOCK_OUT":
            if not ProductModel.objects.filter(pk=asset.product_model_id, is_active=True).exists():
                raise StockError("Inactive products cannot be issued")
            if not line.recipient_id or not AssetRecipient.objects.filter(pk=line.recipient_id, is_active=True).exists():
                raise StockError("Active recipient required")
            if AssetAssignment.objects.filter(asset=asset, returned_at__isnull=True).exists():
                raise StockError("Asset already has active custody")
    else:
        values["product_model_id"] = line.product_model_id
        if kind == "RETURN" and not line.reverses_id:
            raise StockError("Bulk return requires its original issue movement")
        source = _bucket(line.product_model_id, line.source_location_id, line.source_condition, line.source_state) if line.source_location_id else None
        destination = _bucket(line.product_model_id, line.destination_location_id, line.condition, line.state) if line.destination_location_id else None
        if source and destination and source.pk == destination.pk:
            raise StockError("No-op bucket transfer")
        if kind == "STOCK_OUT" and source.stock_state != "AVAILABLE":
            raise StockError("Only available bulk stock can be issued")
        values.update(source_balance=source, destination_balance=destination)
    if line.reverses_id:
        original = StockMovement.objects.select_for_update().get(pk=line.reverses_id)
        used = original.reversal_entries.aggregate(total=Sum("quantity"))["total"] or 0
        if original.reverses_id or used + line.quantity > original.quantity:
            raise StockError("Reversal exceeds eligible original quantity")
        if (original.asset_id, original.product_model_id) != (values.get("asset").pk if values.get("asset") else None, values.get("product_model_id")):
            raise StockError("Reversal target mismatch")
        if kind == "RETURN":
            if original.operation_type != "STOCK_OUT":
                raise StockError("Returns reference an issue")
        elif (line.source_location_id, line.destination_location_id) != (original.destination_location_id, original.source_location_id):
            raise StockError("Reversal must invert original endpoints")
    movement = StockMovement(**values)
    movement.full_clean()
    movement.save(force_insert=True)
    if asset:
        asset.condition = movement.condition_after
        asset.lifecycle_status = movement.lifecycle_after
        asset.current_location_id = line.destination_location_id
        asset.version += 1
        asset.save(update_fields=["condition", "lifecycle_status", "current_location", "version", "updated_at"])
        if kind == "STOCK_OUT":
            due_at = datetime.fromisoformat(line.due_at) if line.due_at else None
            if due_at and (timezone.is_naive(due_at) or due_at < moment):
                raise StockError("Expected return must be an aware future timestamp")
            AssetAssignment.objects.create(asset=asset, recipient_id=line.recipient_id, issued_by=actor,
                assigned_at=moment, due_at=due_at, issue_movement=movement,
                destination_reference=line.destination_reference, destination_description=line.destination_description,
                purpose=line.purpose)
        if assignment:
            assignment.returned_at = moment
            assignment.returned_by = actor
            assignment.return_movement = movement
            assignment.save(update_fields=["returned_at", "returned_by", "return_movement", "updated_at"])
    else:
        if source:
            if not StockBalance.objects.filter(pk=source.pk, quantity__gte=line.quantity).update(quantity=F("quantity")-line.quantity, version=F("version")+1, updated_at=moment):
                raise StockError("Insufficient stock")
        if destination:
            StockBalance.objects.filter(pk=destination.pk).update(quantity=F("quantity")+line.quantity, version=F("version")+1, updated_at=moment)
