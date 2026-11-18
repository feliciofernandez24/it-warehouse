"""Disposable PostgreSQL-only deletion and routing response regression."""
from datetime import date
from uuid import uuid4
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection,close_old_connections,DatabaseError
from django.test import TestCase,TransactionTestCase,Client,override_settings
from django.utils import timezone
from config.test_phase4c import fixtures,registration
from apps.inventory.models import AssetCategory,Manufacturer,ProductModel,StockBalance,AssetSpecification,SpecificationDefinition,Asset
from apps.warehouse.models import Warehouse,StorageLocation
from apps.audits.models import AssetChangeLog,PhysicalInventoryAudit
from apps.transactions.services import Request,Line,request_operation
from apps.inventory.master_delete import remove
P="/api/management/"
@override_settings(MASTER_DATA_DELETE_ENABLED=True,MANUAL_INVENTORY_ENABLED=True)
class DeleteTests(TestCase):
 def setUp(self):
  self.user,self.product,self.bulk,self.loc,self.dest,self.recipient=fixtures();self.client.force_login(self.user)
 def delete(self,resource,obj,**extra):
  return self.client.delete(P+resource+"/"+str(obj.pk)+"/",{"change_reason":"Unused duplicate master","expected_version":obj.version,**extra},content_type="application/json")
 def test_each_unused_master_deleted_and_before_state_audited(self):
  cases=[("categories",AssetCategory.objects.create(code="UNUSED",name="Unused")),
   ("manufacturers",Manufacturer.objects.create(code="UNUSED",name="Unused")),
   ("product-models",ProductModel.objects.create(sku_code="UNUSED",name="Unused",category=self.product.category,tracking_mode="BULK")),
   ("warehouses",Warehouse.objects.create(code="UNUSED",name="Unused")),
   ("locations",StorageLocation.objects.create(code="UNUSED",name="Unused",warehouse=self.loc.warehouse,kind="AREA"))]
  for resource,obj in cases:
   key=obj.pk;res=self.delete(resource,obj);self.assertEqual(res.status_code,204,res.content)
   self.assertFalse(type(obj).objects.filter(pk=key).exists())
   event=AssetChangeLog.objects.get(entity_kind=obj._meta.label_lower,entity_pk=key,action="MASTER_DELETE")
   self.assertEqual(event.before["name"],"Unused");self.assertEqual(event.after,{})
 def test_authentication_and_delete_permission(self):
  obj=AssetCategory.objects.create(code="X",name="X")
  self.client.logout();self.assertEqual(self.delete("categories",obj).status_code,401)
  self.user.user_permissions.remove(Permission.objects.get(codename="delete_assetcategory"));self.client.force_login(self.user)
  self.assertEqual(self.delete("categories",obj).status_code,403)
 def test_csrf_enforced(self):
  obj=Warehouse.objects.create(code="X",name="X");c=Client(enforce_csrf_checks=True);c.force_login(self.user)
  self.assertEqual(c.delete(P+"warehouses/"+str(obj.pk)+"/",{},content_type="application/json").status_code,403)
 def test_feature_disabled(self):
  with override_settings(MASTER_DATA_DELETE_ENABLED=False):
   self.assertEqual(self.delete("categories",self.product.category).status_code,503)
 def test_referenced_category_and_manufacturer(self):
  res=self.delete("categories",self.product.category);self.assertEqual(res.status_code,409);self.assertIn("dependencies",res.json())
  m=Manufacturer.objects.create(code="REF",name="Referenced");self.product.manufacturer=m;self.product.save()
  self.assertEqual(self.delete("manufacturers",m).status_code,409)
 def test_warehouse_with_location(self):
  self.assertEqual(self.delete("warehouses",self.loc.warehouse).status_code,409)
 def test_location_with_child(self):
  StorageLocation.objects.create(code="CHILD",name="Child",warehouse=self.loc.warehouse,parent=self.loc,kind="BIN")
  self.assertEqual(self.delete("locations",self.loc).status_code,409)
 def test_zero_balance_and_product_references(self):
  StockBalance.objects.create(product_model=self.bulk,location=self.loc,quantity=0,condition="USED",stock_state="AVAILABLE")
  self.assertEqual(self.delete("locations",self.loc).status_code,409)
  self.assertEqual(self.delete("product-models",self.bulk).status_code,409)
 def test_product_specification_protects(self):
  definition=SpecificationDefinition.objects.create(code="SPEC",name="Specification",data_type="TEXT")
  AssetSpecification.objects.create(product_model=self.product,definition=definition,text_value="Evidence")
  self.assertEqual(self.delete("product-models",self.product).status_code,409)
 def test_pending_operation_references_protect(self):
  request_operation(actor=self.user,request=Request(uuid4(),(Line("STOCK_IN",product_model_id=self.bulk.pk,destination_location_id=self.loc.pk),),"Pending request"))
  self.assertEqual(self.delete("product-models",self.bulk).status_code,409)
  self.assertEqual(self.delete("locations",self.loc).status_code,409)
 def test_audit_scope_freezes_other_empty_locations(self):
  audit=PhysicalInventoryAudit.objects.create(scope_location=self.loc,performed_by=self.user,planned_date=date(2026,11,17))
  audit.status="COUNTING";audit.started_at=timezone.now();audit.save()
  self.assertEqual(self.delete("locations",self.dest).status_code,409)
 def test_audit_failure_rolls_back_delete(self):
  obj=Warehouse.objects.create(code="KEEP",name="Keep")
  with patch("apps.inventory.master_delete.AssetChangeLog.objects.create",side_effect=DatabaseError("private failure")):
   response=self.delete("warehouses",obj)
  self.assertEqual(response.status_code,503);self.assertTrue(Warehouse.objects.filter(pk=obj.pk).exists())
  self.assertNotIn("private",response.content.decode())
 def test_stale_version_and_unknown_fields(self):
  obj=Warehouse.objects.create(code="KEEP",name="Keep")
  self.assertEqual(self.delete("warehouses",obj,expected_version=9).status_code,409)
  self.assertEqual(self.delete("warehouses",obj,actor_id=self.user.pk).status_code,400)
 def test_assets_and_history_stay_non_deletable(self):
  self.assertEqual(self.client.delete(P+"assets/1/",{},content_type="application/json").status_code,405)
  self.assertEqual(self.client.delete("/api/transactions/movements/1/").status_code,405)
  self.assertEqual(self.client.delete("/api/inventory/categories/1/").status_code,405)
 def test_tag_and_receipt_on_registration_and_replay(self):
  body=registration(self.product,self.loc)
  with override_settings(MANUAL_INVENTORY_ENABLED=True):
   first=self.client.post("/api/transactions/manual/register/",body,content_type="application/json")
   again=self.client.post("/api/transactions/manual/register/",body,content_type="application/json")
  self.assertEqual(first.status_code,201,first.content);self.assertEqual(again.status_code,200)
  self.assertEqual(first.json()["assets"],again.json()["assets"])
  self.assertEqual(first.json()["assets"][0]["asset_tag"],Asset.objects.get().asset_tag)
  self.assertEqual(first.json()["receipt"],again.json()["receipt"])
  self.assertIn("public_id",first.json()["receipt"][0])
 def test_identity_exposes_master_delete_but_not_asset_delete(self):
  data=self.client.get("/api/auth/me/").json()["user"]
  self.assertTrue(data["master_data_delete_enabled"])
  self.assertIn("inventory.delete_assetcategory",data["permissions"])
  self.assertNotIn("inventory.delete_asset",data["permissions"])

@override_settings(MASTER_DATA_DELETE_ENABLED=True)
class DeleteConcurrency(TransactionTestCase):
 def test_simultaneous_deletes_create_one_audit(self):
  user,*_=fixtures();obj=Warehouse.objects.create(code="RACE",name="Race");barrier=Barrier(2)
  def worker():
   close_old_connections()
   try:
    client=Client();client.force_login(user);barrier.wait()
    return client.delete(P+"warehouses/"+str(obj.pk)+"/",{"expected_version":0,"change_reason":"Unused"},content_type="application/json").status_code
   finally:connection.close()
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:worker(),range(2)))
  self.assertEqual(sorted(results),[204,404]);self.assertEqual(AssetChangeLog.objects.filter(action="MASTER_DELETE").count(),1)
