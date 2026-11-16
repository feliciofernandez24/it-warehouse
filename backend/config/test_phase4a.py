"""HTTP/security tests: synthetic fixtures, disposable PostgreSQL only."""
import json
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.sessions.models import Session
from django.core.cache import caches
from django.db import DatabaseError, transaction, connection
from django.test import Client, TestCase, override_settings
from apps.inventory.models import Asset, AssetCategory, Manufacturer, ProductModel, StockBalance, StockThreshold, ImportReviewEvent
from apps.warehouse.models import Warehouse, StorageLocation
from apps.transactions.models import StockMovement
from apps.transactions.services import Line, Request, post


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
class AuthenticationTests(TestCase):
    def setUp(self):
        caches["login"].clear()
        self.user = get_user_model().objects.create_user(username="reader", password="test-only-password")
        self.client = Client(enforce_csrf_checks=True)

    def token(self):
        return self.client.get("/api/auth/csrf/").json()["csrfToken"]

    def signin(self, **extra):
        return self.client.post("/api/auth/login/", {"username": "reader", "password": "test-only-password"},
                                content_type="application/json", HTTP_X_CSRFTOKEN=self.token(), **extra)

    def test_login_me_and_private_cookies(self):
        response = self.signin()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").json()["user"]["username"], "reader")
        self.assertTrue(response.cookies["sessionid"]["httponly"])
        self.assertEqual(response.cookies["sessionid"]["samesite"], "Lax")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotIn("password", response.json()["user"])
        self.assertNotIn("email", response.json()["user"])

    def test_anonymous_login_requires_csrf(self):
        self.assertEqual(self.client.post("/api/auth/login/", {}, content_type="application/json").status_code, 403)
        self.assertFalse(self.client.get("/api/auth/csrf/").cookies["csrftoken"]["secure"])

    def test_bad_origin_is_denied(self):
        token = self.token()
        response = self.client.post("/api/auth/login/", {}, content_type="application/json",
                                    HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://evil.invalid")
        self.assertEqual(response.status_code, 403)

    def test_invalid_credentials_do_not_disclose_account(self):
        token = self.token()
        for username in ("reader", "missing"):
            response = self.client.post("/api/auth/login/", {"username": username, "password": "wrong"},
                                        content_type="application/json", HTTP_X_CSRFTOKEN=token)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json(), {"detail": "Invalid username or password."})

    def test_inactive_user_denied(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.signin().status_code, 401)

    def test_logout_flushes_session_and_requires_csrf(self):
        self.signin()
        key = self.client.cookies["sessionid"].value
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 403)
        self.assertEqual(self.client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=self.token()).status_code, 200)
        self.assertFalse(Session.objects.filter(session_key=key).exists())
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_login_rotates_session_and_csrf(self):
        session = self.client.session
        session["prelogin"] = True
        session.save()
        old = session.session_key
        token = self.token()
        response = self.client.post("/api/auth/login/", {"username": "reader", "password": "test-only-password"},
                                    content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(self.client.cookies["sessionid"].value, old)
        self.assertFalse(Session.objects.filter(session_key=old).exists())
        self.assertEqual(self.client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=token).status_code, 403)

    def test_anonymous_me_and_unsupported_methods(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        self.assertEqual(self.client.get("/api/auth/login/").status_code, 405)
        self.assertEqual(self.client.get("/api/auth/logout/").status_code, 405)

    def test_malformed_payloads(self):
        for value in ("[]", "null", "{", '{"username":1,"password":"x"}'):
            self.assertEqual(self.client.post("/api/auth/login/", value, content_type="application/json",
                                             HTTP_X_CSRFTOKEN=self.token()).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/login/", {}, HTTP_X_CSRFTOKEN=self.token()).status_code, 415)

    def test_account_throttle_across_peer_addresses(self):
        token = self.token()
        for n in range(5):
            response = self.client.post("/api/auth/login/", {"username": "reader", "password": "wrong"},
                                        content_type="application/json", HTTP_X_CSRFTOKEN=token, REMOTE_ADDR="192.0.2." + str(n))
            self.assertEqual(response.status_code, 401)
        self.assertEqual(self.signin().status_code, 429)

    @override_settings(LOGIN_PEER_LIMIT=2)
    def test_peer_throttle_ignores_spoofed_forwarding_header(self):
        for n in range(3):
            response = self.client.post("/api/auth/login/", {"username": "absent" + str(n), "password": "wrong"},
                                        content_type="application/json", HTTP_X_CSRFTOKEN=self.token(),
                                        HTTP_X_FORWARDED_FOR="192.0.2." + str(n))
        self.assertEqual(response.status_code, 429)

    @patch("apps.accounts.session_api.budget", side_effect=RuntimeError)
    def test_throttle_failure_is_closed(self, _budget):
        self.assertEqual(self.signin().status_code, 503)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    @override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
    def test_secure_cookie_flags_are_configurable(self):
        response = self.signin()
        self.assertTrue(response.cookies["sessionid"]["secure"])
        self.assertTrue(response.cookies["csrftoken"]["secure"])


class ReadApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="catalog-reader")
        cls.user.user_permissions.add(*Permission.objects.filter(codename__startswith="view_"))
        cls.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="transactions"))
        cls.category = AssetCategory.objects.create(code="TEST", name="Test category")
        cls.manufacturer = Manufacturer.objects.create(code="MAKER", name="Test manufacturer")
        cls.product = ProductModel.objects.create(sku_code="SERVER", name="Server model", category=cls.category,
                                                  manufacturer=cls.manufacturer, tracking_mode="SERIALIZED")
        cls.bulk = ProductModel.objects.create(sku_code="PART", name="Bulk part", category=cls.category, tracking_mode="BULK")
        cls.site = Warehouse.objects.create(code="SITE", name="Test warehouse")
        cls.empty_site = Warehouse.objects.create(code="EMPTY", name="Empty warehouse")
        cls.location = StorageLocation.objects.create(code="AREA", name="Test area", warehouse=cls.site, kind="AREA")
        received = post(actor=cls.user, request=Request(uuid4(), tuple(Line("STOCK_IN", product_model_id=cls.product.pk,
            destination_location_id=cls.location.pk, device_name=name) for name in ("Server Alpha", "Server Beta")),
            "Synthetic catalog test fixtures"))
        cls.asset = Asset.objects.get(pk=received.asset_ids[0])
        cls.other = Asset.objects.get(pk=received.asset_ids[1])

    def setUp(self):
        self.client.force_login(self.user)

    def test_anonymous_reads_are_rejected(self):
        self.client.logout()
        for path in ("inventory/assets", "inventory/categories", "inventory/manufacturers",
                     "inventory/product-models", "warehouses", "locations", "dashboard/summary"):
            self.assertEqual(self.client.get("/api/" + path + "/").status_code, 401, path)

    def test_authenticated_lists_are_paginated(self):
        for path in ("inventory/assets", "inventory/categories", "inventory/manufacturers",
                     "inventory/product-models", "warehouses", "locations"):
            response = self.client.get("/api/" + path + "/")
            self.assertEqual(response.status_code, 200, response.content)
            self.assertIn("results", response.json())
            self.assertIn("no-store", response["Cache-Control"])

    def test_pagination_search_filter_and_order(self):
        result = self.client.get("/api/inventory/assets/?page_size=1&ordering=-device_name").json()
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["results"][0]["device_name"], "Server Beta")
        self.assertIsNotNone(result["next"])
        self.assertEqual(self.client.get("/api/inventory/assets/?search=Alpha").json()["count"], 1)
        self.assertEqual(self.client.get("/api/inventory/assets/?warehouse=" + str(self.empty_site.pk)).json()["count"], 0)
        self.assertEqual(self.client.get("/api/inventory/product-models/?tracking_mode=BULK").json()["count"], 1)

    def test_malformed_filters_fail_safely(self):
        for query in ("warehouse=x", "category=-1", "category=" + "9"*5000, "lifecycle_status=INVALID"):
            self.assertEqual(self.client.get("/api/inventory/assets/?" + query).status_code, 400)
        self.assertEqual(self.client.get("/api/warehouses/?is_active=yes").status_code, 400)

    def test_asset_detail_minimizes_data(self):
        response = self.client.get("/api/inventory/assets/" + str(self.asset.pk) + "/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["product_name"], "Server model")
        for field in ("serial_raw", "remarks", "description", "import_rows"):
            self.assertNotIn(field, response.json())
        self.assertEqual(self.client.get("/api/inventory/assets/999999999/").status_code, 404)

    def test_model_permissions_and_revocation(self):
        user = get_user_model().objects.create_user(username="no-views")
        self.client.force_login(user)
        self.assertEqual(self.client.get("/api/inventory/assets/").status_code, 403)
        grant = Permission.objects.get(content_type__app_label="inventory", codename="view_asset")
        user.user_permissions.add(grant)
        self.assertEqual(self.client.get("/api/inventory/assets/").status_code, 200)
        user.user_permissions.remove(grant)
        self.assertEqual(self.client.get("/api/inventory/assets/").status_code, 403)

    def test_warehouse_and_location_detail(self):
        self.assertEqual(self.client.get("/api/warehouses/" + str(self.site.pk) + "/").status_code, 200)
        data = self.client.get("/api/warehouses/" + str(self.site.pk) + "/locations/").json()
        self.assertEqual(data["results"][0]["code"], "AREA")
        self.assertEqual(self.client.get("/api/warehouses/" + str(self.empty_site.pk) + "/locations/").json()["results"], [])
        self.assertEqual(self.client.get("/api/warehouses/999999999/locations/").status_code, 404)
        self.assertEqual(self.client.get("/api/locations/?warehouse=" + str(self.site.pk)).json()["count"], 1)

    def test_nested_locations_require_both_permissions(self):
        user = get_user_model().objects.create_user(username="site-reader")
        user.user_permissions.add(Permission.objects.get(content_type__app_label="warehouse", codename="view_warehouse"))
        self.client.force_login(user)
        self.assertEqual(self.client.get("/api/warehouses/" + str(self.site.pk) + "/locations/").status_code, 403)

    def test_write_methods_do_not_change_records(self):
        before = (Asset.objects.count(), Warehouse.objects.count(), StockMovement.objects.count(), ImportReviewEvent.objects.count())
        for path in ("inventory/assets/", "inventory/assets/" + str(self.asset.pk) + "/", "warehouses/", "warehouses/" + str(self.site.pk) + "/", "locations/"):
            for method in ("post", "put", "patch", "delete"):
                self.assertEqual(getattr(self.client, method)("/api/" + path, {}, content_type="application/json").status_code, 405)
        self.assertEqual(before, (Asset.objects.count(), Warehouse.objects.count(), StockMovement.objects.count(), ImportReviewEvent.objects.count()))

    def test_evidence_and_operational_routes_are_absent(self):
        for path in ("inventory/import-batches", "inventory/review-events", "inventory/capture", "review/approve", "stock/post"):
            self.assertEqual(self.client.get("/api/" + path + "/").status_code, 404)

    def test_dashboard_real_stock_metrics_and_sanitized_activity(self):
        post(actor=self.user, request=Request(uuid4(), (Line("STOCK_IN", quantity=5, product_model_id=self.bulk.pk,
             destination_location_id=self.location.pk),), "Synthetic test only"))
        StockThreshold.objects.create(product_model=self.bulk, warehouse=self.site, minimum_quantity=6)
        StockThreshold.objects.create(product_model=self.bulk, warehouse=self.empty_site, minimum_quantity=2)
        result = self.client.get("/api/dashboard/summary/").json()
        self.assertEqual(result["total_assets"], 2)
        self.assertEqual(result["stock_totals"], {"all": 5, "available": 5})
        self.assertEqual(result["low_stock_count"], 2)
        self.assertEqual({r["available_quantity"] for r in result["low_stock"]}, {0, 5})
        self.assertEqual(set(result["recent_activity"][0]), {"id", "operation_type", "quantity", "recorded_at"})

    def test_dashboard_permissions(self):
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label="inventory", codename="view_stockthreshold"))
        self.assertEqual(self.client.get("/api/dashboard/summary/").status_code, 403)

    def test_guard_still_rejects_direct_balance_changes(self):
        post(actor=self.user, request=Request(uuid4(), (Line("STOCK_IN", quantity=5, product_model_id=self.bulk.pk,
             destination_location_id=self.location.pk),), "Synthetic test only"))
        with self.assertRaises(DatabaseError), transaction.atomic():
            StockBalance.objects.update(quantity=99)
            with connection.cursor() as c:
                c.execute("SET CONSTRAINTS ALL IMMEDIATE")



    def test_related_loading_stays_bounded(self):
        from django.test.utils import CaptureQueriesContext
        post(actor=self.user, request=Request(uuid4(), tuple(Line("STOCK_IN", product_model_id=self.product.pk,
             destination_location_id=self.location.pk, device_name="Query test " + str(n)) for n in range(20)),
             "Synthetic query-bound fixture"))
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/inventory/assets/?page_size=100")
            self.assertEqual(len(response.json()["results"]), 22)
        self.assertLessEqual(len(queries), 9)

    @override_settings(API_PAGE_SIZE=1)
    def test_page_size_is_configurable(self):
        self.assertEqual(len(self.client.get("/api/inventory/assets/").json()["results"]), 1)


class EmptyDashboardTests(TestCase):
    def test_empty_metrics_and_activity_permission(self):
        user = get_user_model().objects.create_user(username="empty-reader")
        user.user_permissions.add(*Permission.objects.filter(codename__startswith="view_").exclude(content_type__app_label="transactions"))
        self.client.force_login(user)
        response = self.client.get("/api/dashboard/summary/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual((data["total_assets"], data["total_warehouses"], data["total_categories"]), (0, 0, 0))
        self.assertEqual(data["stock_totals"], {"all": 0, "available": 0})
        self.assertEqual(data["low_stock"], [])
        self.assertEqual(data["recent_activity"], [])
        self.assertFalse(data["recent_activity_permitted"])
