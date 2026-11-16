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


# Phase 4B writes are separate; the Phase 4A read-only contracts remain unchanged.
from apps.inventory import master_api
for prefix, view, name in (
    ("categories", master_api.Categories, "master-categories"),
    ("manufacturers", master_api.Manufacturers, "master-manufacturers"),
    ("product-models", master_api.Products, "master-products"),
    ("warehouses", master_api.Warehouses, "master-warehouses"),
    ("locations", master_api.Locations, "master-locations"),
    ("assets", master_api.Assets, "master-assets"),
):
    router.register("management/" + prefix, view, basename=name)

from apps.transactions import manual_api
for prefix,view,name in [("movements",manual_api.Movements,"movements"),("recipients",manual_api.Recipients,"recipients"),("assignments",manual_api.Assignments,"assignments"),("balances",manual_api.Balances,"balances")]:
    router.register("transactions/"+prefix,view,basename="manual-"+name)

urlpatterns = [
    path("transactions/manual/<str:action>/", manual_api.Command.as_view(), name="manual-command"),
    path("auth/csrf/", session_api.csrf, name="csrf"),
    path("auth/login/", session_api.sign_in, name="login"),
    path("auth/logout/", session_api.sign_out, name="logout"),
    path("auth/me/", session_api.me, name="me"),
    path("dashboard/summary/", read_api.Dashboard.as_view(), name="dashboard"),
    *router.urls,
]
