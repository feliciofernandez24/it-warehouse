"""ISOLATED FEASIBILITY ONLY. No operational capture API or production installer."""
import hashlib
import json
import os
import time
import uuid
import psycopg
from psycopg import sql
from apps.inventory.staging.common import canonical

BASE = "phase3b2b1_test"
PREFIX = "phase3b2b2a_"
OWNER = "itw_fa_owner"
RUNTIME = "itw_fa_runtime"
PASSWORD = "feasibility-synthetic-only"
EVIDENCE = {}


def connect(database=BASE, runtime=False):
    if (os.environ.get("ITW_CAPTURE_FEASIBILITY") != "1"
        or os.environ.get("POSTGRES_HOST") != "127.0.0.1"
        or os.environ.get("POSTGRES_DB") != BASE
        or os.environ.get("POSTGRES_PASSWORD") != "phase3b2b2a-isolated-only"
        or not (database == BASE or database.startswith(PREFIX))):
        raise RuntimeError("ISOLATED_FEASIBILITY_REQUIRED")
    conn = psycopg.connect(host="127.0.0.1", dbname=database,
        user=RUNTIME if runtime else "postgres",
        password=PASSWORD if runtime else os.environ["POSTGRES_PASSWORD"],
        autocommit=True)
    if conn.info.server_version // 10000 != 17:
        conn.close()
        raise RuntimeError("POSTGRESQL_17_REQUIRED")
    if not runtime:
        conn.execute("SET pgsodium.enable_event_trigger=off")  # Isolated workaround for unused extension masking DDL hook.
    return conn


def clone(label):
    name = PREFIX + label + "_" + uuid.uuid4().hex[:8]
    with connect() as c:
        c.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
            sql.Identifier(name), sql.Identifier(BASE)))
    return name


def lock(c):
    c.execute("SELECT pg_catalog.pg_advisory_xact_lock(73921,2)")


def wait_for_lock(observer, pid, timeout=5):
    # Poll catalog state with a deadline; no assertion relies on sleep duration.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if observer.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_locks WHERE pid=%s "
            "AND locktype='advisory' AND NOT granted)", (pid,)).fetchone()[0]:
            return
        time.sleep(.01)
    raise AssertionError("EXPECTED_ADVISORY_WAITER")


def strict_load(data):
    if len(data) > 65536:
        raise ValueError("LIMIT")
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError("DUPLICATE_KEY")
            result[k] = v
        return result
    value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
        parse_float=lambda _: (_ for _ in ()).throw(ValueError("FLOAT")),
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("CONSTANT")))
    if canonical(value) != data:
        raise ValueError("NONCANONICAL")
    return value


def fixture(c, owner=False):
    actor = c.execute("INSERT INTO public.auth_user(password,is_superuser,username,"
        "first_name,last_name,email,is_staff,is_active,date_joined) "
        "VALUES('',false,%s,'','','',false,true,now()) RETURNING id",
        ("synthetic-" + uuid.uuid4().hex,)).fetchone()[0]
    c.execute("INSERT INTO public.auth_user_user_permissions(user_id,permission_id) "
        "SELECT %s,p.id FROM public.auth_permission p "
        "JOIN public.django_content_type t ON t.id=p.content_type_id "
        "WHERE t.app_label='inventory' AND t.model='importbatch' AND p.codename='capture_import'", (actor,))
    if owner:
        c.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(OWNER)))
    try:
        batch = c.execute("INSERT INTO public.inventory_importbatch "
            "(public_id,original_filename,file_sha256,source_storage_key,uploaded_by_id,"
            "uploaded_at,mapping_version,source_timezone,status,approved_preview_digest,notes,version,created_at,updated_at) "
            "VALUES(%s,'SYNTHETIC-ONLY.xlsx',%s,'synthetic-only',%s,now(),'proof','Asia/Tokyo',"
            "'UPLOADED','','',0,now(),now()) RETURNING id", (uuid.uuid4(), "a"*64, actor)).fetchone()[0]
        c.execute("INSERT INTO public.inventory_importstagingrecord "
            "(batch_id,worksheet_name,excel_row_number,raw_values,normalized_values,"
            "validation_errors,validation_warnings,status,source_row_digest,version,created_at,updated_at) "
            "VALUES(%s,'Synthetic',2,'[]','{\"capture\":{\"classification\":\"CANDIDATE\"}}',"
            "'[]','[]','CAPTURED',%s,0,now(),now())", (batch, "b"*64))
        profile = uuid.uuid4()
        doc = {"domain":"itw.source-profile.v1","code":"SYN-"+uuid.uuid4().hex.upper(),
            "version":1,"workbook_sha256":"a"*64,"layout_digest":"d"*64,
            "expected_counts":{"worksheets":1,"populated":1,"CANDIDATE":1,"HEADER":0,"SEQUENCE_ONLY":0}}
        data = canonical(doc)
        c.execute("INSERT INTO public.inventory_importsourceprofile "
            "(id,code,version,workbook_sha256,layout_digest,expected_counts,canonical_bytes,"
            "digest,definition_verified,verification_evidence_digest,registered_by) "
            "VALUES(%s,%s,1,%s,%s,%s::jsonb,%s,%s,true,%s,'')",
            (profile,doc["code"],"a"*64,"d"*64,json.dumps(doc["expected_counts"]),
             data,hashlib.sha256(data).hexdigest(),"1"*64))
        return batch, profile, actor
    finally:
        if owner:
            c.execute("RESET ROLE")


