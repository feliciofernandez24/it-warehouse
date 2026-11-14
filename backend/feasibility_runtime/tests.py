"""Actual Django runtime LOGIN tests over a disposable restored database."""
import copy
from datetime import date
import unittest
import uuid
from contextlib import contextmanager
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.sessions.models import Session
from django.db import connections, connection, transaction, DatabaseError
from django.test import Client, override_settings
from django.utils import timezone
from psycopg import sql
from apps.accounts.models import AssetRecipient
from apps.inventory.models import (AssetCategory,ProductModel,Asset,StockBalance,
    ImportBatch,ImportStagingRecord,ImportPreparationRevision,ImportReviewEvent)
from apps.warehouse.models import Warehouse,StorageLocation
from apps.transactions.models import StockMovement,StockOperation,AssetAssignment
from apps.transactions.services import Line,Request,post
from apps.transactions.services.exceptions import AuthorizationError,IdempotencyConflict
from apps.transactions.services.audits import start_audit,record_count
from apps.audits.models import PhysicalInventoryAudit,AuditLine
from harness import (admin,RUNTIME,REVIEW_OWNER,EVIDENCE,create_review_fixture,REVIEW_TABLES)

def denied_sql(query,params=None,code=None):
    with transaction.atomic():
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(query,params)
        except DatabaseError as error:
            if code and error.__cause__.sqlstate != code:
                raise AssertionError((error.__cause__.sqlstate,code)) from error
            return str(error)
        raise AssertionError("EXPECTED_DATABASE_DENIAL")

@contextmanager
def accidental_grant(privilege,table):
    # Test-only, exact grant over synthetic targets; never production setup.
    with admin() as c:
        prior_columns=c.execute("SELECT column_name FROM information_schema.role_column_grants "
            "WHERE grantee=%s AND table_name=%s AND privilege_type='UPDATE'",(RUNTIME,table)).fetchall()
        c.execute(sql.SQL("GRANT {} ON public.{} TO {}").format(
            sql.SQL(privilege),sql.Identifier(table),sql.Identifier(RUNTIME)))
    try:
        yield
    finally:
        with admin() as c:
            c.execute(sql.SQL("REVOKE {} ON public.{} FROM {}").format(
                sql.SQL(privilege),sql.Identifier(table),sql.Identifier(RUNTIME)))
            if "UPDATE" in privilege and prior_columns:
                c.execute(sql.SQL("GRANT UPDATE ({}) ON public.{} TO {}").format(
                    sql.SQL(",").join(sql.Identifier(row[0]) for row in prior_columns),
                    sql.Identifier(table),sql.Identifier(RUNTIME)))

