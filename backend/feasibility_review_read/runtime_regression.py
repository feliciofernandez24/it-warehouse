"""Run the PRE-EXISTING runtime tests on a SYNTHETIC clone, never a restored/live database."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
import psycopg
from psycopg import sql

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
if (os.environ.get("ITW_REVIEW_READ_PROOF")!="1" or os.environ.get("POSTGRES_DB")!="phase3b2b1_test"
    or os.environ.get("POSTGRES_HOST")!="127.0.0.1"
    or os.environ.get("POSTGRES_PASSWORD")!="phase3b2d2-synthetic-only"):
    raise RuntimeError("SYNTHETIC_ISOLATED_DATABASE_REQUIRED")
if "--existing-clone" not in sys.argv:
    common=dict(host="127.0.0.1",user="postgres",password="phase3b2d2-synthetic-only",autocommit=True)
    with psycopg.connect(dbname="phase3b2b1_test",**common) as c:
        if c.info.server_version//10000!=17:
            raise RuntimeError("POSTGRESQL_17_REQUIRED")
        c.execute("CREATE ROLE it_warehouse NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS")
        c.execute("CREATE ROLE itw_rehearsal_migrator LOGIN PASSWORD 'migration-rehearsal-only' "
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS")
        c.execute("GRANT it_warehouse TO itw_rehearsal_migrator")
        c.execute("CREATE DATABASE itw_runtime_rehearsal TEMPLATE phase3b2b1_test OWNER it_warehouse")
    with psycopg.connect(dbname="itw_runtime_rehearsal",**common) as c:
        # Explicit public relation/function catalog lists in this fresh synthetic clone only.
        with c.transaction():
            for name, in c.execute("SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace "
                    "AND relkind='r' ORDER BY relname").fetchall():
                c.execute(sql.SQL("ALTER TABLE public.{} OWNER TO it_warehouse").format(sql.Identifier(name)))
            for fn, in c.execute("SELECT oid::regprocedure::text FROM pg_proc "
                    "WHERE pronamespace='public'::regnamespace AND prokind='f' ORDER BY oid").fetchall():
                c.execute(sql.SQL("ALTER FUNCTION {} OWNER TO it_warehouse").format(sql.SQL(fn)))
        # Match the pre-existing rehearsal harness's synthetic admin credential, in this disposable cluster only.
        c.execute("ALTER ROLE postgres PASSWORD 'runtime-rehearsal-admin-only'")
os.environ.update(POSTGRES_DB="itw_runtime_rehearsal",POSTGRES_USER="itw_django_rehearsal",
    POSTGRES_PASSWORD="runtime-rehearsal-only",ITW_RUNTIME_REHEARSAL="1")
sys.path.insert(0,str(ROOT/"feasibility_runtime"))
import harness
harness.prepare()
harness.django_setup()
with harness.admin() as c:
    c.execute("GRANT USAGE ON SCHEMA itw_read_poc TO itw_django_rehearsal")
    c.execute("GRANT EXECUTE ON FUNCTION itw_read_poc.inspect_v1(text,uuid,uuid,bigint,text) TO itw_django_rehearsal")
spec=importlib.util.spec_from_file_location("existing_runtime_tests",ROOT/"feasibility_runtime"/"tests.py")
tests=importlib.util.module_from_spec(spec); spec.loader.exec_module(tests)
suite=unittest.TestSuite()
for cls in (tests.RuntimeTests,tests.ReviewTests):
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
result=unittest.TextTestRunner(verbosity=2).run(suite)
from django.db import connection,connections
with connection.cursor() as c:
    c.execute("SELECT session_user,current_user")
    identity=c.fetchone()
    assert identity==("itw_django_rehearsal","itw_django_rehearsal")
    c.execute("SELECT itw_read_poc.inspect_v1('record_review',gen_random_uuid(),gen_random_uuid(),1,repeat('a',64))")
    denial=c.fetchone()[0]
    if isinstance(denial,str):
        denial=json.loads(denial)
    assert denial=={"code":"IDENTITY_VERIFICATION_UNAVAILABLE","retryable":False}
connections.close_all()
evidence={"tests":{"ran":result.testsRun,"failed":len(result.failures),"errors":len(result.errors),
    "skipped":len(result.skipped)},"shared_runtime_identity":identity,"shared_runtime_denial":denial,
    "runtime_grants":harness.EVIDENCE["grants"],"restore_used":False}
Path("/tmp/phase3b2d2-runtime-evidence.json").write_text(json.dumps(evidence,indent=2,default=str)+"\n")
print("EXISTING_RUNTIME_RESULT="+json.dumps(evidence["tests"]))
sys.exit(0 if result.wasSuccessful() else 1)