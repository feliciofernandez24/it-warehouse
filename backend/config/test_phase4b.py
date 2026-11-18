"""Phase 4B mutation tests: disposable PostgreSQL and synthetic data only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import DatabaseError, transaction, connection, close_old_connections
from django.test import Client, TestCase, TransactionTestCase
from apps.audits.models import AssetChangeLog, PhysicalInventoryAudit
from apps.inventory.models import AssetCategory, Manufacturer, ProductModel, Asset, StockBalance
from apps.transactions.models import StockMovement, StockOperation
from apps.transactions.services import Line, Request, post
from apps.warehouse.models import Warehouse, StorageLocation

PREFIX = "/api/management/"
MODELS = (AssetCategory, Manufacturer, ProductModel, Warehouse, StorageLocation, Asset)


def editor(name="master-editor"):
    user = get_user_model().objects.create_user(username=name)
    for model in MODELS:
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label=model._meta.app_label, content_type__model=model._meta.model_name,
            codename__in=["view_" + model._meta.model_name, "add_" + model._meta.model_name, "change_" + model._meta.model_name]))
    return user


class MasterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = editor()
        cls.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="transactions"))
        cls.category = AssetCategory.objects.create(code="BASE", name="Base category")
        cls.manufacturer = Manufacturer.objects.create(code="BASE", name="Base manufacturer")
        cls.site = Warehouse.objects.create(code="BASE", name="Base warehouse")
        cls.other = Warehouse.objects.create(code="OTHER", name="Other warehouse")
        cls.area = StorageLocation.objects.create(code="ROOT", name="Root", warehouse=cls.site, kind="AREA")
        cls.product = ProductModel.objects.create(sku_code="BASE", name="Base model", category=cls.category,
                                                  manufacturer=cls.manufacturer, tracking_mode="SERIALIZED",
                                                  speed_value=Decimal("3200"), speed_unit="MHz")
        received = post(actor=cls.user, request=Request(uuid4(), (Line("STOCK_IN", product_model_id=cls.product.pk,
            destination_location_id=cls.area.pk, device_name="Existing asset", serial_raw="OLD-SERIAL"),), "Synthetic fixture"))
        cls.asset = Asset.objects.get(pk=received.asset_ids[0])

    def setUp(self):
        self.client.force_login(self.user)

    def create(self, resource, payload):
        return self.client.post(PREFIX + resource + "/", {"change_reason": "Synthetic creation", **payload}, content_type="application/json")

    def change(self, resource, obj, payload, version=None):
        return self.client.patch(PREFIX + resource + "/" + str(obj.pk) + "/", {
            "change_reason": "Synthetic correction", "expected_version": obj.version if version is None else version, **payload}, content_type="application/json")

    def test_anonymous_and_read_only_actors_cannot_write(self):
        self.client.logout()
        self.assertEqual(self.create("categories", {"code": "NEW", "name": "New"}).status_code, 401)
        reader = get_user_model().objects.create_user(username="reader")
        reader.user_permissions.add(Permission.objects.get(codename="view_assetcategory"))
        self.client.force_login(reader)
        self.assertEqual(self.create("categories", {"code": "NEW", "name": "New"}).status_code, 403)
        self.assertEqual(self.change("categories", self.category, {"name": "bad"}).status_code, 403)
        self.assertEqual(AssetChangeLog.objects.count(), 0)

    def test_each_master_can_create_with_existing_fields(self):
        cases = {
            "categories": {"code": "CAT", "name": "Category"},
            "manufacturers": {"code": "MFR", "name": "Manufacturer"},
            "product-models": {"sku_code": "MODEL", "name": "Product", "category": self.category.pk,
                               "manufacturer": self.manufacturer.pk, "tracking_mode": "BULK"},
            "warehouses": {"code": "WH", "name": "Warehouse", "address": "Synthetic address"},
            "locations": {"code": "CHILD", "name": "Shelf", "warehouse": self.site.pk, "parent": self.area.pk, "kind": "SHELF"},
        }
        for resource, payload in cases.items():
            with self.subTest(resource=resource):
                response = self.create(resource, payload)
                self.assertEqual(response.status_code, 201, response.content)
                self.assertEqual(response.json()["version"], 0)
        self.assertEqual(AssetChangeLog.objects.count(), 5)
        self.assertTrue(all(e.actor_id == self.user.pk and e.action == "MASTER_CREATE" for e in AssetChangeLog.objects.all()))

    def test_each_master_can_edit_and_audit(self):
        for resource, obj in (("categories", self.category), ("manufacturers", self.manufacturer),
                              ("product-models", self.product), ("warehouses", self.site), ("locations", self.area)):
            original_name = obj.name
            response = self.change(resource, obj, {"name": "Corrected"})
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()["version"], 1)
            obj.refresh_from_db()
            self.assertEqual(obj.name, "Corrected")
            event = AssetChangeLog.objects.get(entity_kind=obj._meta.label_lower, entity_pk=obj.pk)
            self.assertEqual(event.actor_id, self.user.pk)
            self.assertEqual(event.before["name"], original_name)
            self.assertEqual(event.after["name"], "Corrected")
            self.assertIn("name", event.after["changed_fields"])

    def test_codes_are_normalized_and_unique(self):
        self.assertEqual(self.create("categories", {"code": " mixed ", "name": "Good"}).json()["code"], "MIXED")
        self.assertEqual(self.create("categories", {"code": "mixed", "name": "Duplicate"}).status_code, 400)
        self.assertEqual(self.create("manufacturers", {"code": "BASE", "name": "Duplicate"}).status_code, 400)
        self.assertEqual(self.create("warehouses", {"code": "BASE", "name": "Duplicate"}).status_code, 400)

    def test_product_sku_duplicate_and_invalid_choices(self):
        payload = {"sku_code": "BASE", "name": "Duplicate", "category": self.category.pk, "tracking_mode": "SERIALIZED"}
        self.assertEqual(self.create("product-models", payload).status_code, 400)
        payload.update(sku_code="NEW", tracking_mode="INVALID")
        self.assertEqual(self.create("product-models", payload).status_code, 400)

    def test_location_duplicate_is_per_warehouse(self):
        data = {"code": "ROOT", "name": "Root", "warehouse": self.site.pk, "kind": "AREA"}
        self.assertEqual(self.create("locations", data).status_code, 400)
        data["warehouse"] = self.other.pk
        self.assertEqual(self.create("locations", data).status_code, 201)

    def test_invalid_foreign_keys_and_inactive_targets(self):
        self.assertEqual(self.create("product-models", {"sku_code": "NEW", "name": "New", "category": 9999999,
                                                       "tracking_mode": "BULK"}).status_code, 400)
        self.assertEqual(self.create("locations", {"code": "NEW", "name": "New", "warehouse": 9999999, "kind": "AREA"}).status_code, 400)
        self.manufacturer.is_active = False
        self.manufacturer.save(update_fields=["is_active"])
        self.assertEqual(self.create("product-models", {"sku_code": "NEW", "name": "New", "category": self.category.pk,
            "manufacturer": self.manufacturer.pk, "tracking_mode": "BULK"}).status_code, 400)

    def test_related_lookup_permissions(self):
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label="inventory", codename="view_manufacturer"))
        response = self.create("product-models", {"sku_code": "NEW", "name": "New", "category": self.category.pk,
            "manufacturer": self.manufacturer.pk, "tracking_mode": "BULK"})
        self.assertEqual(response.status_code, 403)

    def test_location_hierarchy_validation(self):
        self.assertEqual(self.change("locations", self.area, {"parent": self.area.pk}).status_code, 400)
        self.assertEqual(self.create("locations", {"code": "BAD", "name": "Bad", "warehouse": self.other.pk,
                                                  "parent": self.area.pk, "kind": "SHELF"}).status_code, 400)
        self.assertEqual(self.create("locations", {"code": "BAD", "name": "Bad", "warehouse": self.site.pk, "kind": "BIN"}).status_code, 400)

    def test_occupied_location_guard_is_not_bypassed(self):
        response = self.change("locations", self.area, {"warehouse": self.other.pk})
        self.assertEqual(response.status_code, 409)
        self.area.refresh_from_db()
        self.assertEqual(self.area.warehouse_id, self.site.pk)
        self.assertEqual(AssetChangeLog.objects.count(), 0)

    def test_referenced_tracking_mode_guard(self):
        self.assertEqual(self.change("product-models", self.product, {"tracking_mode": "BULK"}).status_code, 409)
        self.product.refresh_from_db()
        self.assertEqual(self.product.tracking_mode, "SERIALIZED")
        self.assertEqual(AssetChangeLog.objects.count(), 0)

    def test_existing_identifiers_are_immutable(self):
        for resource, obj, field in (("categories", self.category, "code"), ("warehouses", self.site, "code"),
                                     ("product-models", self.product, "sku_code"), ("locations", self.area, "code")):
            self.assertEqual(self.change(resource, obj, {field: "CHANGED"}).status_code, 400)

    def test_expected_version_prevents_lost_update(self):
        self.assertEqual(self.change("categories", self.category, {"name": "First"}).status_code, 200)
        response = self.change("categories", self.category, {"name": "Stale"}, version=0)
        self.assertEqual(response.status_code, 409)
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "First")
        self.assertEqual(AssetChangeLog.objects.count(), 1)

    def test_reason_and_version_required_and_no_mass_assignment(self):
        path = PREFIX + "categories/" + str(self.category.pk) + "/"
        for payload in ({"name": "bad"}, {"name": "bad", "change_reason": "reason"},
                        {"name": "bad", "change_reason": " ", "expected_version": 0},
                        {"name": "bad", "change_reason": "reason", "expected_version": 0, "actor": 999}):
            self.assertEqual(self.client.patch(path, payload, content_type="application/json").status_code, 400)
        self.assertEqual(self.create("categories", {"code": "BAD!", "name": "Bad"}).status_code, 400)

    @patch("apps.inventory.master_service.AssetChangeLog.objects.create", side_effect=DatabaseError("private diagnostic"))
    def test_audit_failure_rolls_back_create(self, _audit):
        response = self.create("categories", {"code": "ROLLBACK", "name": "Rollback"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private diagnostic", str(response.content))
        self.assertFalse(AssetCategory.objects.filter(code="ROLLBACK").exists())

    @patch("apps.inventory.master_service.AssetChangeLog.objects.create", side_effect=DatabaseError)
    def test_audit_failure_rolls_back_update(self, _audit):
        self.assertEqual(self.change("categories", self.category, {"name": "Rollback"}).status_code, 503)
        self.category.refresh_from_db()
        self.assertEqual((self.category.name, self.category.version), ("Base category", 0))

    def test_audit_records_are_immutable_and_minimize_free_text(self):
        response = self.change("warehouses", self.site, {"address": "Do not copy this private text"})
        self.assertEqual(response.status_code, 200)
        event = AssetChangeLog.objects.get()
        self.assertNotIn("address", event.after)
        self.assertIn("address", event.after["changed_fields"])
        with self.assertRaises(DatabaseError), transaction.atomic():
            AssetChangeLog.objects.filter(pk=event.pk).update(reason="rewrite")

    def test_asset_metadata_edit_does_not_create_movements(self):
        before = (StockMovement.objects.count(), StockOperation.objects.count(), StockBalance.objects.count())
        response = self.change("assets", self.asset, {"device_name": "Corrected name", "serial_raw": " New Serial "})
        self.assertEqual(response.status_code, 200, response.content)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.serial_normalized, "new serial")
        self.assertEqual(self.asset.serial_review_state, "UNREVIEWED")
        self.assertEqual(before, (StockMovement.objects.count(), StockOperation.objects.count(), StockBalance.objects.count()))
        event = AssetChangeLog.objects.get()
        self.assertEqual(event.asset_id, self.asset.pk)
        self.assertNotIn("serial_raw", event.before)
        self.assertNotIn("serial_normalized", event.after)
        self.assertIn("serial_raw", event.after["changed_fields"])

    def test_asset_position_product_tag_and_state_are_not_editable(self):
        for field, value in (("asset_tag", "bad"), ("product_model_id", 99), ("product_model", 99),
                             ("current_location_id", self.area.pk), ("condition", "BROKEN"),
                             ("lifecycle_status", "LOST"), ("serial_normalized", "forged")):
            self.assertEqual(self.change("assets", self.asset, {field: value}).status_code, 400)

    def test_asset_registration_requires_separate_receipt_workflow(self):
        before = (Asset.objects.count(), StockMovement.objects.count(), AssetChangeLog.objects.count())
        response = self.create("assets", {"product_model": self.product.pk, "current_location": self.area.pk,
                                          "device_name": "Prohibited new asset", "serial_raw": "TEST"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "ASSET_REGISTRATION_REQUIRES_RECEIPT")
        self.assertEqual(before, (Asset.objects.count(), StockMovement.objects.count(), AssetChangeLog.objects.count()))

    def test_asset_serial_details_require_editor_permission(self):
        reader = get_user_model().objects.create_user(username="asset-reader")
        reader.user_permissions.add(Permission.objects.get(content_type__app_label="inventory", codename="view_asset"))
        self.client.force_login(reader)
        self.assertEqual(self.client.get("/api/inventory/assets/" + str(self.asset.pk) + "/").status_code, 200)
        self.assertEqual(self.client.get(PREFIX + "assets/" + str(self.asset.pk) + "/").status_code, 403)

    def test_csrf_is_required_for_authenticated_create_and_edit(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        payload = {"code": "CSRF", "name": "CSRF", "change_reason": "test"}
        self.assertEqual(client.post(PREFIX + "categories/", payload, content_type="application/json").status_code, 403)
        token = client.get("/api/auth/csrf/").json()["csrfToken"]
        self.assertEqual(client.post(PREFIX + "categories/", payload, content_type="application/json", HTTP_X_CSRFTOKEN=token).status_code, 201)
        self.assertEqual(client.patch(PREFIX + "categories/" + str(self.category.pk) + "/", {
            "name": "No CSRF", "expected_version": 0, "change_reason": "test"}, content_type="application/json").status_code, 403)

    def test_permissions_are_revoked_on_next_request(self):
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label="inventory", codename="change_assetcategory"))
        self.assertEqual(self.change("categories", self.category, {"name": "Denied"}).status_code, 403)

    def test_delete_requires_permission_and_no_legacy_write_routes(self):
        for resource, obj in (("categories", self.category), ("assets", self.asset), ("warehouses", self.site)):
            self.assertEqual(self.client.delete(PREFIX + resource + "/" + str(obj.pk) + "/").status_code, 405 if resource=="assets" else 403)
        self.assertEqual(self.client.post("/api/inventory/categories/", {}, content_type="application/json").status_code, 405)
        self.assertEqual(self.client.post("/api/stock/post/", {}, content_type="application/json").status_code, 404)

    def test_management_reads_keep_pagination_filters_and_detail(self):
        self.assertEqual(self.client.get(PREFIX + "warehouses/" + str(self.site.pk) + "/").json()["name"], "Base warehouse")
        data = self.client.get(PREFIX + "locations/?warehouse=" + str(self.site.pk)).json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(self.client.get(PREFIX + "categories/?search=Base&page_size=1").json()["count"], 1)
        self.assertEqual(self.client.get(PREFIX + "categories/9999999/").status_code, 404)



    def test_existing_inactive_association_can_be_retained_but_not_newly_selected(self):
        self.category.is_active = False
        self.category.save(update_fields=["is_active"])
        response = self.change("product-models", self.product, {"name": "Retained category", "category": self.category.pk})
        self.assertEqual(response.status_code, 200, response.content)
        response = self.create("product-models", {"sku_code": "INACTIVE", "name": "New", "category": self.category.pk, "tracking_mode": "BULK"})
        self.assertEqual(response.status_code, 400)

    def test_current_user_exposes_existing_master_grants_without_review_grants(self):
        data = self.client.get("/api/auth/me/").json()["user"]["permissions"]
        self.assertIn("inventory.add_assetcategory", data)
        self.assertIn("warehouse.change_storagelocation", data)
        self.assertFalse(any("import" in permission for permission in data))


class MasterConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = editor("concurrent-editor")
        self.category = AssetCategory.objects.create(code="RACE", name="Original")

    def race(self, action):
        barrier = Barrier(2)
        def task(n):
            close_old_connections()
            try:
                client = Client()
                client.force_login(get_user_model().objects.get(pk=self.user.pk))
                barrier.wait(timeout=5)
                return action(client, n).status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(task, n) for n in range(2)]
            return sorted(f.result(timeout=15) for f in futures)

    def test_concurrent_edits_one_commit_one_conflict(self):
        statuses = self.race(lambda c, n: c.patch(PREFIX + "categories/" + str(self.category.pk) + "/",
            {"name": "Edit " + str(n), "expected_version": 0, "change_reason": "race"}, content_type="application/json"))
        self.assertEqual(statuses, [200, 409])
        self.assertEqual(AssetChangeLog.objects.count(), 1)

    def test_concurrent_duplicate_creation_is_serialized(self):
        statuses = self.race(lambda c, n: c.post(PREFIX + "categories/",
            {"code": "DUPLICATE", "name": "Create " + str(n), "change_reason": "race"}, content_type="application/json"))
        self.assertEqual(statuses, [201, 400])
        self.assertEqual(AssetCategory.objects.filter(code="DUPLICATE").count(), 1)
        self.assertEqual(AssetChangeLog.objects.count(), 1)
