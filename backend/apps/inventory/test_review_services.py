"""Synthetic authorization tests; isolated PostgreSQL only."""
import uuid
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.test import TestCase
from django.db import transaction
from apps.inventory import test_review_schema as fixtures
from apps.inventory.review.authorization import require_capabilities, require_independent_reviewer
from apps.inventory.review.errors import ReviewServiceError, database_error
from apps.inventory.review import services

class AuthenticatedReviewTests(TestCase):
    setUpTestData = classmethod(fixtures.ReviewSchemaTests.setUpTestData.__func__)
    batch = fixtures.ReviewSchemaTests.batch
    profile_for = fixtures.ReviewSchemaTests.profile_for
    create_revision = fixtures.ReviewSchemaTests.create_revision
    captured = fixtures.ReviewSchemaTests.captured
    event = fixtures.ReviewSchemaTests.event
    constraints = fixtures.ReviewSchemaTests.constraints
    advance = fixtures.ReviewSchemaTests.advance

    def denied(self, code, call):
        with self.assertRaises(ReviewServiceError) as error:
            call()
        self.assertEqual(error.exception.code, code)

    def test_anonymous(self):
        for actor in (None, AnonymousUser()):
            self.denied("AUTHENTICATION_REQUIRED", lambda: require_capabilities(actor, "inventory.review_import"))

    def test_forged_actor(self):
        for actor in (self.reviewer.pk, {"actor_id": self.reviewer.pk},
                      get_user_model()(pk=self.reviewer.pk)):
            self.denied("INVALID_ACTOR_CONTEXT", lambda: require_capabilities(actor, "inventory.review_import"))

    def test_inactive(self):
        self.denied("ACTOR_INACTIVE", lambda: require_capabilities(self.inactive, "inventory.review_import"))

    def test_superuser(self):
        self.denied("PERMISSION_DENIED", lambda: require_capabilities(self.no_grants, "inventory.review_import"))

    def test_direct_grant(self):
        self.assertEqual(require_capabilities(self.reviewer, "inventory.review_import").user_id, self.reviewer.pk)

    def test_group_grant(self):
        group = Group.objects.create(name="synthetic-review")
        group.permissions.add(Permission.objects.get(content_type__app_label="inventory", codename="review_import"))
        self.no_grants.groups.add(group)
        require_capabilities(self.no_grants, "inventory.review_import")

    def test_cache_revocation(self):
        self.reviewer.has_perm("inventory.review_import")
        self.reviewer.user_permissions.clear()
        self.denied("PERMISSION_DENIED", lambda: require_capabilities(self.reviewer, "inventory.review_import"))

    def test_stale_inactive_object(self):
        get_user_model().objects.filter(pk=self.reviewer.pk).update(is_active=False)
        self.denied("ACTOR_INACTIVE", lambda: require_capabilities(self.reviewer, "inventory.review_import"))

    def test_evidence_separate(self):
        revision, _ = self.captured()
        self.reviewer.user_permissions.remove(Permission.objects.get(content_type__app_label="inventory", codename="view_import_evidence"))
        self.denied("PERMISSION_DENIED", lambda: require_independent_reviewer(self.reviewer, revision.pk))

    def test_uploader_denied(self):
        revision, _ = self.captured()
        self.denied("SELF_REVIEW_UPLOADER", lambda: require_independent_reviewer(self.preparer, revision.pk))

    def test_creator_denied(self):
        parent, _ = self.captured()
        with transaction.atomic():
            self.advance(parent, "SUPERSEDED", "SUPERSEDE")
            revision, _ = self.captured(batch=parent.batch, creator=self.editor, number=2, parent=parent)
            self.constraints()
        self.denied("SELF_REVIEW_CREATOR", lambda: require_independent_reviewer(self.editor, revision.pk))

    def test_independent_allowed(self):
        revision, _ = self.captured()
        self.assertEqual(require_independent_reviewer(self.reviewer, revision.pk).version, 1)

    def test_preflight_and_disabled_write(self):
        revision, _ = self.captured()
        args = dict(actor=self.preparer, request_id=uuid.uuid4(), revision_id=revision.pk, expected_version=1)
        count = revision.review_events.count()
        self.assertFalse(services.inspect_request(action="start_preparation", **args)["writes_enabled"])
        self.denied("GATEWAY_UNAVAILABLE", lambda: services.start_preparation(**args))
        revision.refresh_from_db()
        self.assertEqual((revision.version, revision.review_events.count()), (1, count))

    def test_expected_version(self):
        revision, _ = self.captured()
        self.denied("VERSION_CONFLICT", lambda: services.start_preparation(actor=self.preparer, request_id=uuid.uuid4(), revision_id=revision.pk, expected_version=2))

    def test_actor_payload_rejected(self):
        self.denied("INVALID_REQUEST", lambda: services.register_verified_capture(actor=self.preparer, request_id=uuid.uuid4(), payload={"actor_id": 123}))

    def test_approval_revocation_promotion_disabled(self):
        for function in (services.approve_revision, services.revoke_approval, services.promote_import):
            self.denied("ACTION_DISABLED", function)

    def test_sanitized_errors(self):
        self.assertEqual(str(ReviewServiceError("private")), "INTERNAL_ERROR")
        self.assertEqual(database_error(Exception("private")).code, "DATABASE_OPERATION_FAILED")

    def test_conflicting_existing_request(self):
        revision, _ = self.captured()
        event = revision.review_events.get()
        self.denied("REQUEST_CONFLICT", lambda: services.inspect_request(actor=self.preparer, action="start_preparation", request_id=event.request_id, revision_id=revision.pk, expected_version=1))

    def test_inherited_contributor_denied(self):
        parent, _ = self.captured()
        with transaction.atomic():
            self.advance(parent, "PREPARING", "START", actor=self.editor)
            self.advance(parent, "SUPERSEDED", "SUPERSEDE")
            revision, _ = self.captured(batch=parent.batch, creator=self.reviewer, number=2, parent=parent)
            self.constraints()
        self.denied("SELF_REVIEW_CONTRIBUTOR", lambda: require_independent_reviewer(self.editor, revision.pk))

    def test_current_contributor_denied(self):
        revision, _ = self.captured()
        with transaction.atomic():
            self.advance(revision, "PREPARING", "START", actor=self.editor)
            self.constraints()
        self.denied("SELF_REVIEW_CONTRIBUTOR", lambda: require_independent_reviewer(self.editor, revision.pk))

    def test_exact_historical_replay_and_payload_conflict(self):
        from apps.inventory.models import ImportReviewEvent
        from django.db import connection
        revision, _ = self.captured()
        args = dict(actor=self.preparer, action="start_preparation", request_id=uuid.uuid4(),
                    revision_id=revision.pk, expected_version=1, payload={"reason_code": "SYNTHETIC"})
        fingerprint = services.inspect_request(**args)["fingerprint"]
        with transaction.atomic():
            revision.state, revision.version = "PREPARING", 2
            revision.save(update_fields=["state", "version"])
            with connection.cursor() as cursor:
                cursor.execute("SELECT encode(sha256(convert_to(draft_payload::text,'UTF8')),'hex') FROM inventory_importpreparationrevision WHERE id=%s", [revision.pk])
                digest = cursor.fetchone()[0]
            event = ImportReviewEvent.objects.create(revision=revision, sequence=2,
                request_id=args["request_id"], request_fingerprint=fingerprint, actor=self.preparer,
                kind="START", from_state="CAPTURED", to_state="PREPARING",
                reason_code="SYNTHETIC", reason="Synthetic",
                details={"after_payload_digest": digest})
            self.constraints()
        replay = services.inspect_request(**args)
        self.assertEqual(replay["historical_event_id"], str(event.pk))
        self.assertEqual(replay["version"], 2)
        self.denied("REQUEST_CONFLICT", lambda: services.inspect_request(**{**args, "payload": {"reason_code": "OTHER"}}))
        self.denied("REQUEST_CONFLICT", lambda: services.inspect_request(**{**args, "actor": self.editor}))
        self.assertEqual(revision.review_events.count(), 2)

    def test_invalid_payloads_sanitized(self):
        for payload in ({"actor_id": 1}, {"value": 1.5}, {"value": object()}, ["private"]):
            self.denied("INVALID_REQUEST", lambda: services.register_verified_capture(actor=self.preparer, request_id=uuid.uuid4(), payload=payload))

    def test_large_payload_rejected(self):
        self.denied("REQUEST_TOO_LARGE", lambda: services.register_verified_capture(actor=self.preparer, request_id=uuid.uuid4(), payload={"value": "x"*32768}))

    def test_invalid_revision_sanitized(self):
        self.denied("INVALID_REQUEST", lambda: require_independent_reviewer(self.reviewer, "PRIVATE-INVALID"))

    def test_deadlock_and_timeout_codes(self):
        for state, code in (("40P01", "RETRYABLE_TRANSACTION"), ("40001", "RETRYABLE_TRANSACTION"), ("55P03", "LOCK_TIMEOUT"), ("57014", "LOCK_TIMEOUT")):
            error = Exception("private SQL")
            error.sqlstate = state
            self.assertEqual(database_error(error).code, code)

    def test_service_database_failure_rolls_back(self):
        from unittest.mock import patch
        from django.db import DatabaseError
        from apps.inventory.models import Asset, StockBalance, ImportReviewEvent
        before = (Asset.objects.count(), StockBalance.objects.count(), ImportReviewEvent.objects.count())
        with patch("apps.inventory.review.services.require_capabilities", side_effect=DatabaseError("private SQL")):
            self.denied("DATABASE_OPERATION_FAILED", lambda: services.register_verified_capture(actor=self.preparer, request_id=uuid.uuid4()))
        self.assertEqual(before, (Asset.objects.count(), StockBalance.objects.count(), ImportReviewEvent.objects.count()))
        require_capabilities(self.preparer, "inventory.capture_import")


