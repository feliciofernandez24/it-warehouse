"""Master writer proof: real nonowner LOGIN, synthetic clone, no operational grants."""
import json,os,sys,unittest
import psycopg
if (os.environ.get("ITW_PHASE4B_TEST")!="1" or os.environ.get("POSTGRES_DB")!="phase3b2b1_test"
    or os.environ.get("POSTGRES_HOST")!="127.0.0.1" or os.environ.get("POSTGRES_PASSWORD")!="phase3b2d2-synthetic-only"):
    raise RuntimeError("EXPLICIT_DISPOSABLE_CONTEXT_REQUIRED")
with psycopg.connect(host="127.0.0.1",dbname="phase3b2b1_test",user="postgres",password="phase3b2d2-synthetic-only",autocommit=True) as admin:
    admin.execute("CREATE DATABASE phase4b_runtime_test TEMPLATE phase3b2b1_test")
os.environ["POSTGRES_DB"]="phase4b_runtime_test"
sys.path.insert(0,"/app");os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings.development")
import django;django.setup()
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import Client,override_settings
from config.test_phase4b import editor
from apps.inventory.models import AssetCategory,ProductModel
from apps.warehouse.models import Warehouse,StorageLocation
from apps.transactions.services import Line,Request,post
from uuid import uuid4
with connection.cursor() as c:
    c.execute("SELECT current_database(),current_user,current_setting('server_version_num')")
    assert c.fetchone()==("phase4b_runtime_test","postgres","170011")
user=editor("phase4b-editor")
user.user_permissions.add(*Permission.objects.filter(content_type__app_label="transactions"))
category=AssetCategory.objects.create(code="P4B",name="Synthetic category")
product=ProductModel.objects.create(sku_code="P4B",name="Synthetic equipment",category=category,tracking_mode="SERIALIZED")
site=Warehouse.objects.create(code="P4B",name="Synthetic warehouse")
location=StorageLocation.objects.create(code="P4B",name="Synthetic area",warehouse=site,kind="AREA")
asset_id=post(actor=user,request=Request(uuid4(),(Line("STOCK_IN",product_model_id=product.pk,
    destination_location_id=location.pk,device_name="Synthetic device"),),"Synthetic setup")).asset_ids[0]
selects=["auth_user","auth_group","auth_permission","auth_user_groups","auth_user_user_permissions","auth_group_permissions",
"django_content_type","django_session","inventory_asset","inventory_assetcategory","inventory_manufacturer","inventory_productmodel",
"inventory_stockbalance","inventory_stockthreshold","warehouse_warehouse","warehouse_storagelocation","transactions_stockmovement",
"transactions_assetassignment","transactions_stockoperation","audits_physicalinventoryaudit","audits_auditline"]
updates={
"inventory_assetcategory":"name,description,is_active,version,updated_at",
"inventory_manufacturer":"name,description,is_active,version,updated_at",
"inventory_productmodel":"name,category_id,manufacturer_id,model_number,part_number,tracking_mode,description,is_active,version,updated_at",
"warehouse_warehouse":"name,description,address,is_active,version,updated_at",
"warehouse_storagelocation":"name,warehouse_id,parent_id,kind,is_active,version,updated_at",
"inventory_asset":"device_name,serial_raw,serial_normalized,serial_review_state,description,remarks,version,updated_at"}
with connection.cursor() as c:
    c.execute("CREATE ROLE itw_phase4b_runtime LOGIN PASSWORD 'phase4b-runtime-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS")
    c.execute("REVOKE ALL ON DATABASE phase4b_runtime_test FROM PUBLIC")
    c.execute("GRANT CONNECT ON DATABASE phase4b_runtime_test TO itw_phase4b_runtime")
    c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    c.execute("GRANT USAGE ON SCHEMA public TO itw_phase4b_runtime")
    for table in selects:c.execute("GRANT SELECT ON "+table+" TO itw_phase4b_runtime")
    c.execute("GRANT UPDATE (password,last_login) ON auth_user TO itw_phase4b_runtime")
    c.execute("GRANT INSERT,UPDATE,DELETE ON django_session TO itw_phase4b_runtime")
    for table,columns in updates.items():c.execute("GRANT UPDATE ("+columns+") ON "+table+" TO itw_phase4b_runtime")
    for table in list(updates)[:-1]:
        c.execute("GRANT INSERT ON "+table+" TO itw_phase4b_runtime")
        c.execute("GRANT USAGE ON SEQUENCE "+table+"_id_seq TO itw_phase4b_runtime")
    c.execute("GRANT INSERT ON audits_assetchangelog TO itw_phase4b_runtime")
    c.execute("GRANT SELECT (id) ON audits_assetchangelog TO itw_phase4b_runtime")
    c.execute("GRANT USAGE ON SEQUENCE audits_assetchangelog_id_seq TO itw_phase4b_runtime")
