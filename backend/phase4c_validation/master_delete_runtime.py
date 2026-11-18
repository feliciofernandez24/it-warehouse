"""Synthetic nonowner proof for the five-table deletion privilege boundary."""
import os,sys,json,unittest
import psycopg
if os.environ.get("ITW_PHASE4B_TEST")!="1" or os.environ.get("POSTGRES_HOST")!="127.0.0.1" or os.environ.get("POSTGRES_DB")!="phase3b2b1_test":
 raise RuntimeError("DISPOSABLE_CONTEXT_REQUIRED")
password=os.environ["POSTGRES_PASSWORD"];os.environ["POSTGRES_DB"]="phase4c_runtime_test"
sys.path.insert(0,"/app");os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings.development")
import django;django.setup()
from django.db import connection
from django.test import Client,override_settings
from django.contrib.auth import get_user_model
from apps.inventory.models import AssetCategory,Manufacturer,ProductModel
from apps.warehouse.models import Warehouse,StorageLocation
from apps.audits.models import AssetChangeLog
user=get_user_model().objects.get(username="manual-operator")
category=AssetCategory.objects.create(code="DELETE",name="Unused")
manufacturer=Manufacturer.objects.create(code="DELETE",name="Unused")
product=ProductModel.objects.create(sku_code="DELETE",name="Unused",category=category,tracking_mode="BULK")
site=Warehouse.objects.create(code="DELETE",name="Unused")
location=StorageLocation.objects.create(code="DELETE",name="Unused",warehouse=site,kind="AREA")
role="itw_phase4c_runtime"
# These reads already exist in the combined deployed Phase 4A/B/C role.
with connection.cursor() as c:
 c.execute("GRANT SELECT ON inventory_stockthreshold TO "+role)
 for table in ["inventory_assetcategory","inventory_manufacturer","warehouse_warehouse","warehouse_storagelocation"]:
  c.execute("GRANT UPDATE (version) ON "+table+" TO "+role)
connection.close();connection.settings_dict.update(USER=role,PASSWORD="phase4c-synthetic-only")
def admin():
 return psycopg.connect(host="127.0.0.1",dbname="phase4c_runtime_test",user="postgres",password=password,autocommit=True)
class RuntimeDeleteTests(unittest.TestCase):
 def setUp(self):
  self.client=Client(enforce_csrf_checks=True);self.client.force_login(user)
  self.token=self.client.get("/api/auth/csrf/").json()["csrfToken"]
 def delete(self,path,obj):
  return self.client.delete("/api/management/"+path+"/"+str(obj.pk)+"/",{"expected_version":obj.version,"change_reason":"Unused synthetic master"},content_type="application/json",HTTP_X_CSRFTOKEN=self.token)
 def test_01_without_new_acl_fails_closed(self):
  r=self.delete("categories",category);self.assertEqual(r.status_code,409) # product reference precedes deletion
  r=self.delete("manufacturers",manufacturer);self.assertEqual(r.status_code,503)
  with admin() as c:self.assertEqual(c.execute("SELECT count(*) FROM inventory_manufacturer WHERE id=%s",(manufacturer.pk,)).fetchone()[0],1)
 def test_02_allowlisted_deletes_and_audits(self):
  with admin() as c:
   c.execute("GRANT DELETE ON inventory_assetcategory,inventory_manufacturer,inventory_productmodel,warehouse_warehouse,warehouse_storagelocation TO "+role)
   c.execute("GRANT SELECT (product_model_id) ON inventory_assetspecification TO "+role)
  for resource,obj in [("product-models",product),("categories",category),("manufacturers",manufacturer),("locations",location),("warehouses",site)]:
   response=self.delete(resource,obj);self.assertEqual(response.status_code,204,response.content)
  with admin() as c:
   events=c.execute("SELECT before,after FROM audits_assetchangelog WHERE action='MASTER_DELETE'").fetchall()
   self.assertEqual(len(events),5);self.assertTrue(all(e[0]["name"]=="Unused" and e[1]=={} for e in events))
 def test_03_forbidden_deletes_remain_denied(self):
  with connection.cursor() as c:
   for table in ["inventory_asset","inventory_stockbalance","transactions_stockmovement","transactions_stockoperation","audits_assetchangelog","inventory_importreviewevent","auth_user","django_migrations"]:
    c.execute("SELECT has_table_privilege(current_user,%s,'DELETE')",[table]);self.assertFalse(c.fetchone()[0],table)
   c.execute("SELECT has_schema_privilege(current_user,'public','CREATE')");self.assertFalse(c.fetchone()[0])
 def test_04_no_csrf_no_delete(self):
  r=self.client.delete("/api/management/categories/1/",{},content_type="application/json");self.assertEqual(r.status_code,403)
 def test_05_deletion_and_audit_rollback_together(self):
  with admin() as c:
   key=c.execute("INSERT INTO warehouse_warehouse(code,name,description,is_active,version,created_at,updated_at,address) VALUES('KEEP','Keep','',true,0,now(),now(),'') RETURNING id").fetchone()[0]
   c.execute("REVOKE INSERT ON audits_assetchangelog FROM "+role)
   try:
    obj=Warehouse.objects.get(pk=key);r=self.delete("warehouses",obj);self.assertEqual(r.status_code,503,r.content)
    self.assertEqual(c.execute("SELECT count(*) FROM warehouse_warehouse WHERE id=%s",(key,)).fetchone()[0],1)
   finally:c.execute("GRANT INSERT ON audits_assetchangelog TO "+role)
with override_settings(ALLOWED_HOSTS=["testserver"],MASTER_DATA_DELETE_ENABLED=True):
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeDeleteTests))
print("MASTER_DELETE_RUNTIME="+json.dumps({"ran":result.testsRun,"failed":len(result.failures),"errors":len(result.errors),"skipped":len(result.skipped)}))
sys.exit(0 if result.wasSuccessful() else 1)
