"""Real nonowner LOGIN API proof on a synthetic, disposable-only database."""
import json,os,sys,unittest
from pathlib import Path
import psycopg
if (os.environ.get("ITW_PHASE4A_TEST")!="1" or os.environ.get("POSTGRES_DB")!="phase3b2b1_test"
    or os.environ.get("POSTGRES_HOST")!="127.0.0.1" or os.environ.get("POSTGRES_PASSWORD")!="phase3b2d2-synthetic-only"):
    raise RuntimeError("EXPLICIT_DISPOSABLE_CONTEXT_REQUIRED")
with psycopg.connect(host="127.0.0.1",dbname="phase3b2b1_test",user="postgres",password="phase3b2d2-synthetic-only",autocommit=True) as admin:
    admin.execute("CREATE DATABASE phase4a_runtime_test TEMPLATE phase3b2b1_test")
os.environ["POSTGRES_DB"]="phase4a_runtime_test"
sys.path.insert(0,"/app");os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings.development")
import django
django.setup()
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import Client,override_settings
from apps.inventory.models import AssetCategory,ProductModel
from apps.warehouse.models import Warehouse,StorageLocation
from apps.transactions.services import Line,Request,post
from uuid import uuid4
with connection.cursor() as c:
    c.execute("SELECT current_database(),current_user,current_setting('server_version_num')")
    assert c.fetchone()==("phase4a_runtime_test","postgres","170011")
user=get_user_model().objects.create_user(username="phase4-reader",password="synthetic-phase4-password")
user.user_permissions.add(*Permission.objects.filter(codename__startswith="view_"))
user.user_permissions.add(*Permission.objects.filter(content_type__app_label="transactions"))
category=AssetCategory.objects.create(code="P4",name="Synthetic category")
product=ProductModel.objects.create(sku_code="P4",name="Synthetic equipment",category=category,tracking_mode="SERIALIZED")
site=Warehouse.objects.create(code="P4",name="Synthetic warehouse")
location=StorageLocation.objects.create(code="P4",name="Synthetic area",warehouse=site,kind="AREA")
post(actor=user,request=Request(uuid4(),(Line("STOCK_IN",product_model_id=product.pk,
     destination_location_id=location.pk,device_name="Synthetic device"),),"Synthetic runtime fixture"))
tables=["auth_user","auth_group","auth_permission","auth_user_groups","auth_user_user_permissions","auth_group_permissions",
"django_content_type","django_session","inventory_asset","inventory_assetcategory","inventory_manufacturer","inventory_productmodel",
"inventory_stockbalance","inventory_stockthreshold","warehouse_warehouse","warehouse_storagelocation"]
with connection.cursor() as c:
    c.execute("CREATE ROLE itw_phase4a_runtime LOGIN PASSWORD 'phase4-runtime-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS")
    c.execute("REVOKE ALL ON DATABASE phase4a_runtime_test FROM PUBLIC")
    c.execute("GRANT CONNECT ON DATABASE phase4a_runtime_test TO itw_phase4a_runtime")
    c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    c.execute("GRANT USAGE ON SCHEMA public TO itw_phase4a_runtime")
    for name in tables:c.execute("GRANT SELECT ON public."+name+" TO itw_phase4a_runtime")
    c.execute("GRANT UPDATE (password,last_login) ON auth_user TO itw_phase4a_runtime")
    c.execute("GRANT INSERT,UPDATE,DELETE ON django_session TO itw_phase4a_runtime")
    c.execute("GRANT SELECT (id,operation_type,quantity,recorded_at) ON transactions_stockmovement TO itw_phase4a_runtime")
connection.close();connection.settings_dict.update(USER="itw_phase4a_runtime",PASSWORD="phase4-runtime-only")
def sql_connection():
    return psycopg.connect(host="127.0.0.1",dbname="phase4a_runtime_test",user="itw_phase4a_runtime",password="phase4-runtime-only",autocommit=True)