class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tag="R"+uuid.uuid4().hex[:10].upper()
        cls.user=get_user_model().objects.db_manager("owner").create_user(
            username=tag,password="Synthetic-rehearsal-7319!",is_staff=True,is_superuser=True)
        from django.contrib.auth.hashers import PBKDF2PasswordHasher
        old_hasher=PBKDF2PasswordHasher()
        old_hasher.iterations=1
        cls.user.password=old_hasher.encode("Synthetic-rehearsal-7319!","synthetic-test-salt")
        cls.user.save(using="owner",update_fields=["password"])
        cls.ungranted=get_user_model().objects.using("owner").create(username=tag+"-denied",is_staff=True,is_superuser=True)
        cls.user.user_permissions.add(*Permission.objects.using("owner").filter(content_type__app_label="transactions"))
        cls.site=Warehouse.objects.using("owner").create(code=tag,name="Synthetic site")
        cls.area=StorageLocation.objects.using("owner").create(warehouse=cls.site,code=tag+"A",name="Area",kind="AREA")
        cls.other=StorageLocation.objects.using("owner").create(warehouse=cls.site,code=tag+"B",name="Other",kind="AREA")
        category=AssetCategory.objects.using("owner").create(code=tag,name="Synthetic")
        cls.bulk=ProductModel.objects.using("owner").create(sku_code=tag+"B",name="Bulk",category=category,tracking_mode="BULK")
        cls.serial=ProductModel.objects.using("owner").create(sku_code=tag+"S",name="Serial",category=category,tracking_mode="SERIALIZED")
        cls.recipient=AssetRecipient.objects.using("owner").create(code=tag,name="Synthetic recipient")

    def setUp(self):
        self.atomic=transaction.atomic()
        self.atomic.__enter__()
        self.actor=get_user_model().objects.get(pk=self.user.pk)

    def tearDown(self):
        transaction.set_rollback(True)
        self.atomic.__exit__(None,None,None)

    def request(self,*lines,key=None):
        return Request(key or uuid.uuid4(),tuple(lines),"Synthetic runtime rehearsal")

    def bulk_line(self,kind="STOCK_IN",quantity=10,**kwargs):
        values={"operation_type":kind,"quantity":quantity,"product_model_id":self.bulk.pk}
        if kind in ("STOCK_IN","RETURN"):
            values["destination_location_id"]=self.area.pk
        else:
            values["source_location_id"]=self.area.pk
        if kind=="TRANSFER":
            values["destination_location_id"]=self.other.pk
        values.update(kwargs)
        return Line(**values)

    def receive(self):
        return post(actor=self.actor,request=self.request(self.bulk_line()))

    def test_01_actual_runtime_identity_and_owner_separation(self):
        with connection.cursor() as c:
            c.execute("SELECT session_user,current_user")
            self.assertEqual(c.fetchone(),(RUNTIME,RUNTIME))
            c.execute("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls "
                "OR rolinherit FROM pg_roles WHERE rolname=current_user")
            self.assertFalse(c.fetchone()[0])
            c.execute("SELECT pg_has_role(current_user,'it_warehouse','MEMBER'),"
                "pg_has_role(current_user,'itw_rehearsal_migrator','MEMBER')")
            self.assertEqual(c.fetchone(),(False,False))
        with connections["owner"].cursor() as c:
            c.execute("SELECT session_user,current_user")
            self.assertEqual(c.fetchone(),("itw_rehearsal_migrator","it_warehouse"))

    @override_settings(ALLOWED_HOSTS=["testserver"])
    def test_02_django_login_session_update_logout_and_admin_index(self):
        client=Client()
        self.assertTrue(client.login(username=self.user.username,password="Synthetic-rehearsal-7319!"))
        authenticated=get_user_model().objects.get(pk=self.user.pk)
        self.assertIsNotNone(authenticated.last_login)
        self.assertFalse(authenticated.password.startswith("pbkdf2_sha256$1$"))
        session=client.session
        session["synthetic"]="rehearsal"
        session.save()
        key=session.session_key
        self.assertTrue(Session.objects.filter(pk=key).exists())
        self.assertEqual(client.get("/admin/").status_code,200)
        self.assertEqual(client.get("/api/health/").status_code,200)
        client.logout()
        self.assertFalse(Session.objects.filter(pk=key).exists())

    def test_03_bulk_receive_issue_transfer_return_and_replay(self):
        request=self.request(self.bulk_line())
        result=post(actor=self.actor,request=request)
        self.assertEqual(post(actor=self.actor,request=request),result)
        with self.assertRaises(IdempotencyConflict):
            post(actor=self.actor,request=self.request(self.bulk_line(quantity=11),key=request.operation_key))
        issued=post(actor=self.actor,request=self.request(self.bulk_line("STOCK_OUT",2)))
        post(actor=self.actor,request=self.request(self.bulk_line("RETURN",2,reverses_id=issued.movement_ids[0])))
        post(actor=self.actor,request=self.request(self.bulk_line("TRANSFER",3)))
        self.assertEqual(StockBalance.objects.get(product_model_id=self.bulk.pk,location_id=self.area.pk).quantity,7)
        self.assertEqual(StockBalance.objects.get(product_model_id=self.bulk.pk,location_id=self.other.pk).quantity,3)

    def test_04_serialized_receive_issue_and_return(self):
        received=post(actor=self.actor,request=self.request(Line("STOCK_IN",
            product_model_id=self.serial.pk,destination_location_id=self.area.pk,device_name="Synthetic unit")))
        asset=Asset.objects.get(pk=received.asset_ids[0])
        issued=post(actor=self.actor,request=self.request(Line("STOCK_OUT",asset_id=asset.pk,
            source_location_id=self.area.pk,recipient_id=self.recipient.pk,destination_reference="synthetic-host")))
        assignment=AssetAssignment.objects.get(asset=asset)
        post(actor=self.actor,request=self.request(Line("RETURN",asset_id=asset.pk,
            assignment_id=assignment.pk,reverses_id=issued.movement_ids[0],destination_location_id=self.other.pk)))
        asset.refresh_from_db(); assignment.refresh_from_db()
        self.assertEqual(asset.current_location_id,self.other.pk)
        self.assertIsNotNone(assignment.returned_at)

    def test_05_unauthorized_actor_is_denied_even_under_valid_sql_login(self):
        actor=get_user_model().objects.get(pk=self.ungranted.pk)
        with self.assertRaises(AuthorizationError):
            post(actor=actor,request=self.request(self.bulk_line()))

    def test_06_direct_balance_change_hits_conservation_guard(self):
        self.receive()
        message=denied_sql("UPDATE inventory_stockbalance SET quantity=quantity+1 WHERE product_model_id=%s;"
            " SET CONSTRAINTS ALL IMMEDIATE",(self.bulk.pk,),code="23514")
        self.assertIn("conservation",message.lower())

    def test_07_orphan_movement_hits_operation_guard(self):
        result=self.receive()
        movement=StockMovement.objects.get(pk=result.movement_ids[0])
        movement.pk=None; movement.public_id=uuid.uuid4(); movement.operation_key=uuid.uuid4()
        with self.assertRaisesRegex(DatabaseError,"open operation"):
            with transaction.atomic():
                movement.save(force_insert=True)

    def test_08_ledger_immutable_even_with_accidental_update_delete_grants(self):
        result=self.receive()
        with accidental_grant("UPDATE,DELETE","transactions_stockmovement"):
            for statement in ("UPDATE transactions_stockmovement SET reason='changed' WHERE id=%s",
                              "DELETE FROM transactions_stockmovement WHERE id=%s"):
                with self.subTest(statement=statement):
                    message=denied_sql(statement,(result.movement_ids[0],),code="23514")
                    self.assertIn("historical record",message.lower())

    def test_09_posted_operation_is_immutable(self):
        result=self.receive()
        message=denied_sql("UPDATE transactions_stockoperation SET posted_at=now() WHERE operation_key=%s",
            (result.operation_key,),code="23514")
        self.assertIn("immutable",message.lower())
        denied_sql("UPDATE transactions_stockmovement SET id=id WHERE id=%s",
            (result.movement_ids[0],),code="23514")

    def test_10_ddl_truncate_schema_and_owner_assumption_denied(self):
        for statement in (
            "ALTER TABLE inventory_asset ADD COLUMN forbidden integer",
            "ALTER TABLE inventory_stockbalance DISABLE TRIGGER ALL",
            "TRUNCATE transactions_stockmovement CASCADE",
            "TRUNCATE inventory_asset CASCADE",
            "SET ROLE it_warehouse","SET ROLE itw_rehearsal_migrator",
            "SET session_replication_role=replica",
            "CREATE SCHEMA forbidden","CREATE TABLE public.forbidden(id int)",
            "CREATE TEMP TABLE forbidden(id int)"):
            with self.subTest(statement=statement):
                denied_sql(statement,code="42501")

    def test_11_nonrequired_dml_and_sequences_denied(self):
        for statement in (
            "INSERT INTO auth_user DEFAULT VALUES","UPDATE auth_user SET is_superuser=true WHERE id=0",
            "DELETE FROM auth_user WHERE id=0","INSERT INTO auth_user_groups DEFAULT VALUES",
            "INSERT INTO auth_user_user_permissions DEFAULT VALUES",
            "INSERT INTO auth_group_permissions DEFAULT VALUES",
            "UPDATE inventory_productmodel SET name='changed' WHERE id=0",
            "INSERT INTO inventory_importbatch DEFAULT VALUES",
            "DELETE FROM transactions_stockoperation WHERE false",
            "DELETE FROM inventory_stockbalance WHERE false",
            "SELECT nextval('auth_user_id_seq')",
            "INSERT INTO django_migrations DEFAULT VALUES",
            "SELECT public.itw_engine_lock()"):
            with self.subTest(statement=statement):
                denied_sql(statement,code="42501")

    def test_12_audit_start_count_and_freeze_guard(self):
        self.receive()
        audit=PhysicalInventoryAudit.objects.create(scope_location_id=self.area.pk,
            performed_by=self.actor,planned_date=date(2026,11,14))
        start_audit(actor=self.actor,audit_id=audit.pk)
        line=AuditLine.objects.get(audit=audit,stock_balance__product_model_id=self.bulk.pk)
        record_count(actor=self.actor,line_id=line.pk,quantity=10,condition="NEW",state="AVAILABLE")
        line.refresh_from_db()
        self.assertEqual(line.outcome,"MATCH")
        denied_sql("UPDATE audits_auditline SET expected_quantity=expected_quantity+1 WHERE id=%s",
            (line.pk,),code="23514")
        with self.assertRaisesRegex(DatabaseError,"frozen"):
            with transaction.atomic():
                post(actor=self.actor,request=self.request(self.bulk_line(quantity=1)))


