"""Real PostgreSQL transactions and competing assignment inserts."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.accounts.models import AssetRecipient
from apps.inventory.models import Asset, AssetCategory, ProductModel
from apps.transactions.models import AssetAssignment, StockMovement
from apps.warehouse.models import StorageLocation, Warehouse


class PostgreSQLTransactionTests(TransactionTestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="concurrent-operator")
        site = Warehouse.objects.create(code="TX", name="Transaction tests")
        location = StorageLocation.objects.create(warehouse=site, code="845", name="Rack", kind="RACK")
        category = AssetCategory.objects.create(code="TX", name="Category")
        product = ProductModel.objects.create(sku_code="TX", name="Serialized", category=category, tracking_mode="SERIALIZED")
        asset = Asset.objects.create(product_model=product, device_name="Unit", current_location=location)
        recipient = AssetRecipient.objects.create(code="TX", name="Recipient")
        self.ids = (user.pk, location.pk, asset.pk, recipient.pk)

    def test_competing_open_assignments_only_one_commits(self):
        barrier = Barrier(2)
        user_id, location_id, asset_id, recipient_id = self.ids

        def attempt():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                with transaction.atomic():
                    moment = timezone.now()
                    movement = StockMovement.objects.create(
                        asset_id=asset_id, quantity=1, operation_type="STOCK_OUT",
                        source_location_id=location_id, actor_id=user_id,
                        reason="Concurrent schema test", occurred_at=moment,
                    )
                    AssetAssignment.objects.create(
                        asset_id=asset_id, recipient_id=recipient_id, issued_by_id=user_id,
                        assigned_at=moment, issue_movement=movement,
                    )
                return "committed"
            except IntegrityError:
                return "rejected"
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertCountEqual(results, ["committed", "rejected"])
        self.assertEqual(AssetAssignment.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_constraint_failure_rolls_back_entire_transaction(self):
        user_id, location_id, asset_id, _ = self.ids
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StockMovement.objects.create(asset_id=asset_id, quantity=1,
                    operation_type="STOCK_OUT", source_location_id=location_id,
                    actor_id=user_id, reason="Must roll back")
                StockMovement.objects.create(asset_id=asset_id, quantity=-1,
                    operation_type="STOCK_OUT", source_location_id=location_id,
                    actor_id=user_id, reason="Invalid")
        self.assertFalse(StockMovement.objects.exists())
