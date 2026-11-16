"""Synthetic PostgreSQL coverage for manual command endpoints."""
from uuid import uuid4
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import DatabaseError,connection,close_old_connections
from django.test import TestCase,TransactionTestCase,Client,override_settings
from apps.inventory.models import AssetCategory,ProductModel,Asset,StockBalance
from apps.warehouse.models import Warehouse,StorageLocation
from apps.accounts.models import AssetRecipient
from apps.audits.models import AssetChangeLog
from apps.transactions.models import StockMovement,StockOperation,AssetAssignment
from apps.transactions.manual_service import execute
from apps.transactions.manual_serializers import Registration
URL="/api/transactions/manual/"
def fixtures():
 u=get_user_model().objects.create_user(username="manual-operator")
 u.user_permissions.add(*Permission.objects.exclude(content_type__model__startswith="import"))
 cat=AssetCategory.objects.create(code="MANUAL",name="Manual")
 p=ProductModel.objects.create(sku_code="SERIAL",name="Serialized",category=cat,tracking_mode="SERIALIZED")
 b=ProductModel.objects.create(sku_code="BULK",name="Bulk",category=cat,tracking_mode="BULK")
 w=Warehouse.objects.create(code="SITE",name="Site")
 l=StorageLocation.objects.create(code="A",name="Area A",warehouse=w,kind="AREA")
 d=StorageLocation.objects.create(code="B",name="Area B",warehouse=w,kind="AREA")
 r=AssetRecipient.objects.create(code="RECIPIENT",name="Synthetic recipient")
 return u,p,b,l,d,r
def registration(p,l,**extra):
 return dict(operation_key=str(uuid4()),reason="Manual fixture",external_reference="",product_model_id=p.pk,destination_location_id=l.pk,condition="USED",state="AVAILABLE",device_name="Device",serial_raw="00123",description="Test description",**extra)