connection.close();connection.settings_dict.update(USER="itw_phase4b_runtime",PASSWORD="phase4b-runtime-only")
def sql():return psycopg.connect(host="127.0.0.1",dbname="phase4b_runtime_test",user="itw_phase4b_runtime",password="phase4b-runtime-only",autocommit=True)
class WriterTests(unittest.TestCase):
    def test_01_real_login_and_nonowner_flags(self):
        with connection.cursor() as c:
            c.execute("SELECT session_user,current_user");self.assertEqual(c.fetchone(),("itw_phase4b_runtime","itw_phase4b_runtime"))
        with sql() as c:
            self.assertEqual(c.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone(),(False,)*5)
            self.assertEqual(c.execute("SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)").fetchone()[0],0)

    def test_02_csrf_api_master_write_and_atomic_audit(self):
        with override_settings(ALLOWED_HOSTS=["testserver"]):
            client=Client(enforce_csrf_checks=True);client.force_login(user)
            token=client.get("/api/auth/csrf/").json()["csrfToken"]
            ids={}
            for resource in ["categories","manufacturers","product-models","warehouses","locations"]:
                data={"code":"WRITER","name":"Writer created","change_reason":"Synthetic nonowner test"}
                if resource=="product-models":
                    data={"sku_code":"WRITER","name":"Writer created","category":ids["categories"],
                          "manufacturer":ids["manufacturers"],"tracking_mode":"BULK","change_reason":"Synthetic product"}
                if resource=="locations":
                    data.update(warehouse=ids["warehouses"],kind="AREA")
                response=client.post("/api/management/"+resource+"/",data,content_type="application/json",HTTP_X_CSRFTOKEN=token)
                self.assertEqual(response.status_code,201,response.content)
                ids[resource]=response.json()["id"]
                response=client.patch("/api/management/"+resource+"/"+str(ids[resource])+"/",
                    {"name":"Writer corrected","expected_version":0,"change_reason":"Correction"},
                    content_type="application/json",HTTP_X_CSRFTOKEN=token)
                self.assertEqual(response.status_code,200,response.content)
        with psycopg.connect(host="127.0.0.1",dbname="phase4b_runtime_test",user="postgres",password="phase3b2d2-synthetic-only") as admin:
            self.assertEqual(admin.execute("SELECT count(*) FROM audits_assetchangelog WHERE actor_id=%s",(user.pk,)).fetchone()[0],10)

    def test_03_asset_metadata_uses_no_position_grants(self):
        with override_settings(ALLOWED_HOSTS=["testserver"]):
            client=Client();client.force_login(user)
            version=client.get("/api/management/assets/"+str(asset_id)+"/").json()["version"]
            response=client.patch("/api/management/assets/"+str(asset_id)+"/",{"device_name":"Runtime corrected","serial_raw":"NEW",
                "expected_version":version,"change_reason":"Metadata correction"},content_type="application/json")
            self.assertEqual(response.status_code,200,response.content)

    def test_04_protected_evidence_audit_rewrite_and_stock_writes_denied(self):
        with sql() as c:
            for q in ["SELECT * FROM inventory_importreviewevent","INSERT INTO inventory_importbatch DEFAULT VALUES",
                      "SELECT before FROM audits_assetchangelog","UPDATE audits_assetchangelog SET reason='rewrite'","DELETE FROM audits_assetchangelog",
                      "UPDATE inventory_asset SET lifecycle_status='LOST'","UPDATE transactions_stockmovement SET quantity=99",
                      "DELETE FROM transactions_stockmovement","INSERT INTO inventory_asset DEFAULT VALUES"]:
                with self.subTest(q=q),self.assertRaises(psycopg.errors.InsufficientPrivilege):c.execute(q)

    def test_05_ddl_and_owner_assumption_denied(self):
        with sql() as c:
            for q in ["CREATE TABLE public.denied(id int)","CREATE TEMP TABLE denied(id int)",
                      "ALTER TABLE inventory_asset DISABLE TRIGGER USER","SET ROLE postgres","TRUNCATE inventory_assetcategory"]:
                with self.subTest(q=q),self.assertRaises(psycopg.errors.InsufficientPrivilege):c.execute(q)

    def test_06_missing_audit_insert_privilege_fails_closed(self):
        admin=psycopg.connect(host="127.0.0.1",dbname="phase4b_runtime_test",user="postgres",password="phase3b2d2-synthetic-only",autocommit=True)
        try:
            admin.execute("REVOKE INSERT ON audits_assetchangelog FROM itw_phase4b_runtime")
            with override_settings(ALLOWED_HOSTS=["testserver"]):
                client=Client();client.force_login(user)
                response=client.post("/api/management/categories/",{"code":"ROLLBACK","name":"Rollback","change_reason":"No audit grant"},content_type="application/json")
                self.assertEqual(response.status_code,503)
            self.assertEqual(admin.execute("SELECT count(*) FROM inventory_assetcategory WHERE code='ROLLBACK'").fetchone()[0],0)
        finally:
            admin.execute("GRANT INSERT ON audits_assetchangelog TO itw_phase4b_runtime");admin.close()
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WriterTests))
print("PHASE4B_RUNTIME="+json.dumps(dict(ran=result.testsRun,failed=len(result.failures),errors=len(result.errors),skipped=len(result.skipped))))
sys.exit(not result.wasSuccessful())