class ReviewTests(unittest.TestCase):
    def test_01_no_direct_review_evidence_or_writes(self):
        for table in REVIEW_TABLES:
            for query in ("SELECT * FROM "+table+" LIMIT 0","INSERT INTO "+table+" DEFAULT VALUES",
                          "TRUNCATE "+table+" CASCADE"):
                with self.subTest(query=query):
                    denied_sql(query,code="42501")

    def test_02_private_review_helpers_are_not_callable(self):
        denied_sql("SELECT public.itw_review_assert(gen_random_uuid())",code="42501")
        denied_sql("SELECT public.itw_review_can(1,'capture_import')",code="42501")

    def test_03_owner_only_guard_survives_accidental_grants(self):
        with accidental_grant("INSERT","inventory_importrevisionparticipant"):
            with admin() as c:
                c.execute(sql.SQL("GRANT USAGE ON SEQUENCE inventory_importrevisionparticipant_id_seq TO {}").format(sql.Identifier(RUNTIME)))
            try:
                message=denied_sql("INSERT INTO inventory_importrevisionparticipant(revision_id,user_id)"
                    " VALUES(%s,1)",(uuid.uuid4(),),code="23514")
                self.assertIn("REVIEW_SERVICE_DISABLED",message)
            finally:
                with admin() as c:
                    c.execute(sql.SQL("REVOKE USAGE ON SEQUENCE inventory_importrevisionparticipant_id_seq FROM {}").format(sql.Identifier(RUNTIME)))

    def test_04_existing_readonly_capture_preflight_fails_closed(self):
        from apps.inventory.review.services import register_verified_capture
        from apps.inventory.review.errors import ReviewServiceError
        # Identity provenance is a synthetic fixture, not authenticated upload evidence.
        user=get_user_model().objects.using("owner").create(username="cap-"+uuid.uuid4().hex)
        permission=Permission.objects.using("owner").get(content_type__app_label="inventory",
            content_type__model="importbatch",codename="capture_import")
        user.user_permissions.add(permission)
        actor=get_user_model().objects.get(pk=user.pk)
        with self.assertRaises(ReviewServiceError) as failure:
            register_verified_capture(actor=actor,request_id=uuid.uuid4(),payload={})
        EVIDENCE["capture_preflight_denial"]=failure.exception.code
        self.assertNotIn("permission denied",str(failure.exception).lower())


