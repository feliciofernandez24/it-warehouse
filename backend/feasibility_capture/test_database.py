"""Ownership and real two-connection authorization feasibility tests."""
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
import psycopg
from psycopg import sql
from common import (connect, clone, OWNER, RUNTIME, PASSWORD, TABLES, fixture,
    owner_setup, transfer_tables, lock, wait_for_lock, EVIDENCE)


class OwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with connect() as c:
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(OWNER,)).fetchone():
                c.execute("CREATE ROLE " + OWNER +
                " NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS")
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(RUNTIME,)).fetchone():
                c.execute("CREATE ROLE " + RUNTIME +
                " LOGIN PASSWORD '" + PASSWORD +
                "' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS")
        cls.db = clone("owner")
        with connect(cls.db) as c:
            EVIDENCE["catalog_before"] = c.execute(
                "SELECT relname,relkind,pg_get_userbyid(relowner),relacl::text "
                "FROM pg_class WHERE relnamespace='public'::regnamespace "
                "AND (relname LIKE 'inventory_import%' OR relkind='S') ORDER BY relname").fetchall()
            EVIDENCE["functions_before"] = c.execute(
                "SELECT proname,pg_get_userbyid(proowner),prosecdef,proacl::text "
                "FROM pg_proc WHERE pronamespace='public'::regnamespace "
                "AND proname LIKE 'itw_%' ORDER BY proname").fetchall()
            owner_setup(c, True)

    def test_fresh_and_populated_upgrade(self):
        for mode in ("fresh", "populated"):
            with self.subTest(mode=mode):
                db = clone(mode)
                with connect(db) as c:
                    before = fixture(c) if mode == "populated" else None
                    owner_setup(c, mode == "fresh")
                    old_revision = None
                    if mode == "populated":
                        # Seed a complete pre-upgrade review history under its original owner.
                        c.execute("ALTER FUNCTION fa_owner.enroll(bigint,uuid) OWNER TO postgres")
                        old_revision=c.execute("SELECT fa_owner.enroll(%s,%s)",before[:2]).fetchone()[0]
                        c.execute("ALTER FUNCTION fa_owner.enroll(bigint,uuid) OWNER TO " + OWNER)
                        transfer_tables(c)
                        self.assertEqual(c.execute("SELECT state,version FROM inventory_importpreparationrevision "
                            "WHERE id=%s",(old_revision,)).fetchone(),("CAPTURED",1))
                    batch, profile, _ = fixture(c, owner=True)
                with connect(db, True) as r:
                    revision = r.execute("SELECT fa_owner.enroll(%s,%s)",(batch,profile)).fetchone()[0]
                with connect(db) as c:
                    self.assertEqual(c.execute("SELECT state,version FROM public.inventory_importpreparationrevision "
                        "WHERE id=%s",(revision,)).fetchone(),("CAPTURED",1))
                    self.assertEqual(c.execute("SELECT count(*) FROM public.inventory_importrevisionparticipant "
                        "WHERE revision_id=%s",(revision,)).fetchone()[0],1)
                    self.assertEqual(c.execute("SELECT count(*) FROM public.inventory_importreviewevent "
                        "WHERE revision_id=%s AND kind='CAPTURE'",(revision,)).fetchone()[0],1)
                    self.assertEqual(c.execute("SELECT count(*) FROM public.transactions_stockmovement").fetchone()[0],0)

    def test_function_owner_without_table_ownership_fails(self):
        db = clone("nonowner")
        with connect(db) as c:
            b,p,_ = fixture(c)
            owner_setup(c, False)
            for t in TABLES:
                c.execute(sql.SQL("GRANT SELECT,INSERT,UPDATE ON public.{} TO {}").format(
                    sql.Identifier(t),sql.Identifier(OWNER)))
            c.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO " + OWNER)
        with connect(db, True) as r:
            with self.assertRaisesRegex(psycopg.Error,"REVIEW_CAPTURE_SERVICE_DISABLED"):
                r.execute("SELECT fa_owner.enroll(%s,%s)",(b,p))
        with connect(db) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM inventory_importpreparationrevision").fetchone()[0],0)

    def test_catalog_owners_sequences_and_flags(self):
        with connect(self.db) as c:
            rows = c.execute("SELECT relname,relkind,pg_get_userbyid(relowner),relacl::text "
                "FROM pg_class WHERE relnamespace='public'::regnamespace "
                "AND relname LIKE 'inventory_import%' ORDER BY relname").fetchall()
            EVIDENCE["catalog_after"] = rows
            for name,kind,owner,acl in rows:
                if kind in ("r","S"):
                    self.assertEqual(owner,OWNER,(name,kind,acl))
            self.assertFalse(c.execute("SELECT rolcanlogin OR rolsuper OR rolcreaterole OR rolcreatedb "
                "OR rolbypassrls OR rolinherit FROM pg_roles WHERE rolname=%s",(OWNER,)).fetchone()[0])
            self.assertFalse(c.execute("SELECT pg_has_role(%s,%s,'MEMBER')",(RUNTIME,OWNER)).fetchone()[0])
            self.assertEqual(c.execute("SELECT proconfig FROM pg_proc WHERE oid="
                "'fa_owner.enroll(bigint,uuid)'::regprocedure").fetchone()[0],
                ["search_path=pg_catalog, pg_temp"])

    def test_runtime_privilege_denials(self):
        denied = ["SET ROLE " + OWNER,
            "SELECT * FROM public.inventory_importstagingrecord",
            "INSERT INTO public.inventory_importbatch DEFAULT VALUES",
            "TRUNCATE public.inventory_importpreparationrevision CASCADE",
            "ALTER TABLE public.inventory_importreviewevent DISABLE TRIGGER ALL",
            "SELECT nextval('public.inventory_importreviewevent_id_seq')",
            "SELECT public.itw_review_assert(gen_random_uuid())",
            "CREATE TABLE fa_owner.evil(id int)", "CREATE SCHEMA evil",
            "SET session_replication_role=replica",
            "INSERT INTO public.inventory_asset DEFAULT VALUES",
            "INSERT INTO public.inventory_stockbalance DEFAULT VALUES",
            "INSERT INTO public.transactions_stockmovement DEFAULT VALUES",
            "INSERT INTO public.transactions_stockoperation DEFAULT VALUES"]
        with connect(self.db,True) as r:
            for query in denied:
                with self.subTest(query=query), self.assertRaises(psycopg.Error):
                    r.execute(query)

    def test_accidental_dml_does_not_bypass_guard(self):
        with connect(self.db) as c:
            with c.transaction():
                c.execute("GRANT INSERT ON public.inventory_importrevisionparticipant TO " + RUNTIME)
                c.execute("GRANT USAGE ON SEQUENCE public.inventory_importrevisionparticipant_id_seq TO " + RUNTIME)
                # Grant must be visible to a separate actual LOGIN.
            try:
                with connect(self.db,True) as r:
                    with self.assertRaisesRegex(psycopg.Error,"REVIEW_SERVICE_DISABLED"):
                        r.execute("INSERT INTO public.inventory_importrevisionparticipant "
                            "(revision_id,user_id) VALUES(%s,1)",(uuid.uuid4(),))
            finally:
                c.execute("REVOKE INSERT ON public.inventory_importrevisionparticipant FROM " + RUNTIME)
                c.execute("REVOKE USAGE ON SEQUENCE public.inventory_importrevisionparticipant_id_seq FROM " + RUNTIME)

    def test_legacy_owner_bootstrap_breaks_and_acl_rollback(self):
        with connect(self.db) as c:
            # Previous nonsuperuser migration owner no longer passes current_user=relowner,
            # even if explicitly granted INSERT. Superuser postgres is not such a role.
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=\'itw_fa_old_owner\'").fetchone():
                c.execute("CREATE ROLE itw_fa_old_owner NOLOGIN")
            c.execute("GRANT USAGE ON SCHEMA public TO itw_fa_old_owner")
            c.execute("GRANT INSERT ON public.inventory_importsourceprofile TO itw_fa_old_owner")
            with self.assertRaisesRegex(psycopg.Error,"REVIEW_PROFILE_REGISTRATION_DISABLED"):
                with c.transaction():
                    c.execute("SET LOCAL ROLE itw_fa_old_owner")
                    c.execute("INSERT INTO public.inventory_importsourceprofile "
                        "(id,code,version,workbook_sha256,layout_digest,expected_counts,canonical_bytes,"
                        "digest,definition_verified,registered_by) VALUES(%s,'SYN',1,%s,%s,'{}','x',%s,false,'')",
                        (uuid.uuid4(),"a"*64,"b"*64,"c"*64))
            before=c.execute("SELECT relowner FROM pg_class WHERE oid='inventory_importbatch'::regclass").fetchone()
            with self.assertRaisesRegex(RuntimeError,"INJECTED"):
                with c.transaction():
                    c.execute("ALTER TABLE public.inventory_importbatch OWNER TO postgres")
                    raise RuntimeError("INJECTED")
            self.assertEqual(c.execute("SELECT relowner FROM pg_class WHERE oid='inventory_importbatch'::regclass").fetchone(),before)
            c.execute("REVOKE EXECUTE ON FUNCTION fa_owner.enroll(bigint,uuid) FROM " + RUNTIME)
            try:
                with connect(self.db,True) as r, self.assertRaises(psycopg.Error):
                    r.execute("SELECT fa_owner.enroll(1,%s)",(uuid.uuid4(),))
            finally:
                c.execute("GRANT EXECUTE ON FUNCTION fa_owner.enroll(bigint,uuid) TO " + RUNTIME)