from apps.inventory import test_review_hardening as hardening
from django.test import TransactionTestCase

class ServiceConcurrencyTests(TransactionTestCase):
    setUp = hardening.HardeningConcurrencyTests.setUp
    race_order = hardening.HardeningConcurrencyTests.race_order
    constraints = fixtures.ReviewSchemaTests.constraints
    profile_for = fixtures.ReviewSchemaTests.profile_for
    create_revision = fixtures.ReviewSchemaTests.create_revision
    batch = fixtures.ReviewSchemaTests.batch
    event = fixtures.ReviewSchemaTests.event
    captured = fixtures.ReviewSchemaTests.captured

    def test_preflight_waits_for_shared_lock_and_observes_current_version(self):
        from django.db import connection
        self.preparer.user_permissions.add(Permission.objects.get(content_type__app_label="inventory", codename="view_import_evidence"))
        revision, _ = self.captured(batch=self.b)
        codes = []
        def first():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(73921,2)")
            revision.version, revision.state = 2, "PREPARING"
            revision.save(update_fields=["version", "state"])
            self.event(revision, "START", "CAPTURED")
            self.constraints()
        def second():
            try:
                services.start_preparation(actor=self.preparer, request_id=uuid.uuid4(), revision_id=revision.pk, expected_version=1)
            except ReviewServiceError as error:
                codes.append(error.code)
        self.assertEqual(self.race_order(first, second), ("COMMITTED", "COMMITTED"))
        self.assertEqual(codes, ["VERSION_CONFLICT"])
        self.assertEqual(revision.review_events.count(), 2)
