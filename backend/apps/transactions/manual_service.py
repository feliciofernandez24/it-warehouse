"""Manual operations compose existing posting and append-only audit atomically."""
import hashlib, json
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from rest_framework.exceptions import PermissionDenied, ValidationError
from apps.audits.models import AssetChangeLog
from apps.inventory.models import Asset, ProductModel
from apps.warehouse.models import StorageLocation
from .models import AssetAssignment, StockMovement, StockOperation
from .services import Line, Request, post
from .services.permissions import require
from .services.exceptions import IdempotencyConflict, StockError

KINDS = {"register":"STOCK_IN","receive":"STOCK_IN","transfer":"TRANSFER","issue":"STOCK_OUT","return":"RETURN"}
CAPS = {"register":"receive_stock","receive":"receive_stock","transfer":"transfer_stock","issue":"issue_stock","return":"return_stock"}

def authorize(actor, action):
    actor = get_user_model().objects.get(pk=actor.pk)
    require(actor, CAPS[action])
    required = ["inventory.view_productmodel","warehouse.view_storagelocation","warehouse.view_warehouse"]
    if action != "receive": required.append("inventory.view_asset")
    if action == "register": required.append("inventory.add_asset")
    if action in ("issue","return"): required += ["accounts.view_assetrecipient","transactions.view_assetassignment"]
    if not actor.is_active or not all(actor.has_perm(p) for p in required):
        raise PermissionDenied()
    return actor

def describe(result):
    result["assets"] = list(Asset.objects.filter(pk__in=result["asset_ids"]).order_by("pk").values("id","asset_tag"))
    result["receipt"] = list(StockMovement.objects.filter(id__in=result["movement_ids"]).order_by("line_number").values("id","public_id","recorded_at","operation_type","quantity"))
    return result

@transaction.atomic
def execute(*, actor, action, data):
    with connection.cursor() as c: c.execute("SELECT pg_advisory_xact_lock(73921,2)")
    actor = authorize(actor, action)
    payload = {"action":action,"data":json.loads(json.dumps(data,default=str,sort_keys=True))}
    fingerprint = hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    key = data["operation_key"]
    previous = StockOperation.objects.filter(pk=key).first()
    if previous:
        audit = AssetChangeLog.objects.filter(operation_key=key).values("after","actor_id").first()
        if not previous.posted_at or previous.requested_by_id != actor.pk or not audit or audit["actor_id"] != actor.pk or audit["after"].get("manual_fingerprint") != fingerprint:
            raise IdempotencyConflict("Operation key conflicts with a different request.")
        # Authorization rechecked above; replay uses original immutable identifiers.
        ids=list(StockMovement.objects.filter(operation_key=key).order_by("line_number").values_list("id",flat=True))
        assets=list(StockMovement.objects.filter(operation_key=key,asset__isnull=False).values_list("asset_id",flat=True))
        return describe({"operation_key":str(key),"movement_ids":ids,"asset_ids":assets,"replayed":True,"warnings":audit["after"].get("warnings",[])})
    values={k:v for k,v in data.items() if k not in ("operation_key","reason","external_reference","description","assignment_id")}
    if action in ("register","receive"):
        product=ProductModel.objects.select_for_update().get(pk=data["product_model_id"])
        expected="SERIALIZED" if action=="register" else "BULK"
        if product.tracking_mode != expected: raise ValidationError("Product tracking mode does not match this operation.")
        if not product.category.is_active or (product.manufacturer_id and not product.manufacturer.is_active):
            raise ValidationError("Product category/manufacturer must be active.")
        if action=="register": values["quantity"]=1
    asset=None
    if data.get("asset_id"):
        asset=Asset.objects.select_for_update().get(pk=data["asset_id"])
        if action in ("issue","transfer") and (asset.current_location_id!=data["source_location_id"] or asset.condition!=data["source_condition"] or asset.lifecycle_status!=data["source_state"]):
            raise StockError("Source no longer matches the asset; refresh.")
        if action=="transfer" and (data["condition"]!=asset.condition or data["state"]!=asset.lifecycle_status):
            raise StockError("Transfers preserve condition and lifecycle.")
    if action=="transfer":
        if data["source_location_id"]==data["destination_location_id"]:raise StockError("Choose a different location.")
        if data["source_condition"]!=data["condition"] or data["source_state"]!=data["state"]:
            raise StockError("Transfers preserve condition and stock state.")
    if action=="return":
        assignment=AssetAssignment.objects.select_for_update().get(pk=data["assignment_id"],asset=asset,returned_at__isnull=True)
        values.update(quantity=1,assignment_id=assignment.pk,reverses_id=assignment.issue_movement_id)
    if action=="issue":
        values.update(condition=asset.condition,state="AVAILABLE")
    warnings=[]
    serial=data.get("serial_raw","")
    if action=="register" and serial.strip() and Asset.objects.filter(serial_normalized=serial.strip().casefold()).exists():
        warnings.append("DUPLICATE_SERIAL_REQUIRES_REVIEW")
    if action=="register" and not serial.strip():warnings.append("SERIAL_NOT_PROVIDED")
    result=post(actor=actor,request=Request(key,(Line(KINDS[action],**values),),data["reason"],data["external_reference"]))
    if action=="register" and data["description"]:
        # Metadata only; receipt remains the sole creator of stock and asset identity.
        Asset.objects.filter(pk=result.asset_ids[0]).update(description=data["description"])
    AssetChangeLog.objects.create(entity_kind="transactions.stockmovement",entity_pk=result.movement_ids[0],
        asset_id=result.asset_ids[0] if result.asset_ids else None,actor=actor,action="MANUAL_"+action.upper(),
        operation_key=key,before={},after={"manual_fingerprint":fingerprint,"movement_ids":list(result.movement_ids),"asset_ids":list(result.asset_ids),"warnings":warnings},reason=data["reason"])
    return describe({"operation_key":str(key),"movement_ids":list(result.movement_ids),"asset_ids":list(result.asset_ids),"replayed":False,"warnings":warnings})
