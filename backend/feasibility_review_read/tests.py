"""Read-only gateway tests; synthetic fixtures and independent real DB LOGIN connections."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
import psycopg
from psycopg import sql
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission,Group
from django.db import connection,transaction
from apps.inventory import test_review_schema as fixtures
from apps.inventory.models import ImportRevisionParticipant,ImportReviewEvent,ImportPreviewSnapshot
from apps.inventory.staging.common import canonical
from adapter import inspect_metadata,GatewayError

PASSWORDS={}
EVIDENCE={}
DB="phase3b2b1_test"
OWNER="itw_read_poc_owner"
ROLES=["itw_read_editor","itw_read_reviewer","itw_read_uploader","itw_read_inactive",
       "itw_read_nogrant","itw_read_group","itw_read_shared"]
TABLES=["inventory_importbatch","inventory_importstagingrecord","inventory_importsourceprofile",
        "inventory_importpreparationrevision","inventory_importrevisionparticipant",
        "inventory_importpreviewsnapshot","inventory_importreviewevent"]

def connect(role="postgres"):
    if (os.environ.get("ITW_REVIEW_READ_PROOF")!="1" or os.environ.get("POSTGRES_DB")!=DB
        or os.environ.get("POSTGRES_HOST")!="127.0.0.1"
        or os.environ.get("POSTGRES_PASSWORD")!="phase3b2d2-synthetic-only"):
        raise RuntimeError("ISOLATED_DATABASE_REQUIRED")
    c=psycopg.connect(host="127.0.0.1",dbname=DB,user=role,
        password="phase3b2d2-synthetic-only" if role=="postgres" else PASSWORDS[role],autocommit=True)
    if c.info.server_version//10000!=17:
        c.close()
        raise RuntimeError("POSTGRESQL_17_REQUIRED")
    return c

def fp(actor,action,revision,version,payload):
    return hashlib.sha256(canonical({"domain":"itw.review-request.v1","actor_id":actor,
        "action":action,"revision_id":str(revision),"expected_version":version,
        "payload_sha256":hashlib.sha256(canonical(payload)).hexdigest()})).hexdigest()

def submit(f,r):
    with transaction.atomic():
        f.advance(r,"PREPARING","START")
        f.advance(r,"PREPARING","EDIT",payload=f.structural_payload(r))
        r.version+=1; r.state="READY_FOR_REVIEW"; r.save(update_fields=["version","state"])
        data=canonical(r.draft_payload)
        snapshot=ImportPreviewSnapshot.objects.create(revision=r,canonical_bytes=data,digest=hashlib.sha256(data).hexdigest())
        f.event(r,"SUBMIT","PREPARING",snapshot=snapshot)
        f.constraints()
    return snapshot

def wait_lock(c,pid):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        if c.execute("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=%s "
                "AND locktype='advisory' AND NOT granted)",(pid,)).fetchone()[0]:
            return
        time.sleep(.01)
    raise AssertionError("ADVISORY_WAITER_NOT_OBSERVED")

class ReadGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ReviewSchemaTests.setUpTestData.__func__(fixtures.ReviewSchemaTests)
        cls.f=fixtures.ReviewSchemaTests()
        f=cls.f
        cls.captured,_=f.captured()
        cls.ready,_,cls.snapshot=f.submitted()
        cls.other,_=f.captured()
        cls.contributing,_=f.captured()
        ImportRevisionParticipant.objects.create(revision=cls.contributing,user=f.editor)
        submit(f,cls.contributing)
        cls.group_user=get_user_model().objects.create(username="synthetic-group-reader")
        cls.group=Group.objects.create(name="synthetic-read-group")
        cls.permissions=list(Permission.objects.filter(content_type__app_label="inventory",
            content_type__model="importbatch",codename__in=["review_import","view_import_evidence"]))
        cls.group.permissions.add(*cls.permissions); cls.group_user.groups.add(cls.group)
        cls.history_request=uuid.uuid4()
        cls.history_version=cls.ready.version
        cls.history_payload={"note":"synthetic"}
        cls.history_fp=fp(f.reviewer.pk,"record_review",cls.ready.pk,cls.history_version,cls.history_payload)
        with transaction.atomic():
            cls.ready.version+=1; cls.ready.save(update_fields=["version"])
            with connection.cursor() as cur:
                cur.execute("SELECT encode(sha256(convert_to(draft_payload::text,'UTF8')),'hex') "
                    "FROM inventory_importpreparationrevision WHERE id=%s",(cls.ready.pk,))
                digest=cur.fetchone()[0]
            cls.history=ImportReviewEvent.objects.create(revision=cls.ready,sequence=cls.ready.version,
                request_id=cls.history_request,request_fingerprint=cls.history_fp,actor=f.reviewer,
                kind="REVIEW_ACCEPT",from_state="READY_FOR_REVIEW",to_state="READY_FOR_REVIEW",
                snapshot=cls.snapshot,reason_code="SYNTHETIC",reason="CONFIDENTIAL-SENTINEL",
                details={"after_payload_digest":digest,"secret":"CONFIDENTIAL-SENTINEL"})
            f.constraints()
        with connect() as c:
            with c.transaction():
                c.execute(Path(__file__).with_name("gateway.sql").read_text())
                c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
                c.execute("REVOKE ALL ON DATABASE phase3b2b1_test FROM PUBLIC")
                actors=[f.editor,f.reviewer,f.preparer,f.inactive,f.no_grants,cls.group_user,None]
                for role,actor in zip(ROLES,actors):
                    PASSWORDS[role]=secrets.token_urlsafe(24)
                    c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB "
                        "NOCREATEROLE NOINHERIT NOBYPASSRLS").format(sql.Identifier(role),sql.Literal(PASSWORDS[role])))
                    c.execute(sql.SQL("GRANT CONNECT ON DATABASE phase3b2b1_test TO {}").format(sql.Identifier(role)))
                    c.execute(sql.SQL("GRANT USAGE ON SCHEMA itw_read_poc TO {}").format(sql.Identifier(role)))
                    c.execute(sql.SQL("GRANT EXECUTE ON FUNCTION itw_read_poc.inspect_v1(text,uuid,uuid,bigint,text) TO {}").format(sql.Identifier(role)))
                    if actor:
                        c.execute("INSERT INTO itw_read_poc.principal VALUES(%s,%s,true)",(role,actor.pk))
                        for revision in (cls.captured,cls.ready,cls.contributing):
                            c.execute("INSERT INTO itw_read_poc.batch_scope VALUES(%s,%s) ON CONFLICT DO NOTHING",
                                (actor.pk,revision.batch_id))
            EVIDENCE["owners"]=c.execute("SELECT relname,pg_get_userbyid(relowner) FROM pg_class "
                "WHERE relnamespace='public'::regnamespace AND relname LIKE 'inventory_import%' "
                "AND relkind IN ('r','S') ORDER BY relname").fetchall()
            EVIDENCE["function"]=c.execute("SELECT pg_get_userbyid(proowner),prosecdef,proconfig,proacl::text "
                "FROM pg_proc WHERE oid='itw_read_poc.inspect_v1(text,uuid,uuid,bigint,text)'::regprocedure").fetchone()
            EVIDENCE["owner_column_grants"]=c.execute("SELECT table_name,column_name FROM "
                "information_schema.role_column_grants WHERE grantee=%s AND privilege_type='SELECT' "
                "ORDER BY table_name,column_name",(OWNER,)).fetchall()
            EVIDENCE["roles"]=c.execute("SELECT rolname,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolbypassrls "
                "FROM pg_roles WHERE rolname LIKE 'itw_read_%' ORDER BY rolname").fetchall()
        cls.before=cls.protected_counts()

    @classmethod
    def protected_counts(cls):
        with connect() as c:
            return {t:c.execute(sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(t))).fetchone()[0] for t in TABLES}

    def call(self,role="itw_read_reviewer",action="record_review",revision=None,version=None,request=None,payload=None):
        revision=revision or self.ready
        with connect(role) as c:
            return inspect_metadata(c,action=action,request_id=request or uuid.uuid4(),revision_id=revision.pk,
                expected_version=revision.version if version is None else version,payload={} if payload is None else payload,
                isolated_db_principal=True)

    def denied(self,expected,**kwargs):
        with self.assertRaises(GatewayError) as error:
            self.call(**kwargs)
        self.assertEqual(error.exception.code,expected)

    def test_01_scoped_metadata_and_b1_fingerprint(self):
        request=uuid.uuid4()
        result=self.call(role="itw_read_editor",action="start_preparation",revision=self.captured,request=request,payload={"x":"日本"})
        self.assertEqual(result,{"writes_enabled":False,"historical_event_id":None,
            "fingerprint":fp(self.f.editor.pk,"start_preparation",self.captured.pk,1,{"x":"日本"})})

    def test_02_shared_login_and_unconfigured_adapter_fail_closed(self):
        self.denied("IDENTITY_VERIFICATION_UNAVAILABLE",role="itw_read_shared")
        with connect("itw_read_editor") as c,self.assertRaises(GatewayError) as error:
            inspect_metadata(c,action="start_preparation",request_id=uuid.uuid4(),revision_id=self.captured.pk,expected_version=1)
        self.assertEqual(error.exception.code,"IDENTITY_VERIFICATION_UNAVAILABLE")

    def test_03_guc_actor_and_role_spoofing_are_rejected(self):
        with connect("itw_read_editor") as c:
            c.execute("SET app.actor_id='999999'")
            result=c.execute("SELECT itw_read_poc.inspect_v1('start_preparation',%s,%s,1,%s)",
                (uuid.uuid4(),self.captured.pk,hashlib.sha256(b"{}").hexdigest())).fetchone()[0]
            self.assertEqual(result["fingerprint"],fp(self.f.editor.pk,"start_preparation",self.captured.pk,1,{}))
            for target in (OWNER,"itw_read_reviewer"):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    c.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(target)))

    def test_04_cross_batch_and_missing_revision_share_denial(self):
        self.denied("ACCESS_DENIED",revision=self.other)
        fake=type("Revision",(),{"pk":uuid.uuid4(),"version":1})()
        self.denied("ACCESS_DENIED",revision=fake)

    def test_05_other_users_history_is_denied(self):
        self.denied("ACCESS_DENIED",role="itw_read_editor",request=self.history_request,version=self.history_version,payload=self.history_payload)

    def test_06_uploader_and_creator_cannot_review(self):
        self.denied("ACCESS_DENIED",role="itw_read_uploader")

    def test_07_contributor_cannot_review(self):
        self.denied("ACCESS_DENIED",role="itw_read_editor",revision=self.contributing)

    def test_08_inactive_user_is_denied(self):
        self.denied("ACCESS_DENIED",role="itw_read_inactive")

    def test_09_ungranted_superuser_is_denied(self):
        self.denied("ACCESS_DENIED",role="itw_read_nogrant")

    def test_10_direct_permission_revocation_is_fresh(self):
        permission=next(p for p in self.permissions if p.codename=="review_import")
        self.f.reviewer.user_permissions.remove(permission)
        try:
            self.denied("ACCESS_DENIED")
        finally:
            self.f.reviewer.user_permissions.add(permission)

    def test_11_group_grants_and_revocations_are_fresh(self):
        self.assertFalse(self.call(role="itw_read_group")["writes_enabled"])
        self.group_user.groups.remove(self.group)
        try:
            self.denied("ACCESS_DENIED",role="itw_read_group")
        finally:
            self.group_user.groups.add(self.group)
        permission=next(p for p in self.permissions if p.codename=="view_import_evidence")
        self.group.permissions.remove(permission)
        try:
            self.denied("ACCESS_DENIED",role="itw_read_group")
        finally:
            self.group.permissions.add(permission)

    def test_12_malformed_requests_and_error_sanitization(self):
        for payload in ({"actor_id":self.f.reviewer.pk},{"x":1.1},{"x":object()}):
            self.denied("INVALID_REQUEST",payload=payload)
        with connect("itw_read_editor") as c:
            for request,revision,version,digest in [(None,self.captured.pk,1,"a"*64),
                (uuid.uuid4(),None,1,"a"*64),(uuid.uuid4(),self.captured.pk,0,"a"*64),
                (uuid.uuid4(),self.captured.pk,1,"bad")]:
                result=c.execute("SELECT itw_read_poc.inspect_v1('start_preparation',%s,%s,%s,%s)",
                    (request,revision,version,digest)).fetchone()[0]
                self.assertEqual(result,{"code":"INVALID_REQUEST","retryable":False})
            with self.assertRaises(GatewayError) as error:
                inspect_metadata(c,action="record_review",request_id="RAW-SECRET",revision_id=self.ready.pk,
                    expected_version=1,isolated_db_principal=True)
            self.assertEqual(str(error.exception),"INVALID_REQUEST")

    def test_13_real_runtime_select_dml_ddl_and_helpers_denied(self):
        with connect("itw_read_editor") as c:
            for table in TABLES+["auth_user","transactions_stockmovement","inventory_stockbalance"]:
                for statement in ("SELECT * FROM "+table+" LIMIT 0","INSERT INTO "+table+" DEFAULT VALUES",
                    "UPDATE "+table+" SET id=id WHERE false" if table!="transactions_stockoperation" else "DELETE FROM "+table+" WHERE false",
                    "DELETE FROM "+table+" WHERE false","TRUNCATE "+table+" CASCADE"):
                    with self.subTest(statement=statement),self.assertRaises(psycopg.errors.InsufficientPrivilege):
                        c.execute(statement)
            for statement in ("ALTER TABLE inventory_importreviewevent DISABLE TRIGGER ALL",
                "CREATE TABLE itw_read_poc.evil(id int)","CREATE SCHEMA evil",
                "CREATE TEMP TABLE evil(id int)","SET session_replication_role=replica",
                "SELECT nextval('inventory_importreviewevent_id_seq')",
                "SELECT itw_read_poc.can(1,'review_import')",
                "SELECT public.itw_review_can(1,'capture_import')",
                "SELECT * FROM itw_read_poc.principal"):
                with self.subTest(statement=statement),self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    c.execute(statement)

    def test_14_definer_has_selected_reads_only_and_no_table_ownership(self):
        with connect() as c:
            self.assertFalse(c.execute("SELECT has_table_privilege(%s,'inventory_importreviewevent','SELECT')",(OWNER,)).fetchone()[0])
            for table in TABLES+["inventory_asset","transactions_stockmovement"]:
                for priv in ("INSERT","UPDATE","DELETE","TRUNCATE"):
                    self.assertFalse(c.execute("SELECT has_table_privilege(%s,%s,%s)",(OWNER,table,priv)).fetchone()[0])
            c.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(OWNER)))
            try:
                for statement in ("SELECT details FROM inventory_importreviewevent",
                    "SELECT reason FROM inventory_importreviewevent",
                    "SELECT draft_payload FROM inventory_importpreparationrevision",
                    "SELECT raw_values FROM inventory_importstagingrecord",
                    "SELECT canonical_bytes FROM inventory_importpreviewsnapshot"):
                    with self.subTest(statement=statement),self.assertRaises(psycopg.errors.InsufficientPrivilege):
                        c.execute(statement)
            finally:
                c.execute("RESET ROLE")

    def test_15_exact_history_is_metadata_only_and_conflicts_deny(self):
        result=self.call(request=self.history_request,version=self.history_version,payload=self.history_payload)
        self.assertEqual(result,{"writes_enabled":False,"historical_event_id":str(self.history.pk),
            "version":self.ready.version,"state":"READY_FOR_REVIEW"})
        self.assertNotIn("CONFIDENTIAL-SENTINEL",json.dumps(result))
        self.denied("REQUEST_CONFLICT",request=self.history_request,version=self.history_version,payload={"changed":True})

    def test_16_version_and_state_checks(self):
        self.denied("VERSION_CONFLICT",version=1)
        self.denied("REVISION_STATE_INVALID",role="itw_read_editor",action="edit_preparation",revision=self.captured)

    def test_17_capture_approval_revocation_and_promotion_disabled(self):
        for action in ("register_verified_capture","approve_revision","revoke_approval","promote_import","unknown"):
            self.denied("ACTION_DISABLED",action=action)

    def test_18_permission_revocation_race_uses_real_advisory_waiter(self):
        permission=next(p for p in self.permissions if p.codename=="review_import")
        with connect() as h,connect("itw_read_reviewer") as w:
            pool=ThreadPoolExecutor(max_workers=1)
            try:
                with h.transaction():
                    h.execute("SELECT pg_advisory_xact_lock(73921,2)")
                    h.execute("DELETE FROM auth_user_user_permissions WHERE user_id=%s AND permission_id=%s",
                        (self.f.reviewer.pk,permission.pk))
                    future=pool.submit(inspect_metadata,w,action="record_review",request_id=uuid.uuid4(),
                        revision_id=self.ready.pk,expected_version=self.ready.version,isolated_db_principal=True)
                    wait_lock(h,w.info.backend_pid)
                with self.assertRaises(GatewayError) as failure:
                    future.result(5)
                self.assertEqual(failure.exception.code,"ACCESS_DENIED")
            finally:
                pool.shutdown()
                self.f.reviewer.user_permissions.add(permission)

    def test_19_snapshot_isolation_rejected(self):
        with connect("itw_read_editor") as c,c.transaction():
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            result=c.execute("SELECT itw_read_poc.inspect_v1('start_preparation',%s,%s,1,%s)",
                (uuid.uuid4(),self.captured.pk,"a"*64)).fetchone()[0]
            self.assertEqual(result,{"code":"UNSUPPORTED_TRANSACTION","retryable":False})

    def test_20_gateway_makes_no_review_or_stock_writes(self):
        self.assertEqual(self.protected_counts(),self.before)
        with connect() as c:
            for t in ("inventory_asset","inventory_stockbalance","transactions_stockmovement","transactions_stockoperation"):
                self.assertEqual(c.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(t))).fetchone()[0],0)
            EVIDENCE["unchanged_counts"]=self.protected_counts()
            EVIDENCE["runtime_memberships"]=c.execute("SELECT count(*) FROM pg_auth_members "
                "WHERE member IN (SELECT oid FROM pg_roles WHERE rolname LIKE 'itw_read_%')").fetchone()[0]