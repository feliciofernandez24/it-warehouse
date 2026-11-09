"""PostgreSQL schema coverage; all fixtures are in Django's isolated test database."""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import AssetRecipient, RecipientKind
from apps.audits.models import AssetChangeLog, AuditLine, AuditOutcome, AuditStatus, PhysicalInventoryAudit
from apps.inventory.choices import Condition, LifecycleStatus, RowStatus, SpecificationType, StockState, TrackingMode
from apps.inventory.models import (
    Asset, AssetCategory, AssetSpecification, ImportBatch, ImportStagingRecord,
    Manufacturer, ProductModel, SpecificationDefinition, StockBalance, StockThreshold,
)
from apps.transactions.models import AssetAssignment, MovementType, StockMovement
from apps.warehouse.models import LocationKind, StorageLocation, Warehouse


class SchemaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="operator")
        cls.other = get_user_model().objects.create_user(username="reviewer")
        cls.site = Warehouse.objects.create(code="MAIN", name="Main")
        cls.other_site = Warehouse.objects.create(code="OTHER", name="Other")
        cls.location = StorageLocation.objects.create(warehouse=cls.site, code="845", name="Rack 845", kind=LocationKind.RACK)
        cls.area = StorageLocation.objects.create(warehouse=cls.site, code="BROKEN", name="Broken area", kind=LocationKind.AREA)
        cls.category = AssetCategory.objects.create(code="SPARES", name="Spare parts")
        cls.vendor = Manufacturer.objects.create(code="VENDOR", name="Vendor")
        cls.serialized = ProductModel.objects.create(sku_code="RAM", name="RAM", category=cls.category, manufacturer=cls.vendor, tracking_mode=TrackingMode.SERIALIZED)
        cls.bulk = ProductModel.objects.create(sku_code="CABLE", name="Cable", category=cls.category, tracking_mode=TrackingMode.BULK)
        cls.asset = cls.make_asset()
        cls.bucket = StockBalance.objects.create(product_model=cls.bulk, location=cls.location)
        cls.recipient = AssetRecipient.objects.create(code="ENGINEERING", name="Engineering", kind=RecipientKind.DEPARTMENT)
        cls.batch = ImportBatch.objects.create(original_filename="source.xlsx", file_sha256="a"*64, source_storage_key="private/source", uploaded_by=cls.user, mapping_version="v1")
        cls.audit = PhysicalInventoryAudit.objects.create(scope_location=cls.location, planned_date=timezone.localdate(), performed_by=cls.user)

    @classmethod
    def make_asset(cls, **overrides):
        values = dict(product_model=cls.serialized, device_name="RAM unit", current_location=cls.location)
        values.update(overrides)
        return Asset.objects.create(**values)

    def movement(self, **overrides):
        values = dict(asset=self.asset, quantity=1, operation_type=MovementType.STOCK_OUT,
                      source_location=self.location, actor=self.user, reason="Test schema",
                      occurred_at=timezone.now())
        values.update(overrides)
        return StockMovement.objects.create(**values)

    def assignment(self, **overrides):
        movement = overrides.pop("issue_movement", None) or self.movement()
        values = dict(asset=self.asset, recipient=self.recipient, issued_by=self.user,
                      assigned_at=movement.occurred_at, issue_movement=movement,
                      destination_description="Server room", destination_reference="server-01")
        values.update(overrides)
        return AssetAssignment.objects.create(**values)

    def line_values(self, **overrides):
        values = dict(audit=self.audit, asset=self.asset, location=self.location,
                      expected_location=self.location, expected_quantity=1,
                      expected_condition=Condition.UNKNOWN)
        values.update(overrides)
        return values

    def row_values(self, **overrides):
        values = dict(batch=self.batch, worksheet_name="845", excel_row_number=2, source_row_digest="b"*64)
        values.update(overrides)
        return values

    def rejected(self, call):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                call()

    def test_default_auth_and_no_report_tables(self):
        self.assertEqual(get_user_model()._meta.label, "auth.User")
        self.assertEqual(list(apps.get_app_config("reports").get_models()), [])

    def test_recipient_without_login_and_optional_person_link(self):
        self.recipient.full_clean()
        person = AssetRecipient.objects.create(code="PERSON", name="Person", user=self.user)
        person.full_clean()
        assignment = self.assignment()
        assignment.full_clean()
        self.assertEqual(assignment.recipient, self.recipient)
        self.assertEqual(assignment.destination_reference, "server-01")

    def test_recipient_account_restrictions(self):
        self.rejected(lambda: AssetRecipient.objects.create(code="TEAM", name="Team", kind=RecipientKind.TEAM, user=self.user))
        AssetRecipient.objects.create(code="PERSON", name="Person", user=self.user)
        self.rejected(lambda: AssetRecipient.objects.create(code="SECOND", name="Second", user=self.user))

    def test_internal_tags_generated_unique(self):
        second = self.make_asset()
        self.assertNotEqual(second.asset_tag, self.asset.asset_tag)
        self.rejected(lambda: self.make_asset(asset_tag=self.asset.asset_tag))

    def test_asset_tag_and_product_immutable_in_database(self):
        self.rejected(lambda: Asset.objects.filter(pk=self.asset.pk).update(asset_tag="REPLACED"))
        other = ProductModel.objects.create(sku_code="OTHER", name="Other", category=self.category, tracking_mode=TrackingMode.SERIALIZED)
        self.rejected(lambda: Asset.objects.filter(pk=self.asset.pk).update(product_model=other))

    def test_missing_and_duplicate_serials_allowed(self):
        first = self.make_asset(serial_raw="  Ab-001  ")
        second = self.make_asset(serial_raw="ab-001", serial_review_state="DUPLICATE")
        missing = self.make_asset(serial_raw="", serial_review_state="MISSING")
        self.assertEqual(first.serial_normalized, second.serial_normalized)
        self.assertEqual(missing.serial_raw, "")
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.serial_raw, "  Ab-001  ")

    def test_serial_update_fields_refresh_search_key(self):
        self.asset.serial_raw = "XYZ-002"
        self.asset.save(update_fields=["serial_raw"])
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.serial_normalized, "xyz-002")

    def test_tracking_relationships_validate_and_database_rejects(self):
        invalid = Asset(product_model=self.bulk, device_name="Wrong", current_location=self.location)
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        self.rejected(lambda: self.make_asset(product_model=self.bulk))
        self.rejected(lambda: StockBalance.objects.create(product_model=self.serialized, location=self.location))
        self.rejected(lambda: StockThreshold.objects.create(product_model=self.serialized, warehouse=self.site))

    def test_referenced_tracking_mode_cannot_change(self):
        self.rejected(lambda: ProductModel.objects.filter(pk=self.serialized.pk).update(tracking_mode=TrackingMode.BULK))
        self.rejected(lambda: ProductModel.objects.filter(pk=self.bulk.pk).update(tracking_mode=TrackingMode.SERIALIZED))

    def test_bulk_zero_positive_and_negative_quantity(self):
        self.assertEqual(self.bucket.quantity, 0)
        # Isolated test projection only; no live balance is modified.
        StockBalance.objects.filter(pk=self.bucket.pk).update(quantity=3)
        self.rejected(lambda: StockBalance.objects.filter(pk=self.bucket.pk).update(quantity=-1))

    def test_bucket_unique_identity_and_quarantine(self):
        self.rejected(lambda: StockBalance.objects.create(product_model=self.bulk, location=self.location))
        self.rejected(lambda: StockBalance.objects.filter(pk=self.bucket.pk).update(location=self.area))
        self.rejected(lambda: StockBalance.objects.create(product_model=self.bulk, location=self.area, condition=Condition.BROKEN, stock_state=StockState.AVAILABLE))

    def test_asset_location_state_and_enums(self):
        self.rejected(lambda: self.make_asset(current_location=None))
        self.rejected(lambda: self.make_asset(lifecycle_status=LifecycleStatus.ASSIGNED))
        self.rejected(lambda: self.make_asset(condition="INVALID"))
        self.rejected(lambda: self.make_asset(lifecycle_status=LifecycleStatus.AVAILABLE))

    def test_capacity_and_decimal_units(self):
        for overrides in [dict(capacity_bytes=-1), dict(speed_value=Decimal("1.5"), speed_unit=""),
                          dict(speed_unit="MHz"), dict(size_unit="mm"), dict(size_value=Decimal("0"), size_unit="mm")]:
            with self.subTest(overrides=overrides):
                self.rejected(lambda: ProductModel.objects.create(sku_code="INVALID", name="Invalid", category=self.category, tracking_mode=TrackingMode.BULK, **overrides))
        valid = ProductModel(sku_code="SPEED", name="Speed", category=self.category, tracking_mode=TrackingMode.BULK, speed_value=Decimal("3200"), speed_unit="MT/s")
        valid.full_clean()

    def test_threshold_constraints(self):
        StockThreshold.objects.create(product_model=self.bulk, warehouse=self.site, minimum_quantity=0)
        self.rejected(lambda: StockThreshold.objects.create(product_model=self.bulk, warehouse=self.site, minimum_quantity=1))
        self.rejected(lambda: StockThreshold.objects.create(product_model=self.bulk, warehouse=self.other_site, minimum_quantity=-1))

    def test_rack_and_standalone_location_valid(self):
        self.location.full_clean()
        self.area.full_clean()
        shelf = StorageLocation(warehouse=self.site, parent=self.location, code="S1", name="Shelf", kind=LocationKind.SHELF)
        shelf.full_clean()
        StorageLocation.objects.create(warehouse=self.other_site, code="845", name="Same rack code another site", kind=LocationKind.RACK)

    def test_location_same_warehouse_and_parent_kind_clean(self):
        wrong = StorageLocation(warehouse=self.other_site, parent=self.location, code="S1", name="Shelf", kind=LocationKind.SHELF)
        with self.assertRaises(ValidationError):
            wrong.full_clean()
        wrong.warehouse = self.site
        wrong.kind = LocationKind.AREA
        with self.assertRaises(ValidationError):
            wrong.full_clean()

    def test_location_cycle_clean_and_self_parent_database(self):
        parent = StorageLocation.objects.create(warehouse=self.site, code="A", name="A", kind=LocationKind.AREA)
        child = StorageLocation.objects.create(warehouse=self.site, parent=parent, code="B", name="B", kind=LocationKind.AREA)
        parent.parent = child
        with self.assertRaises(ValidationError):
            parent.full_clean()
        self.rejected(lambda: StorageLocation.objects.filter(pk=parent.pk).update(parent_id=parent.pk))

    def test_location_root_and_unique_database_checks(self):
        self.rejected(lambda: StorageLocation.objects.create(warehouse=self.site, code="845", name="Duplicate", kind=LocationKind.RACK))
        self.rejected(lambda: StorageLocation.objects.create(warehouse=self.site, code="ROOTBIN", name="Bin", kind=LocationKind.BIN))

    def test_specification_owner_and_value_constraints(self):
        definition = SpecificationDefinition.objects.create(code="LATENCY", name="Latency", data_type=SpecificationType.INTEGER)
        good = AssetSpecification(definition=definition, asset=self.asset, integer_value=10)
        good.full_clean()
        good.save()
        self.rejected(lambda: AssetSpecification.objects.create(definition=definition, integer_value=11))
        self.rejected(lambda: AssetSpecification.objects.create(definition=definition, asset=self.asset, product_model=self.serialized, integer_value=11))
        self.rejected(lambda: AssetSpecification.objects.create(definition=definition, product_model=self.bulk, integer_value=1, text_value="one"))
        self.rejected(lambda: AssetSpecification.objects.create(definition=definition, asset=self.asset, integer_value=12))

    def test_specification_definition_type_clean(self):
        definition = SpecificationDefinition.objects.create(code="ACTIVE", name="Active", data_type=SpecificationType.BOOLEAN)
        valid = AssetSpecification(definition=definition, asset=self.asset, boolean_value=False)
        valid.full_clean()
        invalid = AssetSpecification(definition=definition, asset=self.asset, text_value="false")
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_movement_shape_direction_and_idempotency_key(self):
        movement = self.movement()
        movement.full_clean()
        for overrides in [dict(quantity=0), dict(quantity=2), dict(product_model=self.bulk),
                          dict(source_location=None), dict(line_number=0), dict(reason="   ")]:
            with self.subTest(overrides=overrides):
                self.rejected(lambda: self.movement(**overrides))
        self.rejected(lambda: self.movement(operation_key=movement.operation_key, line_number=movement.line_number))

    def test_bulk_movement_and_wrong_tracking(self):
        valid = self.movement(asset=None, product_model=self.bulk, source_balance=self.bucket, quantity=2)
        valid.full_clean()
        self.rejected(lambda: self.movement(asset=None, product_model=self.bulk, quantity=2))
        self.rejected(lambda: self.movement(asset=None, product_model=self.serialized, source_balance=self.bucket))

    def test_movement_bucket_matching_clean(self):
        invalid = StockMovement(asset=None, product_model=self.bulk, quantity=1, source_balance=self.bucket, source_location=self.area, operation_type=MovementType.STOCK_OUT, actor=self.user, reason="Invalid")
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_transfer_noop_rejected(self):
        self.rejected(lambda: self.movement(operation_type=MovementType.TRANSFER, destination_location=self.location))
        self.rejected(lambda: self.movement(asset=None, product_model=self.bulk, quantity=1, operation_type=MovementType.TRANSFER, destination_location=self.location, source_balance=self.bucket, destination_balance=self.bucket))

    def test_open_assignment_unique_and_history_fields(self):
        first = self.assignment()
        self.assertIsNone(first.returned_at)
        self.rejected(lambda: self.assignment())

    def test_closed_assignment_preserves_recipient_and_new_episode(self):
        movement = self.movement()
        returned = self.movement(operation_type=MovementType.RETURN, source_location=None, destination_location=self.area, occurred_at=movement.occurred_at+timedelta(days=1))
        closed = self.assignment(issue_movement=movement, returned_at=returned.occurred_at, returned_by=self.user, return_movement=returned)
        closed.full_clean()
        self.assignment()
        self.assertEqual(self.asset.assignments.count(), 2)
        self.assertEqual(closed.recipient, self.recipient)

    def test_assignment_date_and_return_fields(self):
        self.rejected(lambda: self.assignment(due_at=timezone.now()-timedelta(days=1)))
        self.rejected(lambda: self.assignment(returned_at=timezone.now()))
        assignment = self.assignment()
        assignment.issue_movement = self.movement(operation_type=MovementType.STOCK_IN, source_location=None, destination_location=self.location)
        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_audit_header_constraints(self):
        self.rejected(lambda: PhysicalInventoryAudit.objects.create(scope_location=self.location, planned_date=timezone.localdate(), performed_by=self.user, approved_by=self.user, approved_at=timezone.now()))
        self.rejected(lambda: PhysicalInventoryAudit.objects.create(scope_location=self.location, planned_date=timezone.localdate(), performed_by=self.user, status=AuditStatus.APPROVED))
        self.rejected(lambda: PhysicalInventoryAudit.objects.create(scope_location=self.location, planned_date=timezone.localdate(), performed_by=self.user, status=AuditStatus.COUNTING))

    def test_audit_line_counts_xor_and_uniqueness(self):
        AuditLine.objects.create(**self.line_values())
        self.rejected(lambda: AuditLine.objects.create(**self.line_values()))
        self.rejected(lambda: AuditLine.objects.create(**self.line_values(asset=None)))
        self.rejected(lambda: AuditLine.objects.create(**self.line_values(asset=None, product_model=self.bulk, expected_stock_state=StockState.QUARANTINED, expected_quantity=-1)))
        self.rejected(lambda: AuditLine.objects.create(**self.line_values(asset=self.make_asset(), expected_quantity=2)))

    def test_audit_counted_observation_evidence(self):
        self.rejected(lambda: AuditLine.objects.create(**self.line_values(observed_quantity=0)))
        valid = AuditLine(**self.line_values(observed_quantity=0, counted_by=self.user, counted_at=timezone.now(), outcome=AuditOutcome.MISSING))
        valid.full_clean()

    def test_audit_bulk_snapshot_and_excess_unique(self):
        values = self.line_values(asset=None, product_model=self.bulk, stock_balance=self.bucket, expected_stock_state=StockState.QUARANTINED, expected_quantity=0)
        AuditLine.objects.create(**values)
        self.rejected(lambda: AuditLine.objects.create(**values))
        values["stock_balance"] = None
        values["expected_location"] = None
        AuditLine.objects.create(**values)
        self.rejected(lambda: AuditLine.objects.create(**values))
        values["location"] = self.area
        AuditLine.objects.create(**values)

    def test_staging_source_coordinates_unique(self):
        row = ImportStagingRecord.objects.create(**self.row_values())
        row.full_clean()
        self.rejected(lambda: ImportStagingRecord.objects.create(**self.row_values()))
        self.rejected(lambda: ImportStagingRecord.objects.create(**self.row_values(excel_row_number=0)))

    def test_staging_promotion_xor_and_timestamp(self):
        self.rejected(lambda: ImportStagingRecord.objects.create(**self.row_values(asset=self.asset)))
        self.rejected(lambda: ImportStagingRecord.objects.create(**self.row_values(status=RowStatus.PROMOTED, promoted_at=timezone.now())))
        row = ImportStagingRecord.objects.create(**self.row_values(status=RowStatus.PROMOTED, promoted_at=timezone.now(), asset=self.asset))
        self.assertEqual(row.asset, self.asset)
        # Opening movement/batch coherence is explicitly deferred to Phase 2C.

    def test_import_review_evidence(self):
        self.rejected(lambda: ImportBatch.objects.filter(pk=self.batch.pk).update(status="APPROVED"))
        self.rejected(lambda: ImportBatch.objects.filter(pk=self.batch.pk).update(reviewed_by=self.user, reviewed_at=timezone.now()))
        ImportBatch.objects.filter(pk=self.batch.pk).update(reviewed_by=self.other, reviewed_at=timezone.now(), approved_preview_digest="c"*64, status="APPROVED")

    def test_protect_referenced_masters_users_and_recipients(self):
        self.assignment()
        for obj in [self.category, self.serialized, self.site, self.location, self.user, self.recipient, self.asset]:
            with self.subTest(model=obj._meta.label):
                with self.assertRaises(ProtectedError):
                    obj.delete()

    def test_unreferenced_history_delete_and_append_only_events(self):
        movement = self.movement()
        log = AssetChangeLog.objects.create(entity_kind="inventory.Asset", entity_pk=self.asset.pk, asset=self.asset, actor=self.user, action="CREATE", reason="Test")
        self.rejected(lambda: StockMovement.objects.filter(pk=movement.pk).update(reason="Rewrite"))
        self.rejected(lambda: AssetChangeLog.objects.filter(pk=log.pk).update(reason="Rewrite"))
        for obj in [movement, log, self.audit, self.batch]:
            with self.subTest(model=obj._meta.label):
                self.rejected(lambda: type(obj).objects.filter(pk=obj.pk).delete())

    def test_history_child_delete_guards(self):
        assignment = self.assignment()
        line = AuditLine.objects.create(**self.line_values())
        row = ImportStagingRecord.objects.create(**self.row_values())
        for obj in [assignment, line, row]:
            with self.subTest(model=obj._meta.label):
                self.rejected(lambda: type(obj).objects.filter(pk=obj.pk).delete())

    def test_database_constraint_and_index_catalog(self):
        expected = {
            Asset: ["asset_serial_search", "asset_location_lifecycle"],
            StockBalance: ["stock_bucket_unique", "stock_quantity_nonnegative"],
            AssetAssignment: ["assignment_one_open_asset", "assignment_recipient_return"],
            AuditLine: ["audit_excess_bucket_unique", "audit_asset_unique"],
            ImportStagingRecord: ["staging_source_row_unique", "staging_batch_status"],
            StockMovement: ["movement_operation_line_unique", "movement_positive_quantity"],
        }
        with connection.cursor() as cursor:
            for model, names in expected.items():
                constraints = connection.introspection.get_constraints(cursor, model._meta.db_table)
                for name in names:
                    self.assertIn(name, constraints)
            cursor.execute("SELECT indexdef FROM pg_indexes WHERE indexname='assignment_one_open_asset'")
            self.assertIn("WHERE (returned_at IS NULL)", cursor.fetchone()[0])
            cursor.execute("SELECT indexdef FROM pg_indexes WHERE indexname='audit_excess_bucket_unique'")
            self.assertIn("NULLS NOT DISTINCT", cursor.fetchone()[0])

    def test_database_guard_triggers_installed(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
            names = {row[0] for row in cursor.fetchall()}
        self.assertTrue({"asset_identity_guard", "bucket_identity_guard", "tracking_guard", "product_mode_guard", "history_no_delete", "history_no_update"} <= names)

    def test_timestamps_are_timezone_aware(self):
        self.assertTrue(timezone.is_aware(self.asset.created_at))
        self.assertTrue(timezone.is_aware(self.movement().recorded_at))

    def test_phase2c_clean_checks_are_not_database_guarantees(self):
        # A deliberate contract test: do not misrepresent clean() as DB enforcement.
        wrong = StorageLocation.objects.create(warehouse=self.other_site, parent=self.location,
                                               code="CROSS", name="Cross site", kind=LocationKind.SHELF)
        with self.assertRaises(ValidationError):
            wrong.full_clean()
        definition = SpecificationDefinition.objects.create(code="BOOL", name="Boolean", data_type=SpecificationType.BOOLEAN)
        wrong_spec = AssetSpecification.objects.create(definition=definition, asset=self.asset, text_value="not boolean")
        with self.assertRaises(ValidationError):
            wrong_spec.full_clean()

    def test_assignment_issued_identity_and_closed_history_immutable(self):
        episode = self.assignment()
        self.rejected(lambda: AssetAssignment.objects.filter(pk=episode.pk).update(destination_reference="rewritten"))
        returned = self.movement(operation_type=MovementType.RETURN, source_location=None,
                                 destination_location=self.area,
                                 occurred_at=episode.assigned_at+timedelta(days=1))
        AssetAssignment.objects.filter(pk=episode.pk).update(
            returned_at=returned.occurred_at, returned_by=self.user, return_movement=returned)
        self.rejected(lambda: AssetAssignment.objects.filter(pk=episode.pk).update(
            returned_at=None, returned_by=None, return_movement=None))

    def test_invalid_foreign_key_clean_is_validation_error(self):
        invalid = Asset(product_model_id=99999999, device_name="Missing catalog",
                        current_location=self.location)
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        missing_issue = AssetAssignment(asset=self.asset, recipient=self.recipient,
                                        issued_by=self.user)
        with self.assertRaises(ValidationError):
            missing_issue.full_clean()
