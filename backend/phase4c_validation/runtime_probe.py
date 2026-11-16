"""Real nonowner manual API proof. Disposable context required."""
import os,sys,json,unittest
import psycopg
if os.environ.get("ITW_PHASE4B_TEST")!="1" or os.environ.get("POSTGRES_HOST")!="127.0.0.1" or os.environ.get("POSTGRES_DB")!="phase3b2b1_test":
 raise RuntimeError("DISPOSABLE_CONTEXT_REQUIRED")
password=os.environ["POSTGRES_PASSWORD"]
with psycopg.connect(host="127.0.0.1",dbname="postgres",user="postgres",password=password,autocommit=True) as c:
 c.execute("CREATE DATABASE phase4c_runtime_test")
os.environ["POSTGRES_DB"]="phase4c_runtime_test"
sys.path.insert(0,"/app");os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings.development")
import django;django.setup()
from django.core.management import call_command
from django.db import connection
from django.test import Client,override_settings
from config.test_phase4c import fixtures,registration,URL
from apps.inventory.models import Asset
from apps.transactions.models import StockMovement
from uuid import uuid4
call_command("migrate",verbosity=0)
user,product,bulk,location,destination,recipient=fixtures()
selects=["auth_user","auth_group","auth_permission","auth_user_groups","auth_user_user_permissions","auth_group_permissions","django_content_type","django_session","inventory_asset","inventory_assetcategory","inventory_manufacturer","inventory_productmodel","inventory_stockbalance","warehouse_warehouse","warehouse_storagelocation","transactions_stockmovement","transactions_stockoperation","transactions_assetassignment","accounts_assetrecipient","audits_physicalinventoryaudit","audits_auditline"]
inserts=["inventory_asset","inventory_stockbalance","transactions_stockmovement","transactions_stockoperation","transactions_assetassignment","audits_assetchangelog","django_session"]
updates={"inventory_productmodel":"version","transactions_stockmovement":"id","inventory_asset":"condition,lifecycle_status,current_location_id,version,updated_at,description","inventory_stockbalance":"quantity,version,updated_at","transactions_stockoperation":"posted_at","transactions_assetassignment":"returned_at,returned_by_id,return_movement_id,updated_at","django_session":"session_data,expire_date","auth_user":"last_login"}
with connection.cursor() as c:
 c.execute("CREATE ROLE itw_phase4c_runtime LOGIN PASSWORD 'phase4c-synthetic-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS")
 c.execute("REVOKE ALL ON DATABASE phase4c_runtime_test FROM PUBLIC")
 c.execute("GRANT CONNECT ON DATABASE phase4c_runtime_test TO itw_phase4c_runtime")
 c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
 c.execute("GRANT USAGE ON SCHEMA public TO itw_phase4c_runtime")
 for table in selects:c.execute("GRANT SELECT ON "+table+" TO itw_phase4c_runtime")
 for table in inserts:c.execute("GRANT INSERT ON "+table+" TO itw_phase4c_runtime")
 for table,cols in updates.items():c.execute("GRANT UPDATE ("+cols+") ON "+table+" TO itw_phase4c_runtime")
 c.execute("GRANT DELETE ON django_session TO itw_phase4c_runtime")
 for table in inserts:
  if table not in ("transactions_stockoperation","django_session"):c.execute("GRANT USAGE ON SEQUENCE "+table+"_id_seq TO itw_phase4c_runtime")
 c.execute("GRANT SELECT (id,operation_key,after,actor_id) ON audits_assetchangelog TO itw_phase4c_runtime")
