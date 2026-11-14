"""Synthetic hardening regressions; no real source data."""
import hashlib
import json
import uuid
from django.db import connection, transaction
from django.test import TestCase

from apps.inventory import test_review_schema as fixtures
from apps.inventory.models import ImportPreviewSnapshot as Snapshot
from apps.inventory.staging.common import canonical


class HardeningRegressionTests(TestCase):
    setUpTestData = classmethod(fixtures.ReviewSchemaTests.setUpTestData.__func__)
    profile_for = fixtures.ReviewSchemaTests.profile_for
    create_revision = fixtures.ReviewSchemaTests.create_revision
    constraints = fixtures.ReviewSchemaTests.constraints
    event = fixtures.ReviewSchemaTests.event
    batch = fixtures.ReviewSchemaTests.batch
    captured = fixtures.ReviewSchemaTests.captured
    advance = fixtures.ReviewSchemaTests.advance
    structural_payload = fixtures.ReviewSchemaTests.structural_payload
    denied = fixtures.ReviewSchemaTests.denied

    def rejected_snapshot(self, mutate, code=None):
        r, _ = self.captured()
        with transaction.atomic():
            self.advance(r, "PREPARING", "START")
            self.constraints()
        def attempt():
            payload = self.structural_payload(r)
            mutate(payload)
            self.advance(r, "PREPARING", "EDIT", payload=payload)
            r.state = "READY_FOR_REVIEW"
            r.version += 1
            r.save(update_fields=["state", "version"])
            data = canonical(payload)
            snapshot = Snapshot.objects.create(revision=r, canonical_bytes=data,
                                               digest=hashlib.sha256(data).hexdigest())
            self.event(r, "SUBMIT", "PREPARING", snapshot=snapshot)
        self.denied(attempt, code)

    def test_source_identity_requires_integer_row_number(self):
        self.rejected_snapshot(lambda p: p["source_rows"][0].update(excel_row_number="2"))

    def test_excluded_scope_requires_excluded_label(self):
        self.rejected_snapshot(lambda p: p["candidate_decisions"][0].update(
            scope="EXCLUDED", label="NEEDS_CLARIFICATION", reason_code="TEST"))


    def profile(self, **overrides):
        from apps.inventory.models import ImportSourceProfile
        values = {
            "code": "HARDENING-" + uuid.uuid4().hex[:12].upper(), "version": 1,
            "workbook_sha256": "a"*64, "layout_digest": "d"*64,
            "expected_counts": {"worksheets": 1, "populated": 1, "CANDIDATE": 1,
                                "HEADER": 0, "SEQUENCE_ONLY": 0},
            "definition_verified": True, "verification_evidence_digest": "1"*64,
        }
        values.update(overrides)
        definition = {k: values[k] for k in
                      ("code", "version", "workbook_sha256", "layout_digest", "expected_counts")}
        definition["domain"] = "itw.source-profile.v1"
        data = canonical(definition)
        values.update(canonical_bytes=data, digest=hashlib.sha256(data).hexdigest())
        return ImportSourceProfile.objects.create(**values)

    def raw_revision(self, batch, profile):
        from apps.inventory.models import ImportPreparationRevision
        return ImportPreparationRevision.objects.create(
            batch=batch, source_profile=profile, revision_number=1, created_by=self.preparer,
            layout_digest="d"*64, manifest_digest="e"*64,
            capture_storage_key="private/synthetic", capture_artifact_digest="f"*64)

    def test_missing_profile_is_rejected(self):
        b, _ = self.batch()
        self.denied(lambda: self.raw_revision(b, None), "REVIEW_PROFILE_REQUIRED")

    def test_unverified_profile_is_rejected(self):
        b, _ = self.batch()
        p = self.profile(definition_verified=False, verification_evidence_digest=None)
        self.denied(lambda: self.raw_revision(b, p), "REVIEW_PROFILE_UNVERIFIED")

    def test_profile_workbook_and_layout_binding(self):
        b, _ = self.batch()
        for p in (self.profile(workbook_sha256="9"*64), self.profile(layout_digest="8"*64)):
            self.denied(lambda: self.raw_revision(b, p), "REVIEW_PROFILE_BINDING_INVALID")

    def test_bad_profile_counts_cannot_be_registered(self):
        invalid = [
            {"worksheets": 1, "populated": 1, "CANDIDATE": "1", "HEADER": 0, "SEQUENCE_ONLY": 0},
            {"worksheets": 1, "populated": 2, "CANDIDATE": 1, "HEADER": 0, "SEQUENCE_ONLY": 0},
            {"worksheets": 0, "populated": 1, "CANDIDATE": 1, "HEADER": 0, "SEQUENCE_ONLY": 0},
            {"worksheets": 1, "populated": 1, "CANDIDATE": 1, "HEADER": 0},
        ]
        for counts in invalid:
            self.denied(lambda: self.profile(expected_counts=counts), "REVIEW_PROFILE_COUNTS_INVALID")

    def test_exact_profile_counts_apply_to_every_hash(self):
        b, _ = self.batch()
        p = self.profile(expected_counts={
            "worksheets": 1, "populated": 2, "CANDIDATE": 2, "HEADER": 0, "SEQUENCE_ONLY": 0})
        self.denied(lambda: self.raw_revision(b, p), "REVIEW_PROFILE_COUNTS_INVALID")

    def test_profile_is_append_only_even_for_owner(self):
        from apps.inventory.models import ImportSourceProfile
        p = self.profile()
        self.denied(lambda: ImportSourceProfile.objects.filter(pk=p.pk).update(
            expected_counts={"forged": 1}), "REVIEW_PROFILE_IMMUTABLE")
        def raw_delete():
            with connection.cursor() as c:
                c.execute("DELETE FROM inventory_importsourceprofile WHERE id=%s", [p.pk])
        self.denied(raw_delete, "REVIEW_PROFILE_IMMUTABLE")

    def test_profile_version_cannot_be_replaced(self):
        p = self.profile()
        self.denied(lambda: self.profile(code=p.code, version=p.version))

    def test_bound_revision_cannot_switch_profiles(self):
        from apps.inventory.models import ImportPreparationRevision
        r, _ = self.captured()
        alternative = self.profile(version=2)
        self.denied(lambda: ImportPreparationRevision.objects.filter(pk=r.pk).update(
            source_profile=alternative, version=r.version+1, state="PREPARING"),
            "REVIEW_IDENTITY_IMMUTABLE")

    def test_profile_definition_digest_and_contract(self):
        from apps.inventory.models import ImportSourceProfile
        p = self.profile()
        values = {field.name: getattr(p, field.name) for field in ImportSourceProfile._meta.fields
                  if field.name not in ("id", "created_at")}
        values.update(code="NEW-PROFILE", canonical_bytes=b"{}")
        self.denied(lambda: ImportSourceProfile.objects.create(**values),
                    "REVIEW_PROFILE_DIGEST_INVALID")
        data = canonical({"domain": "unsupported"})
        values.update(canonical_bytes=data, digest=hashlib.sha256(data).hexdigest())
        self.denied(lambda: ImportSourceProfile.objects.create(**values),
                    "REVIEW_PROFILE_UNSUPPORTED")

    def test_profile_cannot_claim_a_client_registration_identity(self):
        p = self.profile(registered_by="client-forged")
        p.refresh_from_db()
        with connection.cursor() as c:
            c.execute("SELECT current_user")
            self.assertEqual(p.registered_by, c.fetchone()[0])
        self.assertNotEqual(p.registered_by, "client-forged")

    def test_nonowner_registration_stays_disabled_even_with_dml_grants(self):
        from apps.inventory.models import ImportPreparationRevision, ImportSourceProfile
        b, _ = self.batch()
        p = self.profile_for(b)
        with connection.cursor() as c:
            c.execute("CREATE ROLE hardening_capture_runtime NOLOGIN NOSUPERUSER NOCREATEDB "
                      "NOCREATEROLE NOINHERIT NOBYPASSRLS")
            c.execute("GRANT USAGE ON SCHEMA public TO hardening_capture_runtime")
            c.execute("GRANT SELECT,UPDATE ON inventory_importbatch TO hardening_capture_runtime")
            c.execute("GRANT SELECT,INSERT ON inventory_importpreparationrevision,"
                      "inventory_importsourceprofile TO hardening_capture_runtime")
        def attempt():
            with connection.cursor() as c:
                c.execute("SET LOCAL ROLE hardening_capture_runtime")
            self.raw_revision(b, p)
        self.denied(attempt, "REVIEW_CAPTURE_SERVICE_DISABLED")
        def profile_attempt():
            with connection.cursor() as c:
                c.execute("SET LOCAL ROLE hardening_capture_runtime")
            self.profile()
        self.denied(profile_attempt, "REVIEW_PROFILE_REGISTRATION_DISABLED")

    def test_duplicate_source_rows_in_snapshot(self):
        self.rejected_snapshot(lambda p: p["source_rows"].append(dict(p["source_rows"][0])),
                               "REVIEW_SOURCE_RECONCILIATION_INVALID")

    def test_duplicate_candidates_in_snapshot(self):
        self.rejected_snapshot(lambda p: p["candidate_decisions"].append(
            dict(p["candidate_decisions"][0])), "REVIEW_DECISIONS_INVALID")

    def test_incomplete_candidate_manifest(self):
        self.rejected_snapshot(lambda p: p["candidate_decisions"].clear(), "REVIEW_DECISIONS_INVALID")

    def test_snapshot_binds_profile_and_all_source_digests(self):
        for key in ("workbook_sha256", "manifest_digest", "layout_digest", "source_profile_digest"):
            self.rejected_snapshot(lambda p: p.update({key: "9"*64}),
                                   "REVIEW_SNAPSHOT_CONTENT_INVALID")

    def test_candidate_row_number_must_be_numeric(self):
        self.rejected_snapshot(lambda p: p["candidate_decisions"][0].update(excel_row_number="2"),
                               "REVIEW_SNAPSHOT_ENTRY_INVALID")

    def test_exclusion_reason_must_be_text(self):
        self.rejected_snapshot(lambda p: p["candidate_decisions"][0].update(
            scope="EXCLUDED", label="EXCLUDED_WITH_REASON", reason_code=123),
            "REVIEW_DECISIONS_INVALID")

    def test_snapshot_invalid_utf8_is_sanitized(self):
        from apps.inventory.models import ImportPreviewSnapshot
        r, _ = self.captured()
        with transaction.atomic():
            self.advance(r, "PREPARING", "START")
            self.constraints()
        def attempt():
            r.state = "READY_FOR_REVIEW"
            r.version += 1
            r.save(update_fields=["state", "version"])
            data = b"\xff\xfe"
            ImportPreviewSnapshot.objects.create(
                revision=r, canonical_bytes=data, digest=hashlib.sha256(data).hexdigest())
        self.denied(attempt, "REVIEW_SNAPSHOT_JSON_INVALID")

    def test_snapshot_hash_is_of_exact_bytes_not_jsonb_spelling(self):
        from apps.inventory.models import ImportPreviewSnapshot
        r, _ = self.captured()
        with transaction.atomic():
            self.advance(r, "PREPARING", "START")
            payload = self.structural_payload(r)
            self.advance(r, "PREPARING", "EDIT", payload=payload)
            r.state = "READY_FOR_REVIEW"
            r.version += 1
            r.save(update_fields=["state", "version"])
            # Noncanonical whitespace is deliberately not certified by this schema.
            data = json.dumps(payload, indent=2).encode("utf-8")
            snapshot = ImportPreviewSnapshot.objects.create(
                revision=r, canonical_bytes=data, digest=hashlib.sha256(data).hexdigest())
            self.event(r, "SUBMIT", "PREPARING", snapshot=snapshot)
            self.constraints()
        self.assertNotEqual(snapshot.digest, hashlib.sha256(canonical(payload)).hexdigest())

    def test_rollback_removes_profile_and_source_capture_on_failure(self):
        from apps.inventory.models import ImportPreparationRevision, ImportSourceProfile
        before = (ImportSourceProfile.objects.count(), ImportPreparationRevision.objects.count())
        def attempt():
            b, _ = self.batch()
            self.raw_revision(b, self.profile())  # No CAPTURE event.
        self.denied(attempt, "REVIEW_EVENT_EVIDENCE_REQUIRED")
        self.assertEqual(before, (ImportSourceProfile.objects.count(), ImportPreparationRevision.objects.count()))

    def test_hardening_actions_have_no_stock_effects(self):
        from apps.inventory.models import Asset, StockBalance
        from apps.transactions.models import StockMovement, StockOperation
        models = (Asset, StockBalance, StockMovement, StockOperation)
        before = [list(model.objects.values()) for model in models]
        self.profile()
        self.captured()
        self.assertEqual(before, [list(model.objects.values()) for model in models])


    def test_least_privilege_role_catalog_and_denials(self):
        from django.db import DatabaseError
        with connection.cursor() as c:
            for role in ("hardening_review_runtime", "hardening_procedure_owner", "hardening_auth_admin"):
                c.execute("CREATE ROLE " + role + " NOLOGIN NOSUPERUSER NOCREATEDB "
                          "NOCREATEROLE NOINHERIT NOBYPASSRLS")
            c.execute("GRANT USAGE ON SCHEMA public TO hardening_review_runtime")
            c.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolbypassrls,rolcanlogin "
                      "FROM pg_roles WHERE rolname='hardening_review_runtime'")
            self.assertEqual(c.fetchone(), (False, False, False, False, False, False))
            for table in ("inventory_importsourceprofile", "inventory_importpreparationrevision",
                          "inventory_importrevisionparticipant", "inventory_importpreviewsnapshot",
                          "inventory_importreviewevent", "inventory_asset", "inventory_stockbalance",
                          "transactions_stockmovement", "transactions_stockoperation"):
                c.execute("SELECT has_table_privilege('hardening_review_runtime',%s,'INSERT,UPDATE,DELETE,TRUNCATE')",
                          [table])
                self.assertFalse(c.fetchone()[0])
            c.execute("SELECT has_sequence_privilege('hardening_review_runtime',"
                      "pg_get_serial_sequence('inventory_importreviewevent','id'),'USAGE,UPDATE')")
            self.assertFalse(c.fetchone()[0])
            c.execute("SELECT has_schema_privilege('hardening_review_runtime','public','CREATE')")
            self.assertFalse(c.fetchone()[0])
            c.execute("SELECT count(*) FROM pg_proc WHERE proname LIKE 'itw_review_%' "
                      "AND has_function_privilege('hardening_review_runtime',oid,'EXECUTE')")
            self.assertEqual(c.fetchone()[0], 0)
        for statement in (
            "DELETE FROM inventory_importreviewevent",
            "UPDATE inventory_importsourceprofile SET code='FORGED'",
            "TRUNCATE inventory_importpreviewsnapshot",
            "ALTER TABLE inventory_importreviewevent DISABLE TRIGGER ALL",
            "SELECT nextval(pg_get_serial_sequence('inventory_importreviewevent','id'))",
            "SELECT public.itw_review_check_profile(0,NULL,NULL)",
            "CREATE FUNCTION public.hardening_forbidden() RETURNS integer LANGUAGE sql AS 'SELECT 1'",
        ):
            with self.assertRaises(DatabaseError):
                with transaction.atomic(), connection.cursor() as c:
                    c.execute("SET LOCAL ROLE hardening_review_runtime")
                    c.execute(statement)



    def test_supplied_actor_cannot_authorize_nonowner_review_writes(self):
        from apps.inventory.models import ImportReviewEvent, ImportPreparationRevision
        r, _ = self.captured()
        with connection.cursor() as c:
            c.execute("CREATE ROLE hardening_writer_test NOLOGIN NOSUPERUSER NOCREATEDB "
                      "NOCREATEROLE NOINHERIT NOBYPASSRLS")
            c.execute("GRANT USAGE ON SCHEMA public TO hardening_writer_test")
            c.execute("GRANT SELECT,UPDATE ON inventory_importpreparationrevision,"
                      "inventory_importbatch TO hardening_writer_test")
            c.execute("GRANT SELECT,INSERT ON inventory_importreviewevent TO hardening_writer_test")
            c.execute("GRANT USAGE ON SEQUENCE inventory_importreviewevent_id_seq TO hardening_writer_test")
        def state_attempt():
            with connection.cursor() as c:
                c.execute("SET LOCAL ROLE hardening_writer_test")
            ImportPreparationRevision.objects.filter(pk=r.pk).update(
                state="PREPARING", version=2)
        self.denied(state_attempt, "REVIEW_SERVICE_DISABLED")
        def actor_attempt():
            with connection.cursor() as c:
                c.execute("SET LOCAL ROLE hardening_writer_test")
            ImportReviewEvent.objects.create(
                revision=r, sequence=2, request_id=uuid.uuid4(), request_fingerprint="c"*64,
                actor_id=self.preparer.pk, kind="START", from_state="CAPTURED",
                to_state="PREPARING", reason_code="SYNTHETIC", reason="Synthetic",
                details={"after_payload_digest": "c"*64})
        self.denied(actor_attempt, "REVIEW_SERVICE_DISABLED")

