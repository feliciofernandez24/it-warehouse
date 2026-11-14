"""Synthetic review schema tests. No real workbook or development database."""
import copy
import hashlib
import json
import uuid
from importlib import import_module

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import DatabaseError, connection, transaction
from django.db.migrations.exceptions import IrreversibleError
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from apps.inventory.models import (
    ImportSourceProfile as SourceProfile, ImportBatch, ImportStagingRecord, ImportPreparationRevision as Revision,
    ImportRevisionParticipant as Participant, ImportPreviewSnapshot as Snapshot,
    ImportReviewEvent as Event, Asset, StockBalance,
)
from apps.inventory.staging.common import canonical
from apps.transactions.models import StockMovement, StockOperation


class ReviewSchemaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.preparer = get_user_model().objects.create_user(username="synthetic-preparer")
        cls.reviewer = get_user_model().objects.create_user(username="synthetic-reviewer")
        cls.editor = get_user_model().objects.create_user(username="synthetic-editor")
        cls.no_grants = get_user_model().objects.create_user(username="synthetic-no-grants", is_superuser=True)
        cls.inactive = get_user_model().objects.create_user(username="synthetic-inactive", is_active=False)
        permissions = Permission.objects.filter(content_type__app_label="inventory",
            codename__in=["capture_import", "prepare_import", "review_import",
                          "view_import_evidence", "approve_import"])
        for user in (cls.preparer, cls.reviewer, cls.editor, cls.inactive):
            user.user_permissions.add(*permissions)

    def constraints(self):
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("SET CONSTRAINTS ALL DEFERRED")

    def batch(self, *, uploader=None):
        b = ImportBatch.objects.create(
            original_filename="synthetic.xlsx", file_sha256="a" * 64,
            source_storage_key="private/synthetic", uploaded_by=uploader or self.preparer,
            mapping_version="synthetic-v1",
        )
        source = ImportStagingRecord.objects.create(
            batch=b, worksheet_name="Synthetic", excel_row_number=2,
            raw_values=[{"coordinate": "A2", "value": "SYNTHETIC"}],
            normalized_values={"capture": {"classification": "CANDIDATE"}},
            source_row_digest="b" * 64,
        )
        return b, source


    def profile_for(self, batch):
        batch.refresh_from_db(fields=["file_sha256"])
        counts = {"worksheets": 1, "populated": 1, "CANDIDATE": 1, "HEADER": 0, "SEQUENCE_ONLY": 0}
        if batch.file_sha256 == "d0c48893cc095696ada206fb4d61d80c2745d412b289e0ab754dc5bd023bc525":
            counts = {"worksheets": 15, "populated": 920, "CANDIDATE": 897,
                      "HEADER": 21, "SEQUENCE_ONLY": 2}
        code = "SYN-" + batch.file_sha256[:12].upper()
        definition = {"domain": "itw.source-profile.v1", "code": code, "version": 1,
                      "workbook_sha256": batch.file_sha256, "layout_digest": "d"*64,
                      "expected_counts": counts}
        data = canonical(definition)
        profile, _ = SourceProfile.objects.get_or_create(
            code=code, version=1, defaults={
                "workbook_sha256": batch.file_sha256, "layout_digest": "d"*64,
                "expected_counts": counts, "canonical_bytes": data,
                "digest": hashlib.sha256(data).hexdigest(), "definition_verified": True,
                "verification_evidence_digest": "1"*64,
            })
        return profile

    def create_revision(self, **kwargs):
        kwargs.setdefault("source_profile", self.profile_for(kwargs["batch"]))
        return Revision.objects.create(**kwargs)


    def event(self, r, kind, previous, *, actor=None, snapshot=None, source=None, sequence=None):
        with connection.cursor() as cursor:
            cursor.execute("SELECT encode(sha256(convert_to(draft_payload::text,'UTF8')),'hex') "
                           "FROM inventory_importpreparationrevision WHERE id=%s", [r.pk])
            payload_digest = cursor.fetchone()[0]
        return Event.objects.create(
            revision=r, sequence=sequence or r.version, request_id=uuid.uuid4(),
            request_fingerprint="c" * 64, actor=actor or self.preparer, kind=kind,
            from_state=previous, to_state=r.state, snapshot=snapshot, source_row=source,
            reason_code="SYNTHETIC_TEST", reason="Synthetic fixture",
            details={"after_payload_digest": payload_digest},
        )

    def captured(self, *, batch=None, creator=None, number=1, parent=None):
        if batch is None:
            batch, source = self.batch()
        else:
            source = batch.rows.first()
        creator = creator or self.preparer
        with transaction.atomic():
            r = self.create_revision(
                batch=batch, revision_number=number, parent=parent, created_by=creator,
                layout_digest="d" * 64, manifest_digest="e" * 64,
                capture_storage_key="private/synthetic-capture", capture_artifact_digest="f" * 64,
            )
            if parent:
                Participant.objects.bulk_create([
                    Participant(revision=r, user_id=u)
                    for u in parent.participants.values_list("user_id", flat=True)
                ])
            self.event(r, "CAPTURE", "CAPTURED", actor=creator)
            self.constraints()
        return r, source

    def advance(self, r, state, kind, *, actor=None, payload=None, snapshot=None):
        previous = r.state
        r.version += 1
        r.state = state
        fields = ["version", "state"]
        if payload is not None:
            r.draft_payload = payload
            fields.append("draft_payload")
        r.save(update_fields=fields)
        return self.event(r, kind, previous, actor=actor, snapshot=snapshot)

    def structural_payload(self, r):
        source_rows = [
            {"worksheet_name": s.worksheet_name, "excel_row_number": s.excel_row_number,
             "source_row_digest": s.source_row_digest,
             "classification": s.normalized_values["capture"]["classification"]}
            for s in r.batch.rows.all()
        ]
        return {
            "domain": "itw.import-preview.v1", "verification_status": "STRUCTURAL_ONLY",
            "workbook_sha256": r.batch.file_sha256, "source_profile_digest": r.source_profile.digest,
            "layout_digest": r.layout_digest,
            "manifest_digest": r.manifest_digest, "source_rows": source_rows,
            "candidate_decisions": [
                {**{k: value for k, value in s.items() if k != "classification"},
                 "label": "NEEDS_CLARIFICATION", "scope": "DEFERRED"}
                for s in source_rows if s["classification"] == "CANDIDATE"
            ],
        }

    def submitted(self):
        r, source = self.captured()
        with transaction.atomic():
            self.advance(r, "PREPARING", "START")
            self.advance(r, "PREPARING", "EDIT", payload=self.structural_payload(r))
            r.version += 1
            r.state = "READY_FOR_REVIEW"
            r.save(update_fields=["state", "version"])
            data = canonical(r.draft_payload)
            snapshot = Snapshot.objects.create(revision=r, canonical_bytes=data,
                                               digest=hashlib.sha256(data).hexdigest())
            self.event(r, "SUBMIT", "PREPARING", snapshot=snapshot)
            self.constraints()
        return r, source, snapshot

    def denied(self, action, code=None):
        with self.assertRaises(DatabaseError) as error:
            with transaction.atomic():
                action()
                self.constraints()
        if code:
            self.assertIn(code, str(error.exception))

    def test_initial_capture_version_event_and_actor_enrollment(self):
        r, source = self.captured()
        self.assertEqual(r.version, 1)
        self.assertEqual(r.state, "CAPTURED")
        self.assertEqual(list(r.review_events.values_list("sequence", "kind")), [(1, "CAPTURE")])
        self.assertEqual(list(r.participants.values_list("user_id", flat=True)), [self.preparer.pk])

    def test_capture_without_event_fails_at_deferred_check(self):
        b, _ = self.batch()
        self.denied(lambda: self.create_revision(
            batch=b, revision_number=1, created_by=self.preparer, layout_digest="d"*64,
            manifest_digest="e"*64, capture_storage_key="private/test", capture_artifact_digest="f"*64),
            "REVIEW_EVENT_EVIDENCE_REQUIRED")

    def test_duplicate_active_revision_rejected(self):
        r, _ = self.captured()
        self.denied(lambda: self.create_revision(
            batch=r.batch, revision_number=2, parent=r, created_by=self.preparer,
            layout_digest="d"*64, manifest_digest="e"*64,
            capture_storage_key=r.capture_storage_key, capture_artifact_digest="f"*64))

    def test_wrong_parent_batch_is_rejected(self):
        r, _ = self.captured()
        other, _ = self.captured()
        def attempt():
            self.advance(r, "SUPERSEDED", "SUPERSEDE")
            self.create_revision(
                batch=r.batch, revision_number=2, parent=other, created_by=self.preparer,
                layout_digest="d"*64, manifest_digest="e"*64,
                capture_storage_key=r.capture_storage_key, capture_artifact_digest="f"*64)
        self.denied(attempt, "REVIEW_PARENT_INVALID")

    def test_revision_numbers_cannot_skip(self):
        b, _ = self.batch()
        self.denied(lambda: self.create_revision(
            batch=b, revision_number=3, created_by=self.preparer,
            layout_digest="d"*64, manifest_digest="e"*64,
            capture_storage_key="private/test", capture_artifact_digest="f"*64),
            "REVIEW_REVISION_NUMBER_INVALID")

    def test_successor_carries_participant_history(self):
        r, _ = self.captured()
        with transaction.atomic():
            self.advance(r, "PREPARING", "START", actor=self.editor)
            self.advance(r, "SUPERSEDED", "SUPERSEDE")
            next_r, _ = self.captured(batch=r.batch, creator=self.reviewer, number=2, parent=r)
            self.constraints()
        self.assertEqual(set(next_r.participants.values_list("user_id", flat=True)),
                         {self.preparer.pk, self.editor.pk, self.reviewer.pk})

    def test_missing_inherited_participant_fails(self):
        r, _ = self.captured()
        def attempt():
            self.advance(r, "SUPERSEDED", "SUPERSEDE")
            next_r = self.create_revision(
                batch=r.batch, revision_number=2, parent=r, created_by=self.editor,
                layout_digest=r.layout_digest, manifest_digest=r.manifest_digest,
                capture_storage_key=r.capture_storage_key, capture_artifact_digest=r.capture_artifact_digest)
            self.event(next_r, "CAPTURE", "CAPTURED", actor=self.editor)
        self.denied(attempt, "REVIEW_PARTICIPANT_EVIDENCE_REQUIRED")

    def test_supersession_requires_successor(self):
        r, _ = self.captured()
        self.denied(lambda: self.advance(r, "SUPERSEDED", "SUPERSEDE"), "REVIEW_SUCCESSOR_REQUIRED")

    def test_direct_state_change_without_event_sql(self):
        r, _ = self.captured()
        def attempt():
            with connection.cursor() as c:
                c.execute("UPDATE inventory_importpreparationrevision SET state='PREPARING',"
                          "version=version+1 WHERE id=%s", [r.pk])
        self.denied(attempt, "REVIEW_EVENT_EVIDENCE_REQUIRED")
        r.refresh_from_db()
        self.assertEqual(r.state, "CAPTURED")

    def test_version_cannot_skip(self):
        r, _ = self.captured()
        self.denied(lambda: Revision.objects.filter(pk=r.pk).update(version=8), "REVIEW_VERSION_INVALID")

    def test_event_sequence_cannot_advance_revision(self):
        r, _ = self.captured()
        self.denied(lambda: self.event(r, "START", "CAPTURED", sequence=2),
                    "REVIEW_EVENT_VERSION_INVALID")

    def test_wrong_event_kind_cannot_attest_transition(self):
        r, _ = self.captured()
        self.denied(lambda: self.advance(r, "PREPARING", "EDIT"),
                    "REVIEW_EVENT_TRANSITION_INVALID")

    def test_payload_update_needs_matching_digest(self):
        r, _ = self.captured()
        with transaction.atomic():
            self.advance(r, "PREPARING", "START")
            self.constraints()
        def attempt():
            Revision.objects.filter(pk=r.pk).update(version=r.version+1, draft_payload={"synthetic": True})
            r.refresh_from_db()
            Event.objects.create(
                revision=r, sequence=r.version, request_id=uuid.uuid4(), request_fingerprint="c"*64,
                actor=self.preparer, kind="EDIT", from_state="PREPARING", to_state="PREPARING",
                reason_code="TEST", reason="Synthetic", details={"after_payload_digest": "0"*64})
        self.denied(attempt, "REVIEW_EVENT_PAYLOAD_INVALID")

    def test_snapshot_valid_hash_and_structural_submission(self):
        r, source, snapshot = self.submitted()
        self.assertEqual(hashlib.sha256(bytes(snapshot.canonical_bytes)).hexdigest(), snapshot.digest)
        self.assertEqual(snapshot.revision_id, r.pk)
        self.assertEqual(r.review_events.filter(kind="SUBMIT").count(), 1)

    def test_snapshot_cannot_be_updated_orm_or_sql(self):
        _, _, snapshot = self.submitted()
        self.denied(lambda: Snapshot.objects.filter(pk=snapshot.pk).update(canonical_bytes=b"tampered"),
                    "REVIEW_SNAPSHOT_IMMUTABLE")
        def raw():
            with connection.cursor() as c:
                c.execute("UPDATE inventory_importpreviewsnapshot SET digest=%s WHERE id=%s",
                          ["0"*64, snapshot.pk])
        self.denied(raw, "REVIEW_SNAPSHOT_IMMUTABLE")

    def test_snapshot_cannot_be_deleted(self):
        _, _, snapshot = self.submitted()
        def raw():
            with connection.cursor() as c:
                c.execute("DELETE FROM inventory_importpreviewsnapshot WHERE id=%s", [snapshot.pk])
        self.denied(raw, "REVIEW_SNAPSHOT_IMMUTABLE")
        with self.assertRaises(ProtectedError):
            snapshot.delete()

    def test_snapshot_one_to_one_and_wrong_digest(self):
        r, _, snapshot = self.submitted()
        self.denied(lambda: Snapshot.objects.create(
            revision=r, canonical_bytes=snapshot.canonical_bytes, digest="0"*64),
            "REVIEW_SNAPSHOT_DIGEST_INVALID")
        self.denied(lambda: Snapshot.objects.create(
            revision=r, canonical_bytes=snapshot.canonical_bytes, digest=snapshot.digest))

    def test_ready_without_snapshot_is_rejected(self):
        r, _ = self.captured()
        with transaction.atomic():
            self.advance(r, "PREPARING", "START")
            self.constraints()
        def attempt():
            r.state = "READY_FOR_REVIEW"
            r.version += 1
            r.save(update_fields=["state", "version"])
        self.denied(attempt, "REVIEW_EVENT_EVIDENCE_REQUIRED")

    def test_incomplete_snapshot_source_rows_rejected(self):
        r, _ = self.captured()
        with transaction.atomic():
            self.advance(r, "PREPARING", "START")
            self.constraints()
        def attempt():
            payload = self.structural_payload(r)
            payload["source_rows"] = []
            self.advance(r, "PREPARING", "EDIT", payload=payload)
            r.state = "READY_FOR_REVIEW"
            r.version += 1
            r.save(update_fields=["state", "version"])
            data = canonical(payload)
            Snapshot.objects.create(revision=r, canonical_bytes=data, digest=hashlib.sha256(data).hexdigest())
        self.denied(attempt, "REVIEW_SOURCE_RECONCILIATION_INVALID")

    def test_event_cannot_be_changed_or_deleted_sql_and_orm(self):
        r, _ = self.captured()
        event = r.review_events.get()
        self.denied(lambda: Event.objects.filter(pk=event.pk).update(reason="Changed"),
                    "REVIEW_HISTORY_IMMUTABLE")
        self.denied(lambda: Event.objects.filter(pk=event.pk).delete(), "REVIEW_HISTORY_IMMUTABLE")
        def raw():
            with connection.cursor() as c:
                c.execute("UPDATE inventory_importreviewevent SET reason='changed' WHERE id=%s", [event.pk])
        self.denied(raw, "REVIEW_HISTORY_IMMUTABLE")
        def raw_delete():
            with connection.cursor() as c:
                c.execute("DELETE FROM inventory_importreviewevent WHERE id=%s", [event.pk])
        self.denied(raw_delete, "REVIEW_HISTORY_IMMUTABLE")

    def test_event_source_ownership(self):
        r, _ = self.captured()
        _, other_source = self.batch()
        self.denied(lambda: self._source_attempt(r, other_source),
                    "REVIEW_SOURCE_OWNER_INVALID")

    def _source_attempt(self, r, source):
        r.state = "PREPARING"
        r.version += 1
        r.save(update_fields=["state", "version"])
        self.event(r, "START", "CAPTURED", source=source)

    def test_snapshot_event_ownership(self):
        other, _, other_snapshot = self.submitted()
        r, _, _ = self.submitted()
        self.denied(lambda: self.advance(r, "READY_FOR_REVIEW", "REVIEW_ACCEPT",
                                        actor=self.reviewer, snapshot=other_snapshot),
                    "REVIEW_SNAPSHOT_OWNER_INVALID")

    def test_uploader_cannot_review(self):
        r, _, snapshot = self.submitted()
        self.denied(lambda: self.advance(r, "READY_FOR_REVIEW", "REVIEW_ACCEPT",
                                        actor=self.preparer, snapshot=snapshot),
                    "REVIEW_ACTOR_NOT_INDEPENDENT")

    def test_editor_cannot_review(self):
        r, _ = self.captured()
        with transaction.atomic():
            self.advance(r, "PREPARING", "START", actor=self.editor)
            self.advance(r, "PREPARING", "EDIT", payload=self.structural_payload(r))
            r.state = "READY_FOR_REVIEW"
            r.version += 1
            r.save(update_fields=["state", "version"])
            data = canonical(r.draft_payload)
            s = Snapshot.objects.create(revision=r, canonical_bytes=data, digest=hashlib.sha256(data).hexdigest())
            self.event(r, "SUBMIT", "PREPARING", snapshot=s)
            self.constraints()
        self.denied(lambda: self.advance(r, "READY_FOR_REVIEW", "REVIEW_ACCEPT",
                                        actor=self.editor, snapshot=s), "REVIEW_ACTOR_NOT_INDEPENDENT")

    def test_independent_review_event_is_not_approval(self):
        r, _, snapshot = self.submitted()
        with transaction.atomic():
            self.advance(r, "READY_FOR_REVIEW", "REVIEW_ACCEPT", actor=self.reviewer, snapshot=snapshot)
            self.constraints()
        self.assertEqual(r.state, "READY_FOR_REVIEW")
        self.assertEqual(Event.objects.filter(kind="APPROVE").count(), 0)

    def test_inactive_and_superuser_without_explicit_grant_rejected(self):
        for actor in (self.inactive, self.no_grants):
            r, _, snapshot = self.submitted()
            self.denied(lambda: self.advance(r, "READY_FOR_REVIEW", "REVIEW_ACCEPT",
                                            actor=actor, snapshot=snapshot), "REVIEW_ACTOR_UNAUTHORIZED")

    def test_approval_and_promoted_states_are_hard_disabled(self):
        r, _, _ = self.submitted()
        for state in ("APPROVED", "PROMOTED", "REVOKED"):
            self.denied(lambda: Revision.objects.filter(pk=r.pk).update(
                state=state, version=r.version+1), "REVIEW_APPROVAL_DISABLED")

    def test_approval_event_hard_disabled_even_with_signature(self):
        r, _, snapshot = self.submitted()
        def attempt():
            with connection.cursor() as c:
                c.execute("INSERT INTO inventory_importreviewevent "
                          "(revision_id,sequence,request_id,request_fingerprint,actor_id,kind,from_state,to_state,"
                          "snapshot_id,reason_code,reason,details,signature_algorithm,signing_key_id,signature) "
                          "VALUES (%s,%s,%s,%s,%s,'APPROVE','READY_FOR_REVIEW','APPROVED',%s,"
                          "'TEST','Synthetic','{}','HMAC-SHA256-v1','synthetic-key',%s)",
                          [r.pk, r.version+1, uuid.uuid4(), "a"*64, self.reviewer.pk, snapshot.pk, b"x"*32])
        self.denied(attempt, "REVIEW_APPROVAL_DISABLED")

    def test_registered_source_rows_and_batch_are_frozen(self):
        r, source = self.captured()
        ImportBatch.objects.filter(pk=r.batch_id).update(notes="Non-source note")
        self.assertEqual(ImportBatch.objects.get(pk=r.batch_id).notes, "Non-source note")
        self.denied(lambda: ImportStagingRecord.objects.filter(pk=source.pk).update(raw_values=[]),
                    "REVIEW_SOURCE_IMMUTABLE")
        self.denied(lambda: ImportBatch.objects.filter(pk=r.batch_id).update(file_sha256="9"*64),
                    "REVIEW_SOURCE_IMMUTABLE")
        self.denied(lambda: ImportStagingRecord.objects.create(
            batch=r.batch, worksheet_name="Synthetic", excel_row_number=3, source_row_digest="b"*64),
            "REVIEW_SOURCE_IMMUTABLE")
        def raw():
            with connection.cursor() as c:
                c.execute("DELETE FROM inventory_importstagingrecord WHERE id=%s", [source.pk])
        self.denied(raw)

    def test_unregistered_source_behavior_unchanged(self):
        b, source = self.batch()
        ImportBatch.objects.filter(pk=b.pk).update(notes="Synthetic")
        ImportStagingRecord.objects.filter(pk=source.pk).update(raw_values=[])
        self.assertEqual(ImportStagingRecord.objects.get(pk=source.pk).raw_values, [])

    def test_cannot_adopt_legacy_reviewed_batch(self):
        b, _ = self.batch()
        ImportBatch.objects.filter(pk=b.pk).update(
            reviewed_by=self.reviewer, reviewed_at=b.uploaded_at, approved_preview_digest="a"*64,
            status="APPROVED")
        self.denied(lambda: self.captured(batch=b), "REVIEW_ADOPTION_DISABLED")

    def test_registered_evidence_fk_protection_and_safe_repr(self):
        r, source, snapshot = self.submitted()
        for obj in (r, r.batch, snapshot):
            with self.assertRaises(ProtectedError):
                obj.delete()
        for obj in (r, snapshot, r.review_events.first(), r.participants.first()):
            self.assertNotIn("SYNTHETIC", str(obj))
            self.assertNotIn("private", repr(obj))

    def test_participants_cannot_change_or_delete_or_join_after_seal(self):
        r, _, snapshot = self.submitted()
        self.denied(lambda: Participant.objects.create(revision=r, user=self.reviewer),
                    "REVIEW_PARTICIPANTS_FROZEN")
        p = r.participants.first()
        self.denied(lambda: Participant.objects.filter(pk=p.pk).update(user=self.reviewer),
                    "REVIEW_HISTORY_IMMUTABLE")
        self.denied(lambda: Participant.objects.filter(pk=p.pk).delete(), "REVIEW_HISTORY_IMMUTABLE")

    def test_frozen_payload_after_submission(self):
        r, _, _ = self.submitted()
        self.denied(lambda: Revision.objects.filter(pk=r.pk).update(
            draft_payload={}, version=r.version+1), "REVIEW_PAYLOAD_FROZEN")

    def test_duplicate_request_id_and_sequence_rejected(self):
        r, _ = self.captured()
        old = r.review_events.get()
        def attempt():
            r.state = "PREPARING"
            r.version += 1
            r.save(update_fields=["state", "version"])
            with connection.cursor() as c:
                c.execute("INSERT INTO inventory_importreviewevent "
                          "(revision_id,sequence,request_id,request_fingerprint,actor_id,kind,from_state,to_state,"
                          "reason_code,reason,details) SELECT revision_id,2,request_id,request_fingerprint,actor_id,"
                          "'START','CAPTURED','PREPARING',reason_code,reason,details "
                          "FROM inventory_importreviewevent WHERE id=%s", [old.pk])
        self.denied(attempt)

    def test_payload_orphan_rollback_leaves_original_state(self):
        r, _, snapshot = self.submitted()
        before = (r.version, Event.objects.count(), Snapshot.objects.count(), Participant.objects.count())
        self.denied(lambda: self.advance(r, "APPROVED", "APPROVE", actor=self.reviewer, snapshot=snapshot))
        r.refresh_from_db()
        self.assertEqual(before, (r.version, Event.objects.count(), Snapshot.objects.count(),
                                  Participant.objects.count()))
        self.assertEqual(r.state, "READY_FOR_REVIEW")

    def test_supported_schema_actions_have_no_stock_effects(self):
        models = (Asset, StockBalance, StockMovement, StockOperation)
        before = [list(m.objects.values()) for m in models]
        r, _, snapshot = self.submitted()
        with transaction.atomic():
            self.advance(r, "REJECTED", "REJECT", actor=self.reviewer, snapshot=snapshot)
            self.constraints()
        self.assertEqual(before, [list(m.objects.values()) for m in models])

    def test_authoritative_source_cannot_register_partial_capture(self):
        b, _ = self.batch()
        ImportBatch.objects.filter(pk=b.pk).update(
            file_sha256="d0c48893cc095696ada206fb4d61d80c2745d412b289e0ab754dc5bd023bc525")
        self.denied(lambda: self.captured(batch=b), "REVIEW_PROFILE_COUNTS_INVALID")

    def test_catalog_proves_trigger_security_and_deferred_guards(self):
        with connection.cursor() as c:
            c.execute("SELECT proname,prosecdef,proconfig,has_function_privilege('public',oid,'EXECUTE') "
                      "FROM pg_proc WHERE proname LIKE 'itw_review_%'")
            functions = c.fetchall()
            self.assertEqual(len(functions), 11)
            for name, definer, config, public in functions:
                self.assertFalse(definer)
                self.assertIn("search_path=pg_catalog, public, pg_temp", config)
                self.assertFalse(public)
            c.execute("SELECT count(*) FROM pg_trigger WHERE tgname='review_final' "
                      "AND tgdeferrable AND tginitdeferred")
            self.assertEqual(c.fetchone()[0], 4)

    def test_no_default_sensitive_crud_permissions(self):
        for model in (SourceProfile, Revision, Participant, Snapshot, Event):
            self.assertEqual(model._meta.default_permissions, ())
            self.assertFalse(Permission.objects.filter(content_type__app_label="inventory",
                content_type__model=model._meta.model_name).exists())

    def test_nonowner_role_cannot_bypass_via_dml_or_ddl(self):
        r, _, snapshot = self.submitted()
        with connection.cursor() as c:
            c.execute("CREATE ROLE itw_review_schema_test NOLOGIN NOSUPERUSER NOCREATEDB "
                      "NOCREATEROLE NOINHERIT NOBYPASSRLS")
            c.execute("GRANT USAGE ON SCHEMA public TO itw_review_schema_test")
        statements = [
            "UPDATE inventory_importpreviewsnapshot SET digest='tampered'",
            "TRUNCATE inventory_importpreviewsnapshot",
            "ALTER TABLE inventory_importpreviewsnapshot DISABLE TRIGGER ALL",
            "SELECT public.itw_review_assert('00000000-0000-0000-0000-000000000000'::uuid)",
            "SET LOCAL session_replication_role=replica",
        ]
        for statement in statements:
            with self.assertRaises(DatabaseError):
                with transaction.atomic(), connection.cursor() as c:
                    c.execute("SET LOCAL ROLE itw_review_schema_test")
                    c.execute(statement)

    def test_review_migrations_cannot_unapply(self):
        module = import_module("apps.inventory.migrations.0002_import_review_schema")
        with self.assertRaises(IrreversibleError):
            module.Migration("0002_import_review_schema", "inventory").unapply(None, None)
        guards = import_module("apps.inventory.migrations.0003_import_review_guards")
        self.assertFalse(guards.Migration.operations[0].reversible)


    def test_direct_revision_delete_is_rejected(self):
        r, _ = self.captured()
        def attempt():
            with connection.cursor() as c:
                c.execute("DELETE FROM inventory_importpreparationrevision WHERE id=%s", [r.pk])
        self.denied(attempt, "REVIEW_HISTORY_IMMUTABLE")

    def test_initial_capture_actor_must_be_uploader(self):
        b, _ = self.batch()
        self.denied(lambda: self.captured(batch=b, creator=self.editor),
                    "REVIEW_CAPTURE_UPLOADER_INVALID")


    def test_malformed_snapshot_json_raises_sanitized_code(self):
        r, _ = self.captured()
        with transaction.atomic():
            self.advance(r, "PREPARING", "START")
            self.constraints()
        def attempt():
            r.state = "READY_FOR_REVIEW"
            r.version += 1
            r.save(update_fields=["state", "version"])
            data = b"synthetic-private-invalid-json"
            Snapshot.objects.create(revision=r, canonical_bytes=data,
                                    digest=hashlib.sha256(data).hexdigest())
        self.denied(attempt, "REVIEW_SNAPSHOT_JSON_INVALID")

    def test_rejected_revision_cannot_resume(self):
        r, _, snapshot = self.submitted()
        with transaction.atomic():
            self.advance(r, "REJECTED", "REJECT", actor=self.reviewer, snapshot=snapshot)
            self.constraints()
        self.denied(lambda: Revision.objects.filter(pk=r.pk).update(
            state="PREPARING", version=r.version+1), "REVIEW_TRANSITION_INVALID")


    def test_import_linked_posting_remains_rejected_without_stock_effect(self):
        from apps.inventory.models import AssetCategory, ProductModel
        from apps.warehouse.models import Warehouse, StorageLocation
        from apps.transactions.services.posting import Line, Request, _payload

        r, source = self.captured()
        self.preparer.user_permissions.add(Permission.objects.get(
            content_type__app_label="transactions", codename="receive_stock"))
        before = [m.objects.count() for m in (Asset, StockBalance, StockMovement, StockOperation)]

        def attempt():
            # All fixture positions/header are inside the expected-failure rollback.
            site = Warehouse.objects.create(code="SYN-REJECT", name="Synthetic")
            location = StorageLocation.objects.create(
                warehouse=site, code="SYN-REJECT", name="Synthetic", kind="RACK")
            category = AssetCategory.objects.create(code="SYN-REJECT", name="Synthetic")
            product = ProductModel.objects.create(
                sku_code="SYN-REJECT", name="Synthetic", category=category, tracking_mode="SERIALIZED")
            asset = Asset.objects.create(
                product_model=product, device_name="Synthetic", condition="NEW",
                lifecycle_status="AVAILABLE", current_location=location)
            request = Request(uuid.uuid4(), (Line(
                operation_type="STOCK_IN", product_model_id=product.pk,
                destination_location_id=location.pk, device_name="Synthetic",
            ),), reason="Synthetic rejection proof")
            payload, fingerprint = _payload(request)
            StockOperation.objects.create(operation_key=request.operation_key, request=payload,
                                          fingerprint=fingerprint, requested_by=self.preparer)
            StockMovement.objects.create(
                operation_key=request.operation_key, line_number=1, operation_type="STOCK_IN",
                quantity=1, asset=asset, actor=self.preparer, destination_location=location,
                condition_after="NEW", lifecycle_after="AVAILABLE",
                reason=request.reason, import_row=source,
            )

        self.denied(attempt, "Audit correction and import posting are not enabled")
        self.assertEqual(before, [m.objects.count() for m in
                                 (Asset, StockBalance, StockMovement, StockOperation)])


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.test import TransactionTestCase


class ReviewConcurrencyTests(TransactionTestCase):
    # Reuse fixture construction only; no Case inheritance or copied test methods.
    profile_for = ReviewSchemaTests.profile_for
    create_revision = ReviewSchemaTests.create_revision
    constraints = ReviewSchemaTests.constraints
    event = ReviewSchemaTests.event
    batch = ReviewSchemaTests.batch
    captured = ReviewSchemaTests.captured

    def setUp(self):
        self.preparer = get_user_model().objects.create_user(username="synthetic-race")
        self.preparer.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="inventory", codename="capture_import"))
        self.batch_record, _ = self.batch()

    def test_two_initial_revisions_cannot_commit(self):
        barrier = Barrier(2)
        batch_id = self.batch_record.pk

        def attempt():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                self.captured(batch=ImportBatch.objects.get(pk=batch_id))
                return "COMMITTED"
            except DatabaseError:
                return "REJECTED"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertCountEqual(results, ["COMMITTED", "REJECTED"])
        self.assertEqual(Revision.objects.filter(batch_id=batch_id).count(), 1)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual((Asset.objects.count(), StockBalance.objects.count(), StockMovement.objects.count()),
                         (0, 0, 0))
