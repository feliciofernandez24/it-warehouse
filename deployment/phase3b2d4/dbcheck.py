"""Metadata-only inspector; apply requires both an explicit opt-in and matching cluster ID."""
import argparse, hashlib, json, os, sys
sys.path.insert(0,"/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings.development")
import django
django.setup()
from django.db import connection,transaction
from django.db.migrations.executor import MigrationExecutor
from django.core.management import call_command
from contextlib import redirect_stdout
from io import StringIO

APPROVED=[["inventory","0002_import_review_schema"],["inventory","0003_import_review_guards"]]
NEW=["inventory_importsourceprofile","inventory_importpreparationrevision","inventory_importrevisionparticipant",
     "inventory_importpreviewsnapshot","inventory_importreviewevent"]
def h(text): return hashlib.sha256(text.encode()).hexdigest()
def rows(c,q,p=None):
    c.execute(q,p); return c.fetchall()
def one(c,q,p=None): return rows(c,q,p)[0][0]

def snapshot():
    with transaction.atomic(), connection.cursor() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        c.execute("SET LOCAL statement_timeout='30s'")
        identity=rows(c,"SELECT current_database(),session_user,current_user,current_setting('server_version_num')::int,"
            "(SELECT system_identifier::text FROM pg_control_system()),pg_database_size(current_database())")[0]
        if identity[0]!=os.environ["POSTGRES_DB"] or identity[1:3]!=("it_warehouse","it_warehouse") or identity[3]!=170011:
            raise RuntimeError("DATABASE_IDENTITY_MISMATCH")
        tables={}; sequences={}
        for table,owner,acl in rows(c,"SELECT relname,pg_get_userbyid(relowner),relacl::text FROM pg_class "
                                      "WHERE relnamespace='public'::regnamespace AND relkind='r' ORDER BY relname"):
            pk=rows(c,"SELECT a.attname FROM pg_constraint p CROSS JOIN LATERAL unnest(p.conkey) k "
                "JOIN pg_attribute a ON a.attrelid=p.conrelid AND a.attnum=k WHERE p.conrelid=%s::regclass AND p.contype='p'",(table,))
            if len(pk)!=1: raise RuntimeError("UNSUPPORTED_PRIMARY_KEY")
            ident=lambda s:'"'+s.replace('"','""')+'"'
            # Only one-way key hashes and one-way row hashes leave PostgreSQL. No raw records/tokens.
            digests=dict(rows(c,"SELECT encode(sha256(convert_to("+ident(pk[0][0])+"::text,'UTF8')),'hex'),"
                "encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') FROM public."+ident(table)+" t"))
            tables[table]={"owner":owner,"acl":acl,"rows":digests,"count":len(digests)}
        for seq,owner,acl in rows(c,"SELECT relname,pg_get_userbyid(relowner),relacl::text FROM pg_class "
                                     "WHERE relnamespace='public'::regnamespace AND relkind='S' ORDER BY relname"):
            val=rows(c,'SELECT last_value,is_called FROM public."'+seq.replace('"','""')+'"')[0]
            sequences[seq]=[owner,acl,*val]
        funcs=rows(c,"SELECT proname,pg_get_userbyid(proowner),prosecdef,proacl::text,"
            "encode(sha256(convert_to(pg_get_functiondef(oid),'UTF8')),'hex') FROM pg_proc "
            "WHERE pronamespace='public'::regnamespace ORDER BY proname")
        triggers=rows(c,"SELECT r.relname,t.tgname,t.tgenabled,t.tgdeferrable,t.tginitdeferred,"
            "pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class r ON r.oid=t.tgrelid "
            "WHERE r.relnamespace='public'::regnamespace AND NOT t.tgisinternal ORDER BY r.relname,t.tgname")
        constraints=rows(c,"SELECT r.relname,p.conname,p.contype,p.convalidated,pg_get_constraintdef(p.oid) "
            "FROM pg_constraint p JOIN pg_class r ON r.oid=p.conrelid "
            "WHERE r.relname=ANY(%s) ORDER BY r.relname,p.conname",(NEW,))
        partials=rows(c,"SELECT i.indexrelid::regclass::text,i.indisvalid,pg_get_expr(i.indpred,i.indrelid) "
            "FROM pg_index i JOIN pg_class r ON r.oid=i.indrelid WHERE r.relname=ANY(%s) AND i.indpred IS NOT NULL ORDER BY 1",(NEW,))
        roles=rows(c,"SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolbypassrls,rolreplication,rolcanlogin,rolconnlimit "
            "FROM pg_roles WHERE rolname !~ '^pg_' ORDER BY rolname")
        members=rows(c,"SELECT pg_get_userbyid(roleid),pg_get_userbyid(member),admin_option,inherit_option,set_option "
            "FROM pg_auth_members WHERE pg_get_userbyid(member) !~ '^pg_' ORDER BY 1,2")
        sessions=rows(c,"SELECT pid,usename,application_name,client_addr::text,state,xact_start IS NOT NULL "
            "FROM pg_stat_activity WHERE datname=current_database() AND backend_type='client backend' AND pid<>pg_backend_pid()")
        meta={"database":rows(c,"SELECT pg_get_userbyid(datdba),datacl::text FROM pg_database WHERE datname=current_database()"),
            "schemas":rows(c,"SELECT nspname,pg_get_userbyid(nspowner),nspacl::text FROM pg_namespace WHERE nspname='public'"),
            "default_acls":rows(c,"SELECT defaclrole::regrole::text,defaclnamespace::regnamespace::text,defaclobjtype,defaclacl::text FROM pg_default_acl ORDER BY 1,2,3"),
            "extensions":rows(c,"SELECT extname,extversion,pg_get_userbyid(extowner) FROM pg_extension ORDER BY extname"),
            "role_setting_count":one(c,"SELECT count(*) FROM pg_db_role_setting")}
        result={"identity":identity,"tables":tables,"sequences":sequences,"functions":funcs,"triggers":triggers,
            "constraints":constraints,"partial_indexes":partials,"roles":roles,"members":members,
            "sessions":sessions,"metadata":meta,
            "history":rows(c,"SELECT app,name FROM django_migrations ORDER BY app,name")}
        return json.loads(json.dumps(result,default=str))