class RuntimeApiTests(unittest.TestCase):
    def test_01_effective_identity_and_no_privileged_flags_or_memberships(self):
        with connection.cursor() as c:
            c.execute("SELECT session_user,current_user");self.assertEqual(c.fetchone(),("itw_phase4a_runtime","itw_phase4a_runtime"))
        with sql_connection() as c:
            self.assertEqual(c.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone(),(False,)*5)
            self.assertEqual(c.execute("SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)").fetchone()[0],0)

    def test_02_real_csrf_login_and_all_reads_and_logout(self):
        with override_settings(ALLOWED_HOSTS=["testserver"]):
            client=Client(enforce_csrf_checks=True)
            token=client.get("/api/auth/csrf/").json()["csrfToken"]
            self.assertEqual(client.post("/api/auth/login/",{"username":"phase4-reader","password":"synthetic-phase4-password"},
                content_type="application/json",HTTP_X_CSRFTOKEN=token).status_code,200)
            for path in ["auth/me","dashboard/summary","inventory/assets","inventory/categories","inventory/manufacturers","inventory/product-models","warehouses","locations"]:
                self.assertEqual(client.get("/api/"+path+"/").status_code,200,path)
            token=client.get("/api/auth/csrf/").json()["csrfToken"]
            self.assertEqual(client.post("/api/auth/logout/",HTTP_X_CSRFTOKEN=token).status_code,200)

    def test_03_direct_review_evidence_select_and_dml_are_denied(self):
        with sql_connection() as c:
            for q in ["SELECT * FROM inventory_importreviewevent","SELECT * FROM inventory_importbatch",
                      "DELETE FROM inventory_importreviewevent","INSERT INTO inventory_importbatch DEFAULT VALUES"]:
                with self.subTest(q=q),self.assertRaises(psycopg.errors.InsufficientPrivilege):c.execute(q)

    def test_04_ddl_trigger_control_and_owner_assumption_are_denied(self):
        with sql_connection() as c:
            for q in ["CREATE TABLE public.p4_denied(id int)","CREATE TEMP TABLE p4_denied(id int)",
                      "ALTER TABLE transactions_stockmovement DISABLE TRIGGER USER",
                      "ALTER TABLE inventory_asset ADD COLUMN p4_denied int","SET ROLE postgres","TRUNCATE inventory_asset"]:
                with self.subTest(q=q),self.assertRaises(psycopg.errors.InsufficientPrivilege):c.execute(q)

    def test_05_stock_history_and_business_writes_denied(self):
        with sql_connection() as c:
            for q in ["UPDATE transactions_stockmovement SET quantity=2","DELETE FROM transactions_stockmovement",
                      "SELECT reason FROM transactions_stockmovement","UPDATE inventory_asset SET device_name='bad'",
                      "DELETE FROM warehouse_warehouse"]:
                with self.subTest(q=q),self.assertRaises(psycopg.errors.InsufficientPrivilege):c.execute(q)

    def test_06_permission_revocation_is_immediate(self):
        with override_settings(ALLOWED_HOSTS=["testserver"]):
            client=Client();client.force_login(user)
            self.assertEqual(client.get("/api/inventory/assets/").status_code,200)
            with psycopg.connect(host="127.0.0.1",dbname="phase4a_runtime_test",user="postgres",password="phase3b2d2-synthetic-only",autocommit=True) as admin:
                admin.execute("DELETE FROM auth_user_user_permissions WHERE user_id=%s AND permission_id IN (SELECT id FROM auth_permission WHERE codename='view_asset')",(user.pk,))
            self.assertEqual(client.get("/api/inventory/assets/").status_code,403)

result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeApiTests))
print("PHASE4_RUNTIME="+json.dumps(dict(ran=result.testsRun,failed=len(result.failures),errors=len(result.errors),skipped=len(result.skipped))))
sys.exit(not result.wasSuccessful())
