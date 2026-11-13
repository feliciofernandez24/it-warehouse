"""Current-schema PostgreSQL service and adversarial SQL tests (never live inventory)."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import StringIO
from threading import Barrier
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.db.models import Sum
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.accounts.models import AssetRecipient
from apps.audits.models import AuditLine, PhysicalInventoryAudit
from apps.inventory.models import Asset, AssetCategory, ProductModel, StockBalance
from apps.transactions.models import AssetAssignment, StockMovement, StockOperation
from apps.transactions.services import Line, Request, approve_operation, post, request_operation
from apps.transactions.services.audits import record_count, start_audit
from apps.transactions.services.custody import current_custody
from apps.transactions.services.exceptions import AuthorizationError, IdempotencyConflict, StockError
from apps.warehouse.models import StorageLocation, Warehouse


class EngineTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="operator")
        self.reviewer = get_user_model().objects.create_user(username="reviewer")
        self.denied = get_user_model().objects.create_superuser(username="ungranted", password="test")
        permissions = Permission.objects.filter(content_type__app_label="transactions")
        self.user.user_permissions.add(*permissions)
        self.reviewer.user_permissions.add(*permissions)
        self.site = Warehouse.objects.create(code="SITE", name="Site")
        self.location = StorageLocation.objects.create(warehouse=self.site, code="AREA", name="Area", kind="AREA")
        self.rack = StorageLocation.objects.create(warehouse=self.site, parent=self.location, code="RACK", name="Rack", kind="RACK")
        self.other = StorageLocation.objects.create(warehouse=self.site, code="OTHER", name="Other", kind="AREA")
        self.category = AssetCategory.objects.create(code="PARTS", name="Parts")
        self.bulk = ProductModel.objects.create(sku_code="BULK", name="Bulk", category=self.category, tracking_mode="BULK")
        self.serialized = ProductModel.objects.create(sku_code="SERIAL", name="Serialized", category=self.category, tracking_mode="SERIALIZED")
        self.recipient = AssetRecipient.objects.create(code="RECIPIENT", name="Recipient")

    def request(self, *lines, key=None, reason="Test stock operation"):
        return Request(key or uuid4(), tuple(lines), reason)

    def bulk_line(self, kind="STOCK_IN", quantity=10, **kwargs):
        values = dict(operation_type=kind, quantity=quantity, product_model_id=self.bulk.pk)
        if kind in ("STOCK_IN", "RETURN", "ADJUSTMENT_IN"):
            values["destination_location_id"] = self.location.pk
        else:
            values["source_location_id"] = self.location.pk
        if kind == "TRANSFER":
            values["destination_location_id"] = self.other.pk
        values.update(kwargs)
        return Line(**values)

    def receive_bulk(self, quantity=10):
        return post(actor=self.user, request=self.request(self.bulk_line(quantity=quantity)))

    def receive_asset(self, **kwargs):
        values = dict(operation_type="STOCK_IN", product_model_id=self.serialized.pk,
            destination_location_id=self.location.pk, device_name="Unit")
        values.update(kwargs)
        result = post(actor=self.user, request=self.request(Line(**values)))
        return Asset.objects.get(pk=result.asset_ids[0])

    def issue_asset(self, asset):
        return post(actor=self.user, request=self.request(Line("STOCK_OUT", asset_id=asset.pk,
            source_location_id=asset.current_location_id, recipient_id=self.recipient.pk,
            destination_reference="host-01", destination_description="Engineering")))

    def approve(self, request):
        request_operation(actor=self.user, request=request)
        approve_operation(actor=self.reviewer, operation_key=request.operation_key, reason="Reviewed exact request")

    def assert_reconciled(self):
        call_command("reconcile_stock", stdout=StringIO())

    def test_serialized_receipt(self):
        asset = self.receive_asset()
        self.assertEqual(asset.lifecycle_status, "AVAILABLE")
        self.assertEqual(asset.current_location_id, self.location.pk)
        self.assert_reconciled()

    def test_serialized_issue_custody(self):
        asset = self.receive_asset()
        self.issue_asset(asset)
        asset.refresh_from_db()
        self.assertEqual(asset.lifecycle_status, "ASSIGNED")
        self.assertIsNone(asset.current_location_id)
        assignment = current_custody(asset.pk)
        self.assertEqual(assignment.destination_reference, "host-01")
        self.assertEqual(assignment.recipient, self.recipient)
        self.assert_reconciled()

    def test_serialized_return_restores_correct_bucket_and_history(self):
        asset = self.receive_asset()
        issued = self.issue_asset(asset)
        assignment = current_custody(asset.pk)
        post(actor=self.user, request=self.request(Line("RETURN", asset_id=asset.pk,
            assignment_id=assignment.pk, reverses_id=issued.movement_ids[0],
            destination_location_id=self.other.pk, condition="BROKEN", state="QUARANTINED")))
        asset.refresh_from_db(); assignment.refresh_from_db()
        self.assertEqual((asset.condition, asset.lifecycle_status, asset.current_location_id), ("BROKEN", "QUARANTINED", self.other.pk))
        self.assertIsNotNone(assignment.returned_at)
        self.assertIsNone(current_custody(asset.pk))
        self.assertEqual(AssetAssignment.objects.count(), 1)
        self.assert_reconciled()

    def test_duplicate_issue_rejected(self):
        asset = self.receive_asset(); self.issue_asset(asset)
        with self.assertRaises(StockError):
            self.issue_asset(asset)
        self.assertEqual(AssetAssignment.objects.count(), 1)

    def test_disposed_asset_issue_rejected(self):
        asset = self.receive_asset()
        request = self.request(Line("DISPOSAL", asset_id=asset.pk, source_location_id=self.location.pk))
        self.approve(request); post(actor=self.user, request=request)
        with self.assertRaises(StockError): self.issue_asset(asset)
        self.assert_reconciled()

    def test_bulk_receipt(self):
        self.receive_bulk()
        self.assertEqual(StockBalance.objects.get().quantity, 10)
        self.assert_reconciled()

    def test_bulk_issue_without_assignment(self):
        self.receive_bulk()
        post(actor=self.user, request=self.request(self.bulk_line("STOCK_OUT", 4)))
        self.assertEqual(StockBalance.objects.get().quantity, 6)
        self.assertFalse(AssetAssignment.objects.exists())
        self.assert_reconciled()

    def test_insufficient_stock_rollback(self):
        self.receive_bulk(3)
        request = self.request(self.bulk_line("STOCK_OUT", 4))
        with self.assertRaises(StockError): post(actor=self.user, request=request)
        self.assertEqual(StockBalance.objects.get().quantity, 3)
        self.assertFalse(StockOperation.objects.filter(pk=request.operation_key).exists())
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_bulk_transfer(self):
        self.receive_bulk()
        post(actor=self.user, request=self.request(self.bulk_line("TRANSFER", 4)))
        self.assertEqual(StockBalance.objects.get(location=self.location).quantity, 6)
        self.assertEqual(StockBalance.objects.get(location=self.other).quantity, 4)
        self.assert_reconciled()

    def test_serialized_transfer(self):
        asset = self.receive_asset()
        post(actor=self.user, request=self.request(Line("TRANSFER", asset_id=asset.pk,
            source_location_id=self.location.pk, destination_location_id=self.other.pk)))
        asset.refresh_from_db()
        self.assertEqual(asset.current_location_id, self.other.pk)
        self.assert_reconciled()

    def test_bulk_quarantine_same_location(self):
        self.receive_bulk()
        post(actor=self.user, request=self.request(self.bulk_line("TRANSFER", 4,
            destination_location_id=self.location.pk, condition="BROKEN", state="QUARANTINED")))
        self.assertEqual(StockBalance.objects.get(condition="BROKEN").quantity, 4)
        self.assert_reconciled()

    def test_serialized_quarantine_same_location(self):
        asset = self.receive_asset()
        post(actor=self.user, request=self.request(Line("TRANSFER", asset_id=asset.pk,
            source_location_id=self.location.pk, destination_location_id=self.location.pk,
            condition="BROKEN", state="QUARANTINED")))
        asset.refresh_from_db()
        self.assertEqual(asset.lifecycle_status, "QUARANTINED")
        self.assert_reconciled()

    def test_bulk_return(self):
        self.receive_bulk()
        issued = post(actor=self.user, request=self.request(self.bulk_line("STOCK_OUT", 4)))
        post(actor=self.user, request=self.request(self.bulk_line("RETURN", 2, reverses_id=issued.movement_ids[0], condition="USED")))
        self.assertEqual(StockBalance.objects.get(condition="USED").quantity, 2)
        self.assert_reconciled()

    def test_approved_adjustment(self):
        request = self.request(self.bulk_line("ADJUSTMENT_IN", 4))
        self.approve(request); post(actor=self.user, request=request)
        self.assertEqual(StockBalance.objects.get().quantity, 4)
        self.assert_reconciled()

    def test_unapproved_adjustment_rejected(self):
        with self.assertRaises(StockError): post(actor=self.user, request=self.request(self.bulk_line("ADJUSTMENT_IN", 4)))
        self.assertFalse(StockMovement.objects.exists())

    def test_bulk_approved_disposal(self):
        self.receive_bulk()
        request = self.request(self.bulk_line("DISPOSAL", 3))
        self.approve(request); post(actor=self.user, request=request)
        self.assertEqual(StockBalance.objects.get().quantity, 7)
        self.assert_reconciled()

    def test_unapproved_disposal_rejected(self):
        self.receive_bulk()
        with self.assertRaises(StockError): post(actor=self.user, request=self.request(self.bulk_line("DISPOSAL", 3)))

    def test_lost_asset_requires_approved_adjustment(self):
        asset = self.receive_asset()
        request = self.request(Line("ADJUSTMENT_OUT", asset_id=asset.pk, source_location_id=self.location.pk))
        self.approve(request); post(actor=self.user, request=request)
        asset.refresh_from_db()
        self.assertEqual(asset.lifecycle_status, "LOST")
        self.assert_reconciled()

    def test_idempotent_identical_request(self):
        request = self.request(self.bulk_line())
        first = post(actor=self.user, request=request)
        self.assertEqual(first, post(actor=self.user, request=request))
        self.assertEqual(StockBalance.objects.get().quantity, 10)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_idempotency_changed_payload_rejected(self):
        request = self.request(self.bulk_line()); post(actor=self.user, request=request)
        with self.assertRaises(IdempotencyConflict):
            post(actor=self.user, request=replace(request, reason="Changed"))
        with self.assertRaises(IdempotencyConflict):
            post(actor=self.user, request=replace(request, lines=(self.bulk_line(quantity=11),)))

    def test_multiline_atomicity_failure_in_second_line(self):
        self.receive_bulk(5)
        request = self.request(self.bulk_line("STOCK_OUT", 3), self.bulk_line("STOCK_OUT", 3))
        with self.assertRaises(StockError): post(actor=self.user, request=request)
        self.assertEqual(StockBalance.objects.get().quantity, 5)
        self.assertFalse(StockOperation.objects.filter(pk=request.operation_key).exists())
        self.assert_reconciled()

    def test_multiline_success_and_idempotency(self):
        request = self.request(self.bulk_line(quantity=3), self.bulk_line(quantity=4))
        result = post(actor=self.user, request=request)
        self.assertEqual(len(result.movement_ids), 2)
        self.assertEqual(post(actor=self.user, request=request), result)
        self.assertEqual(StockBalance.objects.get().quantity, 7)
        self.assert_reconciled()

    def concurrent(self, action):
        barrier = Barrier(2)
        def run(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                action()
                return "committed"
            except StockError:
                return "rejected"
            finally:
                connections["default"].close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, range(2)))

    def test_concurrent_bulk_withdrawals(self):
        self.receive_bulk(5)
        results = self.concurrent(lambda: post(actor=self.user, request=self.request(self.bulk_line("STOCK_OUT", 4))))
        self.assertCountEqual(results, ["committed", "rejected"])
        self.assertEqual(StockBalance.objects.get().quantity, 1)
        self.assert_reconciled()

    def test_concurrent_asset_issues(self):
        asset = self.receive_asset()
        self.assertCountEqual(self.concurrent(lambda: self.issue_asset(asset)), ["committed", "rejected"])
        self.assertEqual(AssetAssignment.objects.filter(returned_at__isnull=True).count(), 1)
        self.assert_reconciled()

    def test_concurrent_identical_operation(self):
        request = self.request(self.bulk_line())
        self.assertCountEqual(self.concurrent(lambda: post(actor=self.user, request=request)), ["committed", "committed"])
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assert_reconciled()

    def test_immutable_movement(self):
        self.receive_bulk()
        for change in (lambda: StockMovement.objects.update(reason="Tampered"), lambda: StockMovement.objects.all().delete()):
            with self.assertRaises(IntegrityError), transaction.atomic(): change()

    def test_immutable_operation_and_approval(self):
        request = self.request(self.bulk_line("ADJUSTMENT_IN")); self.approve(request)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockOperation.objects.filter(pk=request.operation_key).update(approval_reason="Rewritten")
        post(actor=self.user, request=request)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockOperation.objects.filter(pk=request.operation_key).update(request={})

    def test_duplicate_and_excess_reversal_rejected(self):
        self.receive_bulk()
        issued = post(actor=self.user, request=self.request(self.bulk_line("STOCK_OUT", 4)))
        request = self.request(self.bulk_line("RETURN", 4, reverses_id=issued.movement_ids[0]))
        post(actor=self.user, request=request)
        with self.assertRaises(StockError): post(actor=self.user, request=replace(request, operation_key=uuid4()))
        self.assert_reconciled()

    def test_concurrent_reversal_cap(self):
        self.receive_bulk()
        issued = post(actor=self.user, request=self.request(self.bulk_line("STOCK_OUT", 4)))
        self.assertCountEqual(self.concurrent(lambda: post(actor=self.user,
            request=self.request(self.bulk_line("RETURN", 3, reverses_id=issued.movement_ids[0])))), ["committed", "rejected"])
        self.assert_reconciled()

    def freeze(self, location=None, descendants=True):
        audit = PhysicalInventoryAudit.objects.create(scope_location=location or self.location,
            include_descendants=descendants, planned_date=timezone.localdate(), performed_by=self.user)
        return start_audit(actor=self.user, audit_id=audit.pk)

    def test_audit_freeze_includes_parent_and_descendants(self):
        self.receive_bulk(); self.freeze()
        for location in (self.location, self.rack):
            with self.assertRaises(IntegrityError):
                post(actor=self.user, request=self.request(self.bulk_line(destination_location_id=location.pk)))
        self.assertEqual(StockBalance.objects.get().quantity, 10)

    def test_audit_scope_without_descendants(self):
        self.freeze(descendants=False)
        post(actor=self.user, request=self.request(self.bulk_line(destination_location_id=self.rack.pk)))
        self.assert_reconciled()

    def test_overlapping_audit_rejected(self):
        self.freeze()
        with self.assertRaises(IntegrityError): self.freeze(self.rack)
        self.assertEqual(PhysicalInventoryAudit.objects.filter(status="COUNTING").count(), 1)

    def test_nonoverlapping_audits_allowed(self):
        self.freeze(descendants=False); self.freeze(self.rack)
        self.assertEqual(PhysicalInventoryAudit.objects.filter(status="COUNTING").count(), 2)

    def test_audit_hierarchy_freeze(self):
        self.freeze()
        with self.assertRaises(IntegrityError), transaction.atomic():
            StorageLocation.objects.filter(pk=self.rack.pk).update(parent=self.other)

    def test_audit_snapshot_and_observation_immutable(self):
        self.receive_bulk(7); audit = self.freeze()
        line = AuditLine.objects.get(audit=audit)
        self.assertEqual(line.expected_quantity, 7)
        record_count(actor=self.user, line_id=line.pk, quantity=6, condition="NEW", state="AVAILABLE")
        for change in ({"expected_quantity": 6}, {"observed_quantity": 7}):
            with self.assertRaises(IntegrityError), transaction.atomic(): AuditLine.objects.filter(pk=line.pk).update(**change)
        line.refresh_from_db()
        self.assertEqual((line.expected_quantity,line.observed_quantity), (7,6))

    def test_unauthorized_and_superuser_without_grants_denied(self):
        with self.assertRaises(AuthorizationError): post(actor=self.denied, request=self.request(self.bulk_line()))
        self.assertFalse(StockMovement.objects.exists())

    def test_self_approval_denied(self):
        request = self.request(self.bulk_line("ADJUSTMENT_IN")); request_operation(actor=self.user, request=request)
        with self.assertRaises(StockError): approve_operation(actor=self.user, operation_key=request.operation_key, reason="Self")

    def test_revoked_approval_permission_denied_at_post(self):
        request = self.request(self.bulk_line("ADJUSTMENT_IN")); self.approve(request)
        self.reviewer.user_permissions.clear()
        with self.assertRaises(AuthorizationError): post(actor=self.user, request=request)

    def test_changed_approved_payload_rejected(self):
        request = self.request(self.bulk_line("ADJUSTMENT_IN")); self.approve(request)
        with self.assertRaises(IdempotencyConflict): post(actor=self.user, request=replace(request, lines=(self.bulk_line("ADJUSTMENT_IN", 99),)))

    def test_direct_balance_mutation_blocked_at_commit(self):
        self.receive_bulk()
        with self.assertRaises(IntegrityError), transaction.atomic(): StockBalance.objects.update(quantity=999)
        self.assertEqual(StockBalance.objects.get().quantity, 10)

    def test_direct_asset_position_mutation_blocked_at_commit(self):
        asset = self.receive_asset()
        with self.assertRaises(IntegrityError), transaction.atomic(): Asset.objects.filter(pk=asset.pk).update(current_location=self.other)
        asset.refresh_from_db(); self.assertEqual(asset.current_location_id, self.location.pk)

    def test_asset_without_ledger_blocked(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Asset.objects.create(product_model=self.serialized, device_name="No receipt", current_location=self.location)

    def test_movement_without_operation_blocked(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockMovement.objects.create(product_model=self.bulk, quantity=1, operation_type="STOCK_IN",
                destination_location=self.location, actor=self.user, reason="No operation")

    def test_missing_duplicate_serials_allowed_tags_immutable(self):
        first = self.receive_asset(); second = self.receive_asset(serial_raw="duplicate"); third = self.receive_asset(serial_raw="duplicate")
        self.assertEqual(first.serial_raw, "")
        self.assertNotEqual(second.asset_tag, third.asset_tag)
        with self.assertRaises(IntegrityError), transaction.atomic(): Asset.objects.filter(pk=first.pk).update(asset_tag="OTHER")

    def test_zero_and_boolean_quantities_rejected(self):
        for quantity in (0, -1, True, 1.5):
            with self.assertRaises(StockError): post(actor=self.user, request=self.request(self.bulk_line(quantity=quantity)))

    def test_group_permissions_provisioned(self):
        call_command("provision_stock_roles", stdout=StringIO())
        from django.contrib.auth.models import Group
        self.denied.groups.add(Group.objects.get(name="Warehouse Operator"))
        post(actor=self.denied, request=self.request(self.bulk_line()))
        self.assert_reconciled()

    def test_noop_transfer_rejected(self):
        self.receive_bulk()
        with self.assertRaises(StockError): post(actor=self.user, request=self.request(self.bulk_line("TRANSFER", 1, destination_location_id=self.location.pk)))

    def test_inactive_recipient_and_location_rejected(self):
        asset = self.receive_asset()
        self.recipient.is_active=False; self.recipient.save()
        with self.assertRaises(StockError): self.issue_asset(asset)
        self.other.is_active=False; self.other.save()
        with self.assertRaises(StockError): post(actor=self.user, request=self.request(self.bulk_line(destination_location_id=self.other.pk)))

    def test_return_requires_correct_assignment(self):
        asset = self.receive_asset(); issued = self.issue_asset(asset)
        with self.assertRaises(StockError): post(actor=self.user, request=self.request(Line("RETURN", asset_id=asset.pk,
            destination_location_id=self.location.pk, reverses_id=issued.movement_ids[0])))

    def test_ledger_reconciliation_mixed_operations(self):
        self.receive_bulk(20)
        post(actor=self.user, request=self.request(self.bulk_line("TRANSFER", 5)))
        asset = self.receive_asset(); self.issue_asset(asset)
        self.assert_reconciled()

    def test_runtime_nonowner_role_retains_guards_without_ddl_or_truncate(self):
        # Role and grants exist only in this rolled-back test transaction.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("CREATE ROLE itw_phase2c_test_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS")
                cursor.execute("GRANT USAGE ON SCHEMA public TO itw_phase2c_test_runtime")
                cursor.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO itw_phase2c_test_runtime")
                cursor.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO itw_phase2c_test_runtime")
                cursor.execute("SET LOCAL ROLE itw_phase2c_test_runtime")
            self.receive_bulk()
            with self.assertRaises(IntegrityError), transaction.atomic():
                StockBalance.objects.update(quantity=999)
                with connection.cursor() as cursor: cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            from django.db import DatabaseError
            for sql in ("TRUNCATE transactions_stockmovement", "CREATE TABLE unauthorized_test(id bigint)",
                        "ALTER TABLE inventory_stockbalance DISABLE TRIGGER ALL"):
                with self.assertRaises(DatabaseError), transaction.atomic():
                    with connection.cursor() as cursor: cursor.execute(sql)
            self.assert_reconciled()
            transaction.set_rollback(True)

    def test_second_line_cannot_be_appended_to_committed_operation(self):
        result = self.receive_bulk()
        original = StockMovement.objects.get(pk=result.movement_ids[0])
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockMovement.objects.create(operation_key=result.operation_key, line_number=2, quantity=1,
                operation_type="STOCK_IN", product_model=self.bulk, destination_location=self.location,
                destination_balance_id=original.destination_balance_id, actor=self.user, reason="Test stock operation")

    def test_whitespace_approval_reason_rejected(self):
        request = self.request(self.bulk_line("ADJUSTMENT_IN")); request_operation(actor=self.user, request=request)
        with self.assertRaises(StockError): approve_operation(actor=self.reviewer, operation_key=request.operation_key, reason="   ")

    def test_wrong_custody_return_movement_blocked_in_database(self):
        asset = self.receive_asset(); self.issue_asset(asset)
        assignment = current_custody(asset.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AssetAssignment.objects.filter(pk=assignment.pk).update(return_movement=assignment.issue_movement,
                returned_at=timezone.now(), returned_by=self.user)

    def test_submitted_audit_cannot_be_unfrozen_or_counts_rewritten(self):
        self.receive_bulk(); audit = self.freeze()
        PhysicalInventoryAudit.objects.filter(pk=audit.pk).update(status="SUBMITTED", submitted_at=timezone.now())
        with self.assertRaises(IntegrityError), transaction.atomic():
            PhysicalInventoryAudit.objects.filter(pk=audit.pk).update(status="CANCELLED")
        with self.assertRaises(IntegrityError): post(actor=self.user, request=self.request(self.bulk_line("STOCK_OUT", 1)))

    def test_concurrent_audit_and_post_are_serialized(self):
        barrier = Barrier(2)
        audit = PhysicalInventoryAudit.objects.create(scope_location=self.location, planned_date=timezone.localdate(), performed_by=self.user)
        def run(freeze):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                if freeze: start_audit(actor=self.user, audit_id=audit.pk)
                else: self.receive_bulk(5)
                return "committed"
            except IntegrityError:
                return "frozen"
            finally: connections["default"].close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, [True,False]))
        self.assertEqual(results[0], "committed")
        expected = StockBalance.objects.aggregate(total=Sum("quantity"))["total"] or 0
        observed = AuditLine.objects.filter(audit=audit).values_list("expected_quantity",flat=True)
        self.assertEqual(sum(observed), expected)

    def test_cross_warehouse_parent_and_cycle_blocked_in_database(self):
        other_site = Warehouse.objects.create(code="OTHER-SITE", name="Other site")
        with self.assertRaises(IntegrityError), transaction.atomic():
            StorageLocation.objects.create(warehouse=other_site, parent=self.location, code="BAD", name="Bad", kind="SHELF")
        with self.assertRaises(IntegrityError), transaction.atomic():
            StorageLocation.objects.filter(pk=self.location.pk).update(parent=self.rack)

    def test_inactive_serialized_product_cannot_be_issued(self):
        asset = self.receive_asset()
        ProductModel.objects.filter(pk=self.serialized.pk).update(is_active=False)
        with self.assertRaises(StockError): self.issue_asset(asset)

    def test_function_security_attributes_and_search_paths(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT proname,prosecdef,proconfig FROM pg_proc WHERE proname LIKE 'itw_%'")
            rows=cursor.fetchall()
        self.assertTrue(rows)
        for name,security_definer,config in rows:
            self.assertFalse(security_definer, name)
            self.assertIn("search_path=pg_catalog, public, pg_temp", config, name)