def plan():
    with transaction.atomic(),connection.cursor() as c:
        c.execute("SET TRANSACTION READ ONLY")
        executor=MigrationExecutor(connection)
        target=[("inventory","0003_import_review_guards")]
        result=[[m.app_label,m.name] for m,backwards in executor.migration_plan(target) if not backwards]
        total=[[m.app_label,m.name] for m,b in executor.migration_plan(executor.loader.graph.leaf_nodes()) if not b]
        if result!=APPROVED or total!=APPROVED: raise RuntimeError("UNAPPROVED_MIGRATION_PLAN")
        return result

def precheck(s):
    inv=[n for a,n in s["history"] if a=="inventory"]
    tx=[n for a,n in s["history"] if a=="transactions"]
    if inv!=["0001_initial"] or tx!=["0001_initial","0002_schema_guards","0003_stockoperation","0004_posting_guards","0005_serialized_reclassification"]:
        raise RuntimeError("UNEXPECTED_HISTORY")
    if any(t in s["tables"] for t in NEW) or any(f[0].startswith("itw_review_") for f in s["functions"]):
        raise RuntimeError("PREEXISTING_REVIEW_OBJECTS")
    if any(t["owner"]!="it_warehouse" for t in s["tables"].values()): raise RuntimeError("UNEXPECTED_OWNER")
    if s["sessions"]: raise RuntimeError("OTHER_DATABASE_SESSIONS")
    if s["metadata"]["extensions"]!=[("plpgsql","1.0","it_warehouse")]:
        # JSON-loaded comparison handled by callers; source snapshot uses tuples.
        if list(map(list,s["metadata"]["extensions"]))!=[["plpgsql","1.0","it_warehouse"]]:
            raise RuntimeError("EXTENSION_DEPENDENCY_REVIEW_REQUIRED")

