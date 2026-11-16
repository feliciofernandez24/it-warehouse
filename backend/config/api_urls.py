from django.urls import path
from rest_framework.routers import SimpleRouter
from apps.accounts import session_api
from apps.inventory import read_api

router = SimpleRouter()
for prefix, view, name in (
    ("inventory/assets", read_api.Assets, "assets"),
    ("inventory/categories", read_api.Categories, "categories"),
    ("inventory/manufacturers", read_api.Manufacturers, "manufacturers"),
    ("inventory/product-models", read_api.Products, "products"),
    ("warehouses", read_api.Warehouses, "warehouses"),
    ("locations", read_api.Locations, "locations"),
):
    router.register(prefix, view, basename=name)

urlpatterns = [
    path("auth/csrf/", session_api.csrf, name="csrf"),
    path("auth/login/", session_api.sign_in, name="login"),
    path("auth/logout/", session_api.sign_out, name="logout"),
    path("auth/me/", session_api.me, name="me"),
    path("dashboard/summary/", read_api.Dashboard.as_view(), name="dashboard"),
    *router.urls,
]
