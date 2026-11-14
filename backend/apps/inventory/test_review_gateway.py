"""Real nonsuperuser LOGIN checks against an isolated read-only SQL POC."""
from pathlib import Path
import psycopg
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection, transaction
from django.test import TransactionTestCase

class RestrictedGatewayTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.settings_dict["NAME"] != "test_phase3b2b1_test":
            raise RuntimeError("ISOLATED_DATABASE_REQUIRED")
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(Path(__file__).with_name("review").joinpath("gateway_poc.sql.example").read_text())

    @classmethod
    def tearDownClass(cls):
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("DROP SCHEMA itw_review_gateway_poc CASCADE")
                # These exact newly created roles own no application objects.
                cursor.execute("DROP OWNED BY itw_review_poc_owner, itw_review_poc_runtime")
                cursor.execute("DROP ROLE itw_review_poc_runtime, itw_review_poc_owner")
        finally:
            super().tearDownClass()

    def setUp(self):
        cfg = connection.settings_dict
        self.runtime = psycopg.connect(dbname=cfg["NAME"], host=cfg["HOST"], port=cfg["PORT"] or 5432,
            user="itw_review_poc_runtime", password="isolated-poc-only", autocommit=True)
        self.addCleanup(self.runtime.close)
        self.user = get_user_model().objects.create_user(username="poc-synthetic")

    def denied_sql(self, sql):
        with self.assertRaises(psycopg.Error):
            self.runtime.execute(sql)

    def test_real_login_privileges(self):
        row = self.runtime.execute("SELECT session_user,current_user").fetchone()
        self.assertEqual(row, ("itw_review_poc_runtime", "itw_review_poc_runtime"))
        self.denied_sql("SET ROLE itw_review_poc_owner")
        self.denied_sql("SET ROLE postgres")
        self.denied_sql("CREATE ROLE forbidden_role")
        self.denied_sql("CREATE TABLE public.forbidden_table(id integer)")

    def test_direct_review_mutations_and_evidence_denied(self):
        for sql in (
            "UPDATE public.inventory_importpreparationrevision SET version=version+1",
            "DELETE FROM public.inventory_importrevisionparticipant",
            "INSERT INTO public.inventory_importreviewevent DEFAULT VALUES",
            "TRUNCATE public.inventory_importreviewevent",
            "ALTER TABLE public.inventory_importreviewevent DISABLE TRIGGER ALL",
            "SELECT * FROM public.inventory_importpreviewsnapshot",
            "SELECT public.itw_review_check_profile(0,NULL,NULL)",
            "SELECT nextval('public.inventory_importreviewevent_id_seq')",
        ):
            self.denied_sql(sql)

    def test_stock_writes_denied(self):
        for table in ("inventory_asset", "inventory_stockbalance",
                      "transactions_stockmovement", "transactions_stockoperation"):
            self.denied_sql("DELETE FROM public." + table)

    def test_explicit_permission_read_and_guc_not_authentication(self):
        def authorize():
            return self.runtime.execute("SELECT itw_review_gateway_poc.authorize(%s,%s)",
                (self.user.pk, "inventory.review_import")).fetchone()[0]
        self.assertEqual(authorize(), "PERMISSION_DENIED")
        self.runtime.execute("SET app.actor_id='1'")
        self.assertEqual(authorize(), "PERMISSION_DENIED")
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label="inventory", codename="review_import"))
        self.assertEqual(authorize(), "OK")
        self.user.user_permissions.clear()
        self.assertEqual(authorize(), "PERMISSION_DENIED")

    def test_procedure_owner_cannot_write(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT has_table_privilege('itw_review_poc_owner','public.inventory_importreviewevent','INSERT'), has_table_privilege('itw_review_poc_owner','public.inventory_asset','INSERT')")
            self.assertEqual(cursor.fetchone(), (False, False))
            cursor.execute("SELECT prosecdef,proconfig FROM pg_proc WHERE oid='itw_review_gateway_poc.authorize(bigint,text)'::regprocedure")
            elevated, config = cursor.fetchone()
            self.assertTrue(elevated)
            self.assertIn("search_path=pg_catalog, pg_temp", config)