TABLES = ["inventory_importbatch", "inventory_importstagingrecord",
    "inventory_importsourceprofile", "inventory_importpreparationrevision",
    "inventory_importrevisionparticipant", "inventory_importpreviewsnapshot",
    "inventory_importreviewevent"]

# Deliberately NOT authenticated registration: only preseeded synthetic rows.
PROOF_FUNCTION = """
CREATE FUNCTION fa_owner.enroll(b bigint, p uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE r uuid:=pg_catalog.gen_random_uuid(); a bigint;
BEGIN
 PERFORM pg_catalog.pg_advisory_xact_lock(73921,2);
 SELECT uploaded_by_id INTO a FROM public.inventory_importbatch
 WHERE id=b AND original_filename='SYNTHETIC-ONLY.xlsx' FOR UPDATE;
 IF a IS NULL THEN RAISE EXCEPTION 'SYNTHETIC_FIXTURE_REQUIRED'; END IF;
 INSERT INTO public.inventory_importpreparationrevision
 (id,batch_id,source_profile_id,revision_number,state,version,created_by_id,
 layout_digest,manifest_digest,capture_storage_key,capture_artifact_digest,draft_payload)
 VALUES(r,b,p,1,'CAPTURED',1,a,repeat('d',64),repeat('e',64),'synthetic-only',repeat('f',64),'{}');
 INSERT INTO public.inventory_importreviewevent
 (revision_id,sequence,request_id,request_fingerprint,actor_id,kind,from_state,to_state,
 reason_code,reason,details)
 VALUES(r,1,pg_catalog.gen_random_uuid(),repeat('c',64),a,'CAPTURE','CAPTURED','CAPTURED',
 'SYNTHETIC_ONLY','Synthetic proof',
 jsonb_build_object('after_payload_digest',encode(sha256(convert_to('{}'::jsonb::text,'UTF8')),'hex')));
 SET CONSTRAINTS ALL IMMEDIATE;
 RETURN r;
END $$;
REVOKE ALL ON FUNCTION fa_owner.enroll(bigint,uuid) FROM PUBLIC;
"""


def owner_setup(c, transfer):
    with c.transaction():
        c.execute("CREATE SCHEMA fa_owner AUTHORIZATION " + OWNER)
        c.execute(PROOF_FUNCTION)
        c.execute("ALTER FUNCTION fa_owner.enroll(bigint,uuid) OWNER TO " + OWNER)
        c.execute("GRANT USAGE ON SCHEMA public TO " + OWNER)
        c.execute("GRANT SELECT(id,is_active) ON public.auth_user TO " + OWNER)
        c.execute("GRANT SELECT ON public.auth_permission,public.django_content_type,"
            "public.auth_user_user_permissions,public.auth_user_groups,public.auth_group_permissions TO " + OWNER)
        for (fn,) in c.execute("SELECT oid::regprocedure::text FROM pg_catalog.pg_proc "
                "WHERE pronamespace='public'::regnamespace AND proname LIKE 'itw_review_%'").fetchall():
            c.execute(sql.SQL("GRANT EXECUTE ON FUNCTION {} TO {}").format(sql.SQL(fn),sql.Identifier(OWNER)))
        c.execute("GRANT USAGE ON SCHEMA fa_owner TO " + RUNTIME)
        c.execute("GRANT EXECUTE ON FUNCTION fa_owner.enroll(bigint,uuid) TO " + RUNTIME)
        if transfer:
            transfer_tables(c)

def transfer_tables(c):
    with c.transaction():
        for table in TABLES:
            c.execute(sql.SQL("ALTER TABLE public.{} OWNER TO {}").format(
                sql.Identifier(table),sql.Identifier(OWNER)))