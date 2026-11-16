"""Eight existing application smokes under the actual shared-superuser model; disposable only."""
import importlib.util,json,os,sys,unittest
from pathlib import Path
if os.environ.get("ITW_D4_OWNER_SMOKES")!="DISPOSABLE_ONLY" or os.environ.get("POSTGRES_HOST")!="127.0.0.1" or os.environ.get("POSTGRES_DB")!="it_warehouse":
    raise RuntimeError("EXPLICIT_DISPOSABLE_CONTEXT_REQUIRED")
sys.path.insert(0,"/app");os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings.development")
import django;django.setup()
from django.db import connections,connection
import psycopg
sys.path.insert(0,"/app/feasibility_runtime");import harness
def admin():return psycopg.connect(host="127.0.0.1",dbname="it_warehouse",user="it_warehouse",password="d4-disposable-only",autocommit=True)
harness.admin=admin
connections.databases["owner"]=dict(connections["default"].settings_dict)
spec=importlib.util.spec_from_file_location("existing_owner_smokes","/app/feasibility_runtime/tests.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with connection.cursor() as c:
    c.execute("SELECT system_identifier::text FROM pg_control_system()")
    cluster=c.fetchone()[0]
    if cluster=="7706069425466331170" or cluster!=os.environ.get("ITW_D4_EXPECT_CLUSTER"):raise RuntimeError("DISPOSABLE_CLUSTER_ID_REQUIRED")
    c.execute("SELECT session_user,current_user,rolsuper FROM pg_roles WHERE rolname=current_user")
    assert c.fetchone()==("it_warehouse","it_warehouse",True)
methods=["test_02_django_login_session_update_logout_and_admin_index","test_03_bulk_receive_issue_transfer_return_and_replay",
    "test_04_serialized_receive_issue_and_return","test_05_unauthorized_actor_is_denied_even_under_valid_sql_login",
    "test_06_direct_balance_change_hits_conservation_guard","test_07_orphan_movement_hits_operation_guard",
    "test_09_posted_operation_is_immutable","test_12_audit_start_count_and_freeze_guard"]
result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(module.RuntimeTests(n) for n in methods))
print("OWNER_SMOKES="+json.dumps(dict(ran=result.testsRun,failed=len(result.failures),errors=len(result.errors),skipped=len(result.skipped))))
sys.exit(not result.wasSuccessful())