AUTH_QUERY = """SELECT u.is_active AND EXISTS(
 SELECT 1 FROM auth_permission p JOIN django_content_type t ON t.id=p.content_type_id
 WHERE t.app_label='inventory' AND t.model='importbatch' AND p.codename='capture_import'
 AND (EXISTS(SELECT 1 FROM auth_user_user_permissions d WHERE d.user_id=u.id AND d.permission_id=p.id)
 OR EXISTS(SELECT 1 FROM auth_user_groups g JOIN auth_group_permissions gp ON gp.group_id=g.group_id
 WHERE g.user_id=u.id AND gp.permission_id=p.id))) FROM auth_user u WHERE u.id=%s"""


class AuthLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = clone("auth")
        with connect(cls.db) as c:
            c.execute("CREATE SCHEMA fa_auth")
            c.execute("""CREATE FUNCTION fa_auth.lock() RETURNS trigger LANGUAGE plpgsql
                SET search_path=pg_catalog,pg_temp AS $$
                BEGIN PERFORM pg_catalog.pg_advisory_xact_lock(73921,2); RETURN NULL; END $$""")
            for table in ("auth_user","auth_user_user_permissions","auth_user_groups",
                          "auth_group_permissions","auth_permission","auth_group","django_content_type"):
                c.execute(sql.SQL("CREATE TRIGGER fa_lock BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE "
                    "ON public.{} FOR EACH STATEMENT EXECUTE FUNCTION fa_auth.lock()").format(sql.Identifier(table)))

    def seed(self, group=False):
        with connect(self.db) as c:
            _,_,actor=fixture(c)
            if group:
                c.execute("DELETE FROM auth_user_user_permissions WHERE user_id=%s",(actor,))
                g=c.execute("INSERT INTO auth_group(name) VALUES(%s) RETURNING id",(uuid.uuid4().hex,)).fetchone()[0]
                c.execute("INSERT INTO auth_user_groups(user_id,group_id) VALUES(%s,%s)",(actor,g))
                c.execute("INSERT INTO auth_group_permissions(group_id,permission_id) SELECT %s,p.id "
                    "FROM auth_permission p JOIN django_content_type t ON t.id=p.content_type_id "
                    "WHERE t.app_label='inventory' AND t.model='importbatch' AND p.codename='capture_import'",(g,))
                return actor,g
            return actor,None

    def race(self, mutation, group=False, capture_first=False):
        actor,g=self.seed(group)
        with connect(self.db) as holder, connect(self.db) as waiter:
            with holder.transaction():
                lock(holder)
                if not capture_first:
                    holder.execute(mutation,(g or actor,))
                else:
                    self.assertTrue(holder.execute(AUTH_QUERY,(actor,)).fetchone()[0])
                pid=waiter.info.backend_pid
                def run():
                    with waiter.transaction():
                        waiter.execute("SET LOCAL lock_timeout='3s'")
                        if capture_first:
                            # Ordinary DML trigger takes the advisory lock before row mutation.
                            waiter.execute(mutation,(g or actor,))
                            return "revoked"
                        lock(waiter)
                        return waiter.execute(AUTH_QUERY,(actor,)).fetchone()[0]
                pool=ThreadPoolExecutor(max_workers=1)
                future=pool.submit(run)
                wait_for_lock(holder,pid)
                self.assertFalse(future.done())
            try:
                self.assertEqual(future.result(5),"revoked" if capture_first else False)
            finally:
                pool.shutdown(wait=True)
            self.assertFalse(holder.execute(AUTH_QUERY,(actor,)).fetchone()[0])

    def test_deactivation_before_capture(self):
        self.race("UPDATE auth_user SET is_active=false WHERE id=%s")

    def test_direct_revoke_before_capture(self):
        self.race("DELETE FROM auth_user_user_permissions WHERE user_id=%s")

    def test_group_membership_removal_before_capture(self):
        self.race("DELETE FROM auth_user_groups WHERE group_id=%s",True)

    def test_group_permission_removal_before_capture(self):
        self.race("DELETE FROM auth_group_permissions WHERE group_id=%s",True)

    def test_capture_before_authority_changes(self):
        for statement,group in [
            ("UPDATE auth_user SET is_active=false WHERE id=%s",False),
            ("DELETE FROM auth_user_user_permissions WHERE user_id=%s",False),
            ("DELETE FROM auth_user_groups WHERE group_id=%s",True),
            ("DELETE FROM auth_group_permissions WHERE group_id=%s",True)]:
            with self.subTest(statement=statement):
                self.race(statement,group,capture_first=True)

    def test_bounded_timeout_and_no_partial_mutation(self):
        actor,_=self.seed()
        with connect(self.db) as h, connect(self.db) as w:
            with h.transaction():
                lock(h)
                def run():
                    with w.transaction():
                        w.execute("SET LOCAL lock_timeout='250ms'")
                        w.execute("UPDATE auth_user SET is_active=false WHERE id=%s",(actor,))
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future=pool.submit(run)
                    wait_for_lock(h,w.info.backend_pid)
                    with self.assertRaises(psycopg.errors.LockNotAvailable):
                        future.result(3)
            self.assertTrue(h.execute(AUTH_QUERY,(actor,)).fetchone()[0])