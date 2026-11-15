"""Disposable restore/migration readiness proof. No persistent deployment path."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import psycopg
from psycopg import sql

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
if (os.environ.get("ITW_SCHEMA_REHEARSAL")!="1"
    or os.environ.get("POSTGRES_DB")!="itw_runtime_rehearsal"
    or os.environ.get("POSTGRES_HOST")!="127.0.0.1"
    or os.environ.get("POSTGRES_USER")!="it_warehouse"
    or os.environ.get("POSTGRES_PASSWORD")!="owner-rehearsal-only"):
    raise RuntimeError("DISPOSABLE_OWNER_REHEARSAL_REQUIRED")

def admin():
    c=psycopg.connect(dbname="itw_runtime_rehearsal",host="127.0.0.1",user="postgres",
        password="runtime-rehearsal-admin-only",autocommit=True)
    if c.info.server_version!=170011:
        raise RuntimeError("POSTGRESQL_17_11_REQUIRED")
    c.execute("SET TIME ZONE 'UTC'")
    return c

def snapshot():
    result={}
    with admin() as c:
        for table, in c.execute("SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace "
                               "AND relkind='r' ORDER BY relname").fetchall():
            pk=c.execute("SELECT a.attname FROM pg_constraint p "
                "CROSS JOIN LATERAL unnest(p.conkey) k "
                "JOIN pg_attribute a ON a.attrelid=p.conrelid AND a.attnum=k "
                "WHERE p.conrelid=%s::regclass AND p.contype='p'",("public."+table,)).fetchall()
            if len(pk)!=1:
                raise RuntimeError("SINGLE_PRIMARY_KEY_REQUIRED")
            result[table]=dict(c.execute(sql.SQL("SELECT {}::text,encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') "
                "FROM public.{} t").format(sql.Identifier(pk[0][0]),sql.Identifier(table))).fetchall())
    return result

def summary(snap):
    return {t:{"rows":len(rows),"sha256":hashlib.sha256(json.dumps(rows,sort_keys=True,
        separators=(",",":")).encode()).hexdigest()} for t,rows in snap.items()}

def stock_guards(c):
    return {"functions":c.execute("SELECT proname,md5(pg_get_functiondef(oid)) "
        "FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname LIKE 'itw_%' "
        "AND proname NOT LIKE 'itw_review_%' ORDER BY proname").fetchall(),
        "triggers":c.execute("SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid),t.tgenabled "
        "FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
        "WHERE c.relnamespace='public'::regnamespace AND NOT t.tgisinternal "
        "AND t.tgname NOT LIKE 'review_%' ORDER BY c.relname,t.tgname").fetchall()}

BEFORE=snapshot()
with admin() as c:
    HISTORY=c.execute("SELECT app,name FROM django_migrations WHERE app IN ('inventory','transactions') ORDER BY app,name").fetchall()
    STOCK=stock_guards(c)
assert [n for a,n in HISTORY if a=="inventory"]==["0001_initial"]
assert [n for a,n in HISTORY if a=="transactions"]==["0001_initial","0002_schema_guards","0003_stockoperation",
    "0004_posting_guards","0005_serialized_reclassification"]

migration_env=dict(os.environ,POSTGRES_USER="itw_rehearsal_migrator",
    POSTGRES_PASSWORD="migration-rehearsal-only",PGOPTIONS="-crole=it_warehouse")
subprocess.run([sys.executable,"manage.py","migrate","inventory","0003","--noinput"],env=migration_env,check=True)
AFTER=snapshot()
with admin() as c:
    assert stock_guards(c)==STOCK
ORIGINAL_PRESERVED=all(all(AFTER[t].get(k)==v for k,v in rows.items()) for t,rows in BEFORE.items())
CONTROLLED={"auth_permission","django_content_type","django_migrations"}
assert ORIGINAL_PRESERVED
assert all(AFTER[t]==rows for t,rows in BEFORE.items() if t not in CONTROLLED)

os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings.development")
import django
django.setup()
from django.db import connection,connections,transaction,DatabaseError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from apps.inventory import test_review_schema as fixtures
from apps.inventory.models import (ImportSourceProfile,ImportPreparationRevision,ImportRevisionParticipant,
    ImportPreviewSnapshot,ImportReviewEvent)
from apps.inventory.review import services
from apps.inventory.review.errors import ReviewServiceError

new_models=[ImportSourceProfile,ImportPreparationRevision,ImportRevisionParticipant,ImportPreviewSnapshot,ImportReviewEvent]
NEW_TABLES=[m._meta.db_table for m in new_models]
EVIDENCE={"pre_history":HISTORY,"pre_tables":summary(BEFORE),"post_tables":summary(AFTER),
    "original_rows_preserved":ORIGINAL_PRESERVED,"stock_guard_definitions_unchanged":True}
with admin() as c:
    EVIDENCE["post_history"]=c.execute("SELECT app,name FROM django_migrations WHERE app IN ('inventory','transactions') ORDER BY app,name").fetchall()
    EVIDENCE["constraints"]=c.execute("SELECT c.relname,p.contype,count(*),bool_and(p.convalidated) FROM pg_constraint p "
        "JOIN pg_class c ON c.oid=p.conrelid WHERE c.relname=ANY(%s) GROUP BY c.relname,p.contype ORDER BY c.relname,p.contype",(NEW_TABLES,)).fetchall()
    EVIDENCE["review_functions"]=c.execute("SELECT proname,pg_get_userbyid(proowner),prosecdef,proacl::text "
        "FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname LIKE 'itw_review_%' ORDER BY proname").fetchall()
    EVIDENCE["review_triggers"]=c.execute("SELECT c.relname,t.tgname,t.tgenabled,t.tgdeferrable,t.tginitdeferred "
        "FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid WHERE t.tgname LIKE 'review_%' ORDER BY c.relname,t.tgname").fetchall()

class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.atomic=transaction.atomic(); self.atomic.__enter__()
    def tearDown(self):
        transaction.set_rollback(True); self.atomic.__exit__(None,None,None)

    def test_01_existing_rows_preserved_and_history_order(self):
        self.assertTrue(ORIGINAL_PRESERVED)
        self.assertEqual([n for a,n in EVIDENCE["post_history"] if a=="inventory"],
            ["0001_initial","0002_import_review_schema","0003_import_review_guards"])

    def test_02_five_empty_tables_constraints_and_guard_catalog(self):
        with admin() as c:
            for model in new_models:
                table=model._meta.db_table
                self.assertEqual(len(AFTER[table]),0)
                actual={x[0] for x in c.execute("SELECT conname FROM pg_constraint WHERE conrelid=%s::regclass",(table,))}
                actual|={x[0] for x in c.execute("SELECT indexrelid::regclass::text FROM pg_index WHERE indrelid=%s::regclass AND indisvalid",(table,))}
                self.assertTrue({x.name for x in model._meta.constraints}.issubset(actual),table)
            self.assertTrue(all(row[3] for row in EVIDENCE["constraints"]))
            self.assertEqual(len(EVIDENCE["review_functions"]),11)
            self.assertEqual(len(EVIDENCE["review_triggers"]),18)
            self.assertTrue(all(row[2]=="O" for row in EVIDENCE["review_triggers"]))
            self.assertEqual(sum(row[3] and row[4] for row in EVIDENCE["review_triggers"]),4)

    def test_03_owner_consistency_without_operational_gateway(self):
        with connection.cursor() as c:
            c.execute("SELECT session_user,current_user")
            self.assertEqual(c.fetchone(),("it_warehouse","it_warehouse"))
            c.execute("SELECT count(*) FROM pg_class WHERE relname=ANY(%s) AND pg_get_userbyid(relowner)<>'it_warehouse'",(NEW_TABLES,))
            self.assertEqual(c.fetchone()[0],0)
            c.execute("SELECT count(*) FROM pg_namespace WHERE nspname IN ('itw_read_poc','fa_owner','itw_capture')")
            self.assertEqual(c.fetchone()[0],0)
        self.assertTrue(all(not row[2] and row[1]=="it_warehouse" for row in EVIDENCE["review_functions"]))

    def test_04_services_remain_hard_disabled(self):
        user=get_user_model().objects.create(username="schema-synthetic-user")
        user.user_permissions.add(Permission.objects.get(content_type__app_label="inventory",
            content_type__model="importbatch",codename="capture_import"))
        with self.assertRaises(ReviewServiceError) as failure:
            services.register_verified_capture(actor=user,request_id=__import__("uuid").uuid4(),payload={})
        self.assertEqual(failure.exception.code,"GATEWAY_UNAVAILABLE")
        for call in (services.approve_revision,services.revoke_approval,services.promote_import):
            with self.subTest(call=call.__name__),self.assertRaisesRegex(ReviewServiceError,"ACTION_DISABLED"):
                call()
        for model in new_models:
            self.assertEqual(model.objects.count(),0)

    def fixture(self):
        fixtures.ReviewSchemaTests.setUpTestData.__func__(fixtures.ReviewSchemaTests)
        return fixtures.ReviewSchemaTests()

    def test_05_approval_revocation_promotion_states_denied_for_owner(self):
        f=self.fixture(); r,_=f.captured()
        for state in ("APPROVED","REVOKED","PROMOTED"):
            with self.subTest(state=state),self.assertRaisesRegex(DatabaseError,"REVIEW_APPROVAL_DISABLED"):
                with transaction.atomic():
                    ImportPreparationRevision.objects.filter(pk=r.pk).update(state=state,version=r.version+1)

    def test_06_approval_and_revocation_events_denied_for_owner(self):
        f=self.fixture(); r,_=f.captured()
        for kind in ("APPROVE","REVOKE"):
            with self.subTest(kind=kind),self.assertRaisesRegex(DatabaseError,"REVIEW_APPROVAL_DISABLED"):
                with transaction.atomic():
                    f.event(r,kind,"CAPTURED")

    def test_07_owner_has_ddl_and_trigger_control_not_runtime_isolation(self):
        with connection.cursor() as c:
            c.execute("ALTER TABLE inventory_importreviewevent ADD COLUMN schema_rehearsal_only integer")
            c.execute("ALTER TABLE transactions_stockmovement DISABLE TRIGGER USER")
            c.execute("SELECT has_table_privilege(current_user,'inventory_importreviewevent','TRUNCATE')")
            self.assertTrue(c.fetchone()[0])
        # Both DDL operations roll back in tearDown; no ledger change is made.
        EVIDENCE["ordinary_owner_can_alter_and_disable_user_triggers"]=True

    def test_08_stock_guard_definitions_remain_exact(self):
        with admin() as c:
            self.assertEqual(stock_guards(c),STOCK)

schema_result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SchemaTests))
# Reuse eight unmodified existing Django/stock/audit tests under the actual OWNER LOGIN.
owner=dict(connections["default"].settings_dict,USER="itw_rehearsal_migrator",PASSWORD="migration-rehearsal-only",
    OPTIONS={"options":"-crole=it_warehouse"})
connections.databases["owner"]=owner
sys.path.insert(0,str(ROOT/"feasibility_runtime"))
spec=importlib.util.spec_from_file_location("schema_existing_runtime",ROOT/"feasibility_runtime"/"tests.py")
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
methods=["test_02_django_login_session_update_logout_and_admin_index",
    "test_03_bulk_receive_issue_transfer_return_and_replay","test_04_serialized_receive_issue_and_return",
    "test_05_unauthorized_actor_is_denied_even_under_valid_sql_login","test_06_direct_balance_change_hits_conservation_guard",
    "test_07_orphan_movement_hits_operation_guard","test_09_posted_operation_is_immutable",
    "test_12_audit_start_count_and_freeze_guard"]
owner_result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(module.RuntimeTests(name) for name in methods))
FINAL=snapshot()
assert all(all(FINAL[t].get(k)==v for k,v in rows.items()) for t,rows in BEFORE.items())
with admin() as c:
    assert stock_guards(c)==STOCK
    assert c.execute("SELECT count(*) FROM information_schema.columns WHERE column_name='schema_rehearsal_only'").fetchone()[0]==0
EVIDENCE["original_rows_preserved_after_smokes"]=True
for name,result in (("schema_tests",schema_result),("owner_smoke_tests",owner_result)):
    EVIDENCE[name]={"ran":result.testsRun,"failed":len(result.failures),"errors":len(result.errors),"skipped":len(result.skipped)}
Path("/tmp/phase3b2d3-schema-evidence.json").write_text(json.dumps(EVIDENCE,indent=2,default=str)+"\n")
print("SCHEMA_RESULTS="+json.dumps({k:EVIDENCE[k] for k in ("schema_tests","owner_smoke_tests")}))
connections.close_all()
sys.exit(0 if schema_result.wasSuccessful() and owner_result.wasSuccessful() else 1)