connection.close();connection.settings_dict.update(USER="itw_phase4c_runtime",PASSWORD="phase4c-synthetic-only")
def sql():return psycopg.connect(host="127.0.0.1",dbname="phase4c_runtime_test",user="itw_phase4c_runtime",password="phase4c-synthetic-only",autocommit=True)
class RuntimeTests(unittest.TestCase):
 def setUp(self):
  self.client=Client(enforce_csrf_checks=True);self.client.force_login(user)
  self.token=self.client.get("/api/auth/csrf/").json()["csrfToken"]
 def send(self,action,payload):return self.client.post(URL+action+"/",payload,content_type="application/json",HTTP_X_CSRFTOKEN=self.token)
 def test_01_role_is_nonowner_no_memberships(self):
  with sql() as c:
   self.assertEqual(c.execute("SELECT session_user,current_user").fetchone(),("itw_phase4c_runtime",)*2)
   self.assertEqual(c.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone(),(False,)*5)
   self.assertEqual(c.execute("SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)").fetchone()[0],0)
 def test_02_receipt_replay_transfer_issue_return(self):
  d=registration(product,location);res=self.send("register",d);self.assertEqual(res.status_code,201,res.content)
  self.assertTrue(self.send("register",d).json()["replayed"]);asset=res.json()["asset_ids"][0]
  move=dict(operation_key=str(uuid4()),reason="Move",asset_id=asset,quantity=1,source_location_id=location.pk,source_condition="USED",source_state="AVAILABLE",destination_location_id=destination.pk,condition="USED",state="AVAILABLE")
  res=self.send("transfer",move);self.assertEqual(res.status_code,201,res.content)
  issue=dict(operation_key=str(uuid4()),reason="Issue",asset_id=asset,quantity=1,source_location_id=destination.pk,source_condition="USED",source_state="AVAILABLE",recipient_id=recipient.pk)
  res=self.send("issue",issue);self.assertEqual(res.status_code,201,res.content)
  from apps.transactions.models import AssetAssignment
  assignment=AssetAssignment.objects.get(asset_id=asset)
  returned=dict(operation_key=str(uuid4()),reason="Return",asset_id=asset,assignment_id=assignment.pk,destination_location_id=location.pk,condition="USED",state="AVAILABLE")
  res=self.send("return",returned);self.assertEqual(res.status_code,201,res.content)
 def test_03_bulk_receipt_and_transfer(self):
  d=dict(operation_key=str(uuid4()),reason="Bulk receive",product_model_id=bulk.pk,destination_location_id=location.pk,condition="NEW",state="AVAILABLE",quantity=4)
  res=self.send("receive",d);self.assertEqual(res.status_code,201,res.content)
  move=dict(operation_key=str(uuid4()),reason="Move",product_model_id=bulk.pk,quantity=3,source_location_id=location.pk,source_condition="NEW",source_state="AVAILABLE",destination_location_id=destination.pk,condition="NEW",state="AVAILABLE")
  res=self.send("transfer",move);self.assertEqual(res.status_code,201,res.content)
 def test_04_review_ddl_ledger_and_owner_denied(self):
  for statement in ["SELECT * FROM inventory_importreviewevent","UPDATE transactions_stockmovement SET reason='tamper'","UPDATE transactions_stockmovement SET id=id","DELETE FROM transactions_stockmovement","TRUNCATE inventory_asset","ALTER TABLE inventory_asset DISABLE TRIGGER ALL","CREATE TABLE public.not_allowed(id int)","SET ROLE postgres"]:
   with self.subTest(sql=statement),sql() as c:
    with self.assertRaises(psycopg.Error):c.execute(statement)
 def test_05_no_csrf_no_write(self):
  self.assertEqual(self.client.post(URL+"register/",registration(product,location),content_type="application/json").status_code,403)
 def test_06_missing_audit_grant_rolls_back(self):
  before=Asset.objects.count()
  with psycopg.connect(host="127.0.0.1",dbname="phase4c_runtime_test",user="postgres",password=password,autocommit=True) as c:
   c.execute("REVOKE INSERT ON audits_assetchangelog FROM itw_phase4c_runtime")
   try:
    res=self.send("register",registration(product,location));self.assertEqual(res.status_code,503,res.content)
    self.assertEqual(Asset.objects.count(),before)
   finally:c.execute("GRANT INSERT ON audits_assetchangelog TO itw_phase4c_runtime")
with override_settings(ALLOWED_HOSTS=["testserver"],MANUAL_INVENTORY_ENABLED=True):
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeTests))
print("PHASE4C_RUNTIME="+json.dumps({"ran":result.testsRun,"failed":len(result.failures),"errors":len(result.errors),"skipped":len(result.skipped)}))
sys.exit(0 if result.wasSuccessful() else 1)
