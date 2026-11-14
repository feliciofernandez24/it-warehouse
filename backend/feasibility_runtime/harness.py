"""Disposable restored-database privilege rehearsal. Never imported by application code."""
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid
import psycopg
from psycopg import sql

RUNTIME="itw_django_rehearsal"
REVIEW_OWNER="itw_review_rehearsal_owner"
ALLOWED={"itw_runtime_pre","itw_runtime_rehearsal","itw_runtime_gateway","itw_runtime_gateway_final","itw_runtime_gateway_verify","itw_runtime_gateway_auth"}
BACKUP_SHA256="2dfe16325d081973a41d246a065c631dc54560d459419d411fd820f057f97697"
EVIDENCE={}

def admin():
    name=os.environ.get("POSTGRES_DB")
    if (os.environ.get("ITW_RUNTIME_REHEARSAL")!="1" or name not in ALLOWED
        or os.environ.get("POSTGRES_HOST")!="127.0.0.1"
        or os.environ.get("POSTGRES_USER")!=RUNTIME
        or os.environ.get("POSTGRES_PASSWORD")!="runtime-rehearsal-only"):
        raise RuntimeError("DISPOSABLE_RESTORED_DATABASE_REQUIRED")
    c=psycopg.connect(dbname=name,host="127.0.0.1",user="postgres",
        password="runtime-rehearsal-admin-only",autocommit=True)
    if c.info.server_version!=170011:
        c.close()
        raise RuntimeError("REHEARSAL_REQUIRES_VERIFIED_POSTGRESQL_17_11")
    return c

SELECT_TABLES=[
 "auth_user","auth_group","auth_permission","auth_user_groups",
 "auth_user_user_permissions","auth_group_permissions","django_content_type","django_admin_log",
 "django_session","accounts_assetrecipient","warehouse_warehouse","warehouse_storagelocation",
 "inventory_productmodel",
 "inventory_asset","inventory_stockbalance","transactions_stockoperation",
 "transactions_stockmovement","transactions_assetassignment","audits_physicalinventoryaudit",
 "audits_auditline"]
INSERT_TABLES=["django_session","inventory_asset","inventory_stockbalance","transactions_stockoperation",
 "transactions_stockmovement","transactions_assetassignment","audits_physicalinventoryaudit","audits_auditline"]
UPDATE_COLUMNS={
 "auth_user":["last_login","password"],
 "django_session":["session_data","expire_date"],
 "inventory_productmodel":["version"],
 "transactions_stockmovement":["id"],
 "inventory_asset":["condition","lifecycle_status","current_location_id","version","updated_at"],
 "inventory_stockbalance":["quantity","version","updated_at"],
 "transactions_stockoperation":["approved_by_id","approved_at","approval_reason","posted_at"],
 "transactions_assetassignment":["returned_at","returned_by_id","return_movement_id","updated_at"],
 "audits_physicalinventoryaudit":["status","started_at","updated_at"],
 # record_count currently calls save() without update_fields: all model columns are sent.
 "audits_auditline":None}
SEQUENCES=["inventory_asset_id_seq","inventory_stockbalance_id_seq",
 "transactions_stockmovement_id_seq","transactions_assetassignment_id_seq",
 "audits_physicalinventoryaudit_id_seq","audits_auditline_id_seq"]
HELPERS=["itw_asset_identity_guard()","itw_assignment_identity_guard()",
 "itw_audit_line_guard()","itw_audit_scope_guard()","itw_balance_conservation()",
 "itw_bucket_identity_guard()","itw_can(bigint,text)","itw_custody_guard()",
 "itw_engine_lock()","itw_final_state_guard()","itw_freeze_guard()",
 "itw_frozen(bigint)","itw_hierarchy_guard()","itw_movement_guard()",
 "itw_operation_guard()","itw_product_mode_guard()","itw_reject_history_change()",
 "itw_scope(bigint,boolean)","itw_tracking_guard()"]
CALLABLE_HELPERS=["itw_can(bigint,text)","itw_scope(bigint,boolean)","itw_frozen(bigint)"]
REVIEW_TABLES=["inventory_importbatch","inventory_importstagingrecord","inventory_importsourceprofile",
 "inventory_importpreparationrevision","inventory_importrevisionparticipant",
 "inventory_importpreviewsnapshot","inventory_importreviewevent"]