@override_settings(MANUAL_INVENTORY_ENABLED=True)
class ManualTests(TestCase):
 def setUp(self):
  self.user,self.product,self.bulk,self.loc,self.dest,self.recipient=fixtures()
  self.client.force_login(self.user)
 def send(self,a,d):return self.client.post(URL+a+"/",d,content_type="application/json")
 def receive(self):
  return self.send("register",registration(self.product,self.loc))
 def test_registration_receipt_audit_metadata(self):
  res=self.receive();self.assertEqual(res.status_code,201,res.content)
  a=Asset.objects.get();self.assertTrue(a.asset_tag.startswith("AST-"));self.assertEqual(a.serial_raw,"00123")
  self.assertEqual(a.description,"Test description");self.assertEqual(StockMovement.objects.get().asset,a)
  self.assertEqual(AssetChangeLog.objects.get().action,"MANUAL_REGISTER")
 def test_unknown_fields_and_tag_injection_rejected(self):
  d=registration(self.product,self.loc);d["asset_tag"]="FORGED"
  self.assertEqual(self.send("register",d).status_code,400);self.assertFalse(Asset.objects.exists())
 def test_duplicate_serial_warns_and_never_merges(self):
  self.receive();res=self.receive()
  self.assertEqual(res.status_code,201,res.content);self.assertIn("DUPLICATE_SERIAL_REQUIRES_REVIEW",res.json()["warnings"])
  self.assertEqual(Asset.objects.count(),2)
 def test_generated_tag_collision_rolls_back(self):
  self.receive()
  # Force a real duplicate asset tag; the unique index must reject it.
  a=Asset.objects.get()
  with patch.object(Asset._meta.get_field("asset_tag"), "_get_default", lambda: a.asset_tag):
   res=self.receive()
  self.assertEqual(res.status_code,503);self.assertEqual(Asset.objects.count(),1)
 def test_atomic_audit_failure(self):
  with patch("apps.transactions.manual_service.AssetChangeLog.objects.create",side_effect=DatabaseError("private failure")):
   r=self.receive()
  self.assertEqual(r.status_code,503);self.assertNotIn("private",r.content.decode())
  self.assertEqual(Asset.objects.count(),0);self.assertEqual(StockMovement.objects.count(),0);self.assertEqual(StockOperation.objects.count(),0)
 def test_idempotent_retry_and_changed_description_conflict(self):
  d=registration(self.product,self.loc)
  self.assertEqual(self.send("register",d).status_code,201)
  self.assertTrue(self.send("register",d).json()["replayed"])
  d["description"]="Changed";self.assertEqual(self.send("register",d).status_code,409)
  self.assertEqual(Asset.objects.count(),1);self.assertEqual(AssetChangeLog.objects.count(),1)
 def test_replay_requires_current_permission(self):
  d=registration(self.product,self.loc);self.send("register",d)
  self.user.user_permissions.remove(Permission.objects.get(codename="receive_stock"))
  self.assertEqual(self.send("register",d).status_code,403)
 def test_bulk_receipt_and_negative_rejected(self):
  d=registration(self.bulk,self.loc)
  for k in ("device_name","serial_raw","description"):d.pop(k)
  d["quantity"]=7
  self.assertEqual(self.send("receive",d).status_code,201)
  self.assertEqual(StockBalance.objects.get().quantity,7)
  d.update(operation_key=str(uuid4()),quantity=-1)
  self.assertEqual(self.send("receive",d).status_code,400)
 def test_tracking_mode_mismatch(self):
  self.assertEqual(self.send("register",registration(self.bulk,self.loc)).status_code,400)
 def test_inactive_location(self):
  self.loc.is_active=False;self.loc.save()
  self.assertEqual(self.receive().status_code,409)
 def test_unusable_stock_requires_quarantine(self):
  d=registration(self.product,self.loc);d["condition"]="BROKEN"
  self.assertEqual(self.send("register",d).status_code,409)
 def test_serialized_transfer(self):
  self.receive();a=Asset.objects.get()
  d=dict(operation_key=str(uuid4()),reason="Move",asset_id=a.pk,quantity=1,source_location_id=self.loc.pk,source_condition="USED",source_state="AVAILABLE",destination_location_id=self.dest.pk,condition="USED",state="AVAILABLE")
  self.assertEqual(self.send("transfer",d).status_code,201)
  a.refresh_from_db();self.assertEqual(a.current_location,self.dest)
 def test_bulk_transfer_and_insufficient_stock(self):
  d=dict(operation_key=str(uuid4()),reason="Receive",product_model_id=self.bulk.pk,destination_location_id=self.loc.pk,condition="NEW",state="AVAILABLE",quantity=5)
  self.send("receive",d)
  t=dict(operation_key=str(uuid4()),reason="Move",product_model_id=self.bulk.pk,quantity=3,source_location_id=self.loc.pk,source_condition="NEW",source_state="AVAILABLE",destination_location_id=self.dest.pk,condition="NEW",state="AVAILABLE")
  self.assertEqual(self.send("transfer",t).status_code,201)
  self.assertEqual(sum(StockBalance.objects.values_list("quantity",flat=True)),5)
  t["operation_key"]=str(uuid4());self.assertEqual(self.send("transfer",t).status_code,409)
 def test_issue_and_return(self):
  self.receive();a=Asset.objects.get()
  d=dict(operation_key=str(uuid4()),reason="Issue",asset_id=a.pk,quantity=1,source_location_id=self.loc.pk,source_condition="USED",source_state="AVAILABLE",recipient_id=self.recipient.pk)
  self.assertEqual(self.send("issue",d).status_code,201)
  a.refresh_from_db();self.assertEqual(a.lifecycle_status,"ASSIGNED");assignment=AssetAssignment.objects.get()
  d=dict(operation_key=str(uuid4()),reason="Return",asset_id=a.pk,assignment_id=assignment.pk,destination_location_id=self.dest.pk,condition="USED",state="AVAILABLE")
  self.assertEqual(self.send("return",d).status_code,201)
  assignment.refresh_from_db();self.assertIsNotNone(assignment.returned_at)
  d["operation_key"]=str(uuid4());self.assertEqual(self.send("return",d).status_code,409)
 def test_unknown_recipient_denied(self):
  self.receive();a=Asset.objects.get()
  d=dict(operation_key=str(uuid4()),reason="Issue",asset_id=a.pk,quantity=1,source_location_id=self.loc.pk,source_condition="USED",source_state="AVAILABLE",recipient_id=999999)
  self.assertEqual(self.send("issue",d).status_code,409)
 def test_authentication_and_explicit_capability(self):
  self.client.logout();self.assertEqual(self.receive().status_code,401)
  user=get_user_model().objects.create_superuser(username="ungranted",password="synthetic")
  self.client.force_login(user);self.assertEqual(self.receive().status_code,403)
 def test_csrf_required(self):
  c=Client(enforce_csrf_checks=True);c.force_login(self.user)
  self.assertEqual(c.post(URL+"register/",registration(self.product,self.loc),content_type="application/json").status_code,403)
 def test_read_endpoints_and_immutable_history(self):
  self.receive()
  for name in ("movements","recipients","assignments","balances"):
   res=self.client.get("/api/transactions/"+name+"/");self.assertEqual(res.status_code,200,res.content)
   self.assertEqual(self.client.post("/api/transactions/"+name+"/",{},content_type="application/json").status_code,405)
 def test_disabled_deployment_fails_closed(self):
  with override_settings(MANUAL_INVENTORY_ENABLED=False):
   self.assertEqual(self.receive().status_code,503)
   self.assertEqual(Asset.objects.count(),0)
 def test_registration_fields_required(self):
  d=registration(self.product,self.loc);d.pop("condition")
  self.assertEqual(self.send("register",d).status_code,400)
 def test_same_location_or_reclassification_transfer_denied(self):
  self.receive();a=Asset.objects.get()
  d=dict(operation_key=str(uuid4()),reason="Move",asset_id=a.pk,quantity=1,source_location_id=self.loc.pk,source_condition="USED",source_state="AVAILABLE",destination_location_id=self.loc.pk,condition="USED",state="AVAILABLE")
  self.assertEqual(self.send("transfer",d).status_code,409)
  d.update(destination_location_id=self.dest.pk,condition="NEW")
  self.assertEqual(self.send("transfer",d).status_code,409)

class ConcurrencyTests(TransactionTestCase):
 def test_same_key_posts_exactly_once(self):
  u,p,b,l,d,r=fixtures();payload=registration(p,l)
  serializer=Registration(data=payload);serializer.is_valid(raise_exception=True);data=serializer.validated_data
  gate=Barrier(2)
  def worker():
   close_old_connections()
   try:
    gate.wait()
    return execute(actor=u,action="register",data=data)
   finally:connection.close()
  with ThreadPoolExecutor(max_workers=2) as pool:
   results=list(pool.map(lambda _:worker(),range(2)))
  self.assertEqual(sum(r["replayed"] for r in results),1)
  self.assertEqual(Asset.objects.count(),1);self.assertEqual(StockMovement.objects.count(),1);self.assertEqual(AssetChangeLog.objects.count(),1)