from concurrent.futures import ThreadPoolExecutor
from threading import Event as ThreadEvent
from time import monotonic, sleep
from django.db import DatabaseError, close_old_connections
from django.test import TransactionTestCase
from apps.inventory.models import ImportPreparationRevision as Revision, ImportStagingRecord, ImportReviewEvent


class HardeningConcurrencyTests(TransactionTestCase):
    constraints = fixtures.ReviewSchemaTests.constraints
    profile_for = fixtures.ReviewSchemaTests.profile_for
    create_revision = fixtures.ReviewSchemaTests.create_revision
    batch = fixtures.ReviewSchemaTests.batch
    event = fixtures.ReviewSchemaTests.event
    captured = fixtures.ReviewSchemaTests.captured

    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission
        self.preparer = get_user_model().objects.create_user(username="hardening-race")
        self.preparer.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="inventory", codename__in=["capture_import", "prepare_import"]))
        self.b, self.source = self.batch()
        self.profile_for(self.b)

    def race_order(self, first, second):
        held, started, release = ThreadEvent(), ThreadEvent(), ThreadEvent()
        second_pid = []

        def first_worker():
            close_old_connections()
            try:
                with transaction.atomic():
                    first()
                    held.set()
                    if not release.wait(10):
                        raise RuntimeError("Synthetic lock test timed out")
                return "COMMITTED"
            finally:
                close_old_connections()

        def second_worker():
            close_old_connections()
            try:
                with connection.cursor() as c:
                    c.execute("SELECT pg_backend_pid()")
                    second_pid.append(c.fetchone()[0])
                started.set()
                with transaction.atomic():
                    second()
                    self.constraints()
                return "COMMITTED"
            except DatabaseError:
                return "REJECTED"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(first_worker)
            try:
                self.assertTrue(held.wait(10))
                f2 = pool.submit(second_worker)
                self.assertTrue(started.wait(10))
                # Observe an actual advisory-lock waiter, rather than guessing by delay.
                waiting = False
                deadline = monotonic() + 5
                while monotonic() < deadline:
                    with connection.cursor() as c:
                        c.execute("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=%s "
                                  "AND locktype='advisory' AND classid=73921 AND objid=2 AND NOT granted)",
                                  [second_pid[0]])
                        waiting = c.fetchone()[0]
                    if waiting:
                        break
                    sleep(0.01)
                self.assertTrue(waiting)
            finally:
                release.set()
            return f1.result(timeout=10), f2.result(timeout=10)

    def test_registration_wins_then_source_modification_is_rejected(self):
        from apps.inventory.models import ImportBatch
        def register():
            self.captured(batch=ImportBatch.objects.get(pk=self.b.pk))
        def modify():
            ImportStagingRecord.objects.filter(pk=self.source.pk).update(raw_values=[])
        self.assertEqual(self.race_order(register, modify), ("COMMITTED", "REJECTED"))
        self.assertEqual(Revision.objects.count(), 1)
        self.source.refresh_from_db()
        self.assertNotEqual(self.source.raw_values, [])

    def test_profile_relevant_source_change_wins_registration_revalidates(self):
        from apps.inventory.models import ImportBatch
        def modify():
            ImportStagingRecord.objects.filter(pk=self.source.pk).update(
                normalized_values={"capture": {"classification": "HEADER"}})
        def register():
            self.captured(batch=ImportBatch.objects.get(pk=self.b.pk))
        self.assertEqual(self.race_order(modify, register), ("COMMITTED", "REJECTED"))
        self.assertEqual(Revision.objects.count(), 0)

    def test_concurrent_state_and_event_mutation_rejects_stale_version(self):
        r, _ = self.captured(batch=self.b)
        def start():
            item = Revision.objects.get(pk=r.pk)
            item.state = "PREPARING"
            item.version = 2
            item.save(update_fields=["state", "version"])
            self.event(item, "START", "CAPTURED")
            self.constraints()
        def stale_start():
            item = Revision.objects.get(pk=r.pk)
            item.state = "PREPARING"
            item.version = 2
            item.save(update_fields=["state", "version"])
            self.event(item, "START", "CAPTURED")
        self.assertEqual(self.race_order(start, stale_start), ("COMMITTED", "REJECTED"))
        self.assertEqual(ImportReviewEvent.objects.count(), 2)
        self.assertEqual(Revision.objects.get(pk=r.pk).version, 2)
