"""Standalone restored-backup rehearsal. Does not provision development credentials."""
import argparse
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from harness import prepare,django_setup,gateway_setup,EVIDENCE,admin

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=["pre","post","gateway"])
    args=parser.parse_args()
    prepare()
    django_setup()
    from tests import RuntimeTests,ReviewTests,GatewayTests
    suite=unittest.TestSuite()
    if args.stage=="gateway":
        GatewayTests.target=gateway_setup()
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(GatewayTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeTests))
    if args.stage!="pre":
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(ReviewTests))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    EVIDENCE["stage"]=args.stage
    EVIDENCE["tests"]={"ran":result.testsRun,"failed":len(result.failures),"errors":len(result.errors),
        "skipped":len(result.skipped)}
    from django.db import connections
    connections.close_all()
    with admin() as c:
        EVIDENCE["table_grants"]=c.execute("SELECT table_name,privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee='itw_django_rehearsal' ORDER BY table_name,privilege_type").fetchall()
        EVIDENCE["update_column_grants"]=c.execute("SELECT table_name,column_name FROM information_schema.role_column_grants "
            "WHERE grantee='itw_django_rehearsal' AND privilege_type='UPDATE' ORDER BY table_name,column_name").fetchall()
        EVIDENCE["role_flags"]=c.execute("SELECT rolname,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolbypassrls "
            "FROM pg_roles WHERE rolname IN ('itw_django_rehearsal','itw_rehearsal_migrator','it_warehouse') ORDER BY rolname").fetchall()
        EVIDENCE["role_memberships"]=c.execute("SELECT pg_get_userbyid(roleid),pg_get_userbyid(member) "
            "FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname='itw_django_rehearsal')").fetchall()
    Path("/tmp/runtime-rehearsal-"+args.stage+".json").write_text(json.dumps(EVIDENCE,indent=2,default=str)+"\n")
    print("REHEARSAL_RESULT="+json.dumps(EVIDENCE["tests"]))
    sys.exit(0 if result.wasSuccessful() else 1)