class GatewayTests(unittest.TestCase):
    target=None

    def test_01_actual_django_runtime_can_call_owner_guard_compatible_proof(self):
        b,p=self.target
        with transaction.atomic():
            with connection.cursor() as c:
                c.execute("SELECT fa_owner.enroll(%s,%s)",(b,p))
                revision=c.fetchone()[0]
            with admin() as c:
                # Uncommitted row is deliberately invisible to this independent observer.
                self.assertEqual(c.execute("SELECT count(*) FROM inventory_importpreparationrevision WHERE id=%s",
                    (revision,)).fetchone()[0],0)
        with admin() as c:
            self.assertEqual(c.execute("SELECT state,version FROM inventory_importpreparationrevision WHERE id=%s",
                (revision,)).fetchone(),("CAPTURED",1))
            self.assertEqual(c.execute("SELECT count(*) FROM inventory_importreviewevent WHERE revision_id=%s AND kind='CAPTURE'",
                (revision,)).fetchone()[0],1)
        EVIDENCE["gateway_capture_committed"]=True

    def test_02_no_review_owner_membership_or_stock_privilege_expansion(self):
        denied_sql("SET ROLE "+REVIEW_OWNER,code="42501")
        denied_sql("SELECT * FROM inventory_importreviewevent LIMIT 0",code="42501")
        with connection.cursor() as c:
            c.execute("SELECT pg_has_role(current_user,%s,'MEMBER')",(REVIEW_OWNER,))
            self.assertFalse(c.fetchone()[0])
        with admin() as c:
            self.assertFalse(c.execute("SELECT has_table_privilege(%s,'inventory_asset','INSERT')",(REVIEW_OWNER,)).fetchone()[0])