def prepare():
    with admin() as c:
        EVIDENCE["server"]=c.execute("SELECT version()").fetchone()[0]
        EVIDENCE["migrations"]=c.execute("SELECT app,name FROM django_migrations "
            "WHERE app IN ('inventory','transactions') ORDER BY app,name").fetchall()
        EVIDENCE["owners_before"]=c.execute("SELECT relname,pg_get_userbyid(relowner),relacl::text "
            "FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','S') ORDER BY relname").fetchall()
        EVIDENCE["original_stock_counts"]=c.execute("SELECT "
            "(SELECT count(*) FROM inventory_asset),(SELECT count(*) FROM inventory_stockbalance),"
            "(SELECT count(*) FROM transactions_stockmovement),(SELECT count(*) FROM transactions_stockoperation)").fetchone()
        if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(RUNTIME,)).fetchone():
            c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD 'runtime-rehearsal-only' "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS").format(sql.Identifier(RUNTIME)))
        with c.transaction():
            c.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(os.environ["POSTGRES_DB"])))
            c.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {},itw_rehearsal_migrator").format(
                sql.Identifier(os.environ["POSTGRES_DB"]),sql.Identifier(RUNTIME)))
            c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            c.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(RUNTIME)))
            # Reset superseded candidate SELECT grants only in this disposable rehearsal.
            for table in ["inventory_assetcategory","inventory_manufacturer","inventory_specificationdefinition",
                          "inventory_assetspecification","inventory_stockthreshold","audits_assetchangelog"]:
                c.execute(sql.SQL("REVOKE SELECT ON public.{} FROM {}").format(sql.Identifier(table),sql.Identifier(RUNTIME)))
            # Explicit object lists, never ALL TABLES/ALL SEQUENCES.
            for table in SELECT_TABLES:
                c.execute(sql.SQL("GRANT SELECT ON public.{} TO {}").format(sql.Identifier(table),sql.Identifier(RUNTIME)))
            for table in INSERT_TABLES:
                c.execute(sql.SQL("GRANT INSERT ON public.{} TO {}").format(sql.Identifier(table),sql.Identifier(RUNTIME)))
            for table,columns in UPDATE_COLUMNS.items():
                privilege=sql.SQL("UPDATE") if columns is None else sql.SQL("UPDATE ({})").format(
                    sql.SQL(",").join(map(sql.Identifier,columns)))
                c.execute(sql.SQL("GRANT {} ON public.{} TO {}").format(privilege,sql.Identifier(table),sql.Identifier(RUNTIME)))
            c.execute(sql.SQL("GRANT DELETE ON public.django_session TO {}").format(sql.Identifier(RUNTIME)))
            for sequence in SEQUENCES:
                c.execute(sql.SQL("GRANT USAGE ON SEQUENCE public.{} TO {}").format(sql.Identifier(sequence),sql.Identifier(RUNTIME)))
            for function in HELPERS:
                c.execute(sql.SQL("REVOKE EXECUTE ON FUNCTION public.{} FROM PUBLIC").format(sql.SQL(function)))
                c.execute(sql.SQL("REVOKE EXECUTE ON FUNCTION public.{} FROM {}").format(sql.SQL(function),sql.Identifier(RUNTIME)))
                if function in CALLABLE_HELPERS:
                    c.execute(sql.SQL("GRANT EXECUTE ON FUNCTION public.{} TO {}").format(sql.SQL(function),sql.Identifier(RUNTIME)))
        EVIDENCE["grants"]={"select":SELECT_TABLES,"insert":INSERT_TABLES,
            "update":UPDATE_COLUMNS,"delete":["django_session"],"sequence_usage":SEQUENCES,"callable_helpers":CALLABLE_HELPERS,"stock_functions_public_execute_revoked":HELPERS}

def django_setup():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings.development")
    import django
    django.setup()
    from django.db import connections
    owner=connections["default"].settings_dict.copy()
    owner.update(USER="itw_rehearsal_migrator",PASSWORD="migration-rehearsal-only",
        OPTIONS={"options":"-c role=it_warehouse"})
    connections.databases["owner"]=owner

def create_review_fixture():
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission
    from apps.inventory.models import ImportBatch,ImportStagingRecord,ImportSourceProfile
    from apps.inventory.staging.common import canonical
    user=get_user_model().objects.using("owner").create(username="review-"+uuid.uuid4().hex,is_active=True)
    permission=Permission.objects.using("owner").get(content_type__app_label="inventory",
        content_type__model="importbatch",codename="capture_import")
    user.user_permissions.add(permission)
    batch=ImportBatch.objects.using("owner").create(original_filename="SYNTHETIC-ONLY.xlsx",
        file_sha256="a"*64,source_storage_key="synthetic",uploaded_by=user,mapping_version="synthetic")
    ImportStagingRecord.objects.using("owner").create(batch=batch,worksheet_name="Synthetic",
        excel_row_number=2,normalized_values={"capture":{"classification":"CANDIDATE"}},source_row_digest="b"*64)
    doc={"domain":"itw.source-profile.v1","code":"SYN-"+uuid.uuid4().hex.upper(),"version":1,
        "workbook_sha256":"a"*64,"layout_digest":"d"*64,
        "expected_counts":{"worksheets":1,"populated":1,"CANDIDATE":1,"HEADER":0,"SEQUENCE_ONLY":0}}
    data=canonical(doc)
    profile=ImportSourceProfile.objects.using("owner").create(code=doc["code"],version=1,
        workbook_sha256=doc["workbook_sha256"],layout_digest=doc["layout_digest"],
        expected_counts=doc["expected_counts"],canonical_bytes=data,digest=hashlib.sha256(data).hexdigest(),
        definition_verified=True,verification_evidence_digest="1"*64)
    return batch,profile,user

def gateway_setup():
    from feasibility_capture.common import PROOF_FUNCTION
    batch,profile,user=create_review_fixture()
    with admin() as c:
        if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(REVIEW_OWNER,)).fetchone():
            c.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOINHERIT NOBYPASSRLS").format(sql.Identifier(REVIEW_OWNER)))
        with c.transaction():
            c.execute(sql.SQL("CREATE SCHEMA fa_owner AUTHORIZATION {}").format(sql.Identifier(REVIEW_OWNER)))
            c.execute(PROOF_FUNCTION)
            c.execute(sql.SQL("ALTER FUNCTION fa_owner.enroll(bigint,uuid) OWNER TO {}").format(sql.Identifier(REVIEW_OWNER)))
            c.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(REVIEW_OWNER)))
            c.execute(sql.SQL("GRANT SELECT(id,is_active) ON auth_user TO {}").format(sql.Identifier(REVIEW_OWNER)))
            for table in ["auth_permission","django_content_type","auth_user_user_permissions","auth_user_groups","auth_group_permissions"]:
                c.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(sql.Identifier(table),sql.Identifier(REVIEW_OWNER)))
            for fn, in c.execute("SELECT oid::regprocedure::text FROM pg_proc "
                    "WHERE pronamespace='public'::regnamespace AND proname LIKE 'itw_review_%'").fetchall():
                c.execute(sql.SQL("GRANT EXECUTE ON FUNCTION {} TO {}").format(sql.SQL(fn),sql.Identifier(REVIEW_OWNER)))
            for table in REVIEW_TABLES:
                c.execute(sql.SQL("ALTER TABLE public.{} OWNER TO {}").format(sql.Identifier(table),sql.Identifier(REVIEW_OWNER)))
            c.execute(sql.SQL("GRANT USAGE ON SCHEMA fa_owner TO {}").format(sql.Identifier(RUNTIME)))
            c.execute(sql.SQL("GRANT EXECUTE ON FUNCTION fa_owner.enroll(bigint,uuid) TO {}").format(sql.Identifier(RUNTIME)))
        EVIDENCE["gateway_fixture"]={"batch_id":batch.pk,"profile_id":str(profile.pk)}
        EVIDENCE["review_owners"]=c.execute("SELECT relname,pg_get_userbyid(relowner) FROM pg_class "
            "WHERE relnamespace='public'::regnamespace AND relname LIKE 'inventory_import%' "
            "AND relkind IN ('r','S') ORDER BY relname").fetchall()
    return batch.pk,profile.pk