def compare(before,after,post=False):
    expected=set(before["tables"]) | (set(NEW) if post else set())
    if set(after["tables"])!=expected: raise RuntimeError("UNEXPECTED_TABLE_SET")
    controlled={"auth_permission":5,"django_content_type":5,"django_migrations":2} if post else {}
    for name,old in before["tables"].items():
        cur=after["tables"][name]
        if cur["owner"]!=old["owner"] or cur["acl"]!=old["acl"]: raise RuntimeError("SOURCE_ACL_CHANGED")
        if any(cur["rows"].get(k)!=v for k,v in old["rows"].items()): raise RuntimeError("ORIGINAL_ROW_CHANGED")
        if cur["count"]!=old["count"]+controlled.get(name,0): raise RuntimeError("ROW_COUNT_CHANGED")
    if after["metadata"]!=before["metadata"]: raise RuntimeError("DATABASE_METADATA_CHANGED")
    # Source roles must be reproduced exactly. A separate restore administrator is allowed on a disposable cluster.
    if (any(role not in after["roles"] for role in before["roles"]) or before["members"]!=after["members"]
        or any(role not in before["roles"] and role[0]!="restore_admin" for role in after["roles"])):
        raise RuntimeError("ROLE_METADATA_CHANGED")
    for seq,old in before["sequences"].items():
        if post and seq in ("auth_permission_id_seq","django_content_type_id_seq","django_migrations_id_seq"): continue
        if after["sequences"][seq]!=old: raise RuntimeError("SOURCE_SEQUENCE_CHANGED")
    oldf=[f for f in before["functions"] if not f[0].startswith("itw_review_")]
    newf=[f for f in after["functions"] if not f[0].startswith("itw_review_")]
    oldt=[t for t in before["triggers"] if not t[1].startswith("review_")]
    newt=[t for t in after["triggers"] if not t[1].startswith("review_")]
    if oldf!=newf or oldt!=newt: raise RuntimeError("STOCK_GUARDS_CHANGED")
    if not post:
        if after["history"]!=before["history"]: raise RuntimeError("RESTORE_HISTORY_MISMATCH")
        return
    for table in NEW:
        if after["tables"][table]["owner"]!="it_warehouse" or after["tables"][table]["acl"] is not None: raise RuntimeError("NEW_TABLE_ACL_MISMATCH")
        if after["tables"][table]["count"]!=0: raise RuntimeError("REVIEW_NOT_EMPTY")
    if len(after["constraints"])!=63 or not all(x[3] for x in after["constraints"]): raise RuntimeError("CONSTRAINT_MISMATCH")
    review=[x for x in after["functions"] if x[0].startswith("itw_review_")]
    triggers=[x for x in after["triggers"] if x[1].startswith("review_")]
    if len(review)!=11 or any(x[1]!="it_warehouse" or x[2] or x[3]!='{it_warehouse=X/it_warehouse}' for x in review):
        raise RuntimeError("FUNCTION_OWNER_OR_ACL_MISMATCH")
    if len(triggers)!=18 or any(x[2]!="O" for x in triggers) or sum(x[3] and x[4] for x in triggers)!=4:
        raise RuntimeError("TRIGGER_MISMATCH")
    if len(after["partial_indexes"])!=2 or not all(x[1] for x in after["partial_indexes"]):
        raise RuntimeError("PARTIAL_INDEX_MISMATCH")
    if [n for a,n in after["history"] if a=="inventory"]!=["0001_initial",*map(lambda x:x[1],APPROVED)]:
        raise RuntimeError("POST_HISTORY_MISMATCH")


def read_smokes():
    from django.conf import settings
    from django.test import Client,override_settings
    from django.urls import get_resolver
    if [str(p.pattern) for p in get_resolver().url_patterns]!=["admin/","api/health/"]:
        raise RuntimeError("UNREVIEWED_ENDPOINT")
    with override_settings(ALLOWED_HOSTS=["testserver"]):
        client=Client()
        if client.get("/api/health/").status_code!=200 or client.get("/admin/").status_code!=302:
            raise RuntimeError("READ_ONLY_APPLICATION_SMOKE_FAILED")
    with connection.cursor() as c:
        c.execute("SELECT count(*) FROM pg_namespace WHERE nspname IN ('itw_read_poc','fa_owner','itw_capture')")
        if c.fetchone()[0]:raise RuntimeError("UNAPPROVED_GATEWAY_SCHEMA")
    from apps.inventory.review import services
    from apps.inventory.review.errors import ReviewServiceError
    for action in (services.approve_revision,services.revoke_approval,services.promote_import):
        try:action()
        except ReviewServiceError as e:
            if e.code!="ACTION_DISABLED":raise RuntimeError("RESERVED_ACTION_CHANGED")
        else:raise RuntimeError("RESERVED_ACTION_ENABLED")

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["snapshot","plan","apply","verify"])
    p.add_argument("--before");args=p.parse_args()
    try:
        if args.action=="snapshot": result=snapshot()
        elif args.action=="plan":
            precheck(snapshot());result=plan()
        else:
            before=json.load(open(args.before));current=snapshot()
            if args.action=="apply":
                if os.environ.get("ITW_D4_EXECUTE")!="AUTHORIZE_INVENTORY_0002_0003": raise RuntimeError("OPT_IN_REQUIRED")
                if current["identity"][4]!=os.environ.get("ITW_D4_CLUSTER"): raise RuntimeError("CLUSTER_MISMATCH")
                precheck(current);compare(before,current)
                approved=plan()
                with redirect_stdout(StringIO()):
                    call_command("migrate","inventory","0002",interactive=False,verbosity=0)
                    call_command("migrate","inventory","0003",interactive=False,verbosity=0)
                result=snapshot();compare(before,result,post=True)
            else:
                compare(before,current,post=True);read_smokes();result=current
        print(json.dumps(result,default=str,sort_keys=True))
    except Exception as error:
        # Do not expose driver diagnostics, row values or credentials.
        print(json.dumps({"error":str(error) if isinstance(error,RuntimeError) else type(error).__name__}),file=sys.stderr)
        sys.exit(1)