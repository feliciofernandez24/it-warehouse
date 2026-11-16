"""Separate management routes preserve every Phase 4A read-only endpoint."""
from django.db import DatabaseError, IntegrityError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from . import master_serializers as s, read_api as reads
from .master_service import Conflict, Unavailable, mutate


class MasterPermission(BasePermission):
    def has_permission(self, request, view):
        model = view.queryset.model
        opts = model._meta
        permissions = [f"{opts.app_label}.view_{opts.model_name}"]
        if request.method in ("POST", "PUT", "PATCH"):
            permissions.append(f"{opts.app_label}.{'add' if request.method == 'POST' else 'change'}_{opts.model_name}")
        # Editing asset metadata contains serials/notes excluded from ordinary asset reads.
        if opts.model_name == "asset" and request.method in ("GET", "HEAD"):
            permissions.append("inventory.change_asset")
        return request.user.is_authenticated and request.user.is_active and all(request.user.has_perm(p) for p in permissions)


class Managed:
    parser_classes = (JSONParser,)
    permission_classes = (IsAuthenticated, MasterPermission)
    http_method_names = ("get", "post", "put", "patch", "head", "options")
    related_permissions = {}

    def get_serializer_class(self):
        return self.registration_serializer if self.action == "create" and hasattr(self, "registration_serializer") else self.management_serializer

    def related(self):
        if not isinstance(self.request.data, dict):
            return ()
        return tuple(permission for key, permission in self.related_permissions.items() if self.request.data.get(key) is not None)

    def change(self, request, pk=None, partial=False):
        try:
            record = mutate(actor=request.user, model=self.queryset.model, serializer_class=self.get_serializer_class(),
                            data=request.data, pk=pk, partial=partial, related=self.related())
        except IntegrityError:
            raise Conflict("The change violates a uniqueness, hierarchy or stock-integrity rule. No changes were committed.") from None
        except DatabaseError:
            raise Unavailable() from None
        return Response(self.management_serializer(record).data, status=201 if pk is None else 200)

    def create(self, request, *args, **kwargs):
        return self.change(request)

    def update(self, request, *args, **kwargs):
        return self.change(request, pk=kwargs.get("pk"), partial=kwargs.pop("partial", False))

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)


class Categories(Managed, reads.Categories):
    management_serializer = s.Category


class Manufacturers(Managed, reads.Manufacturers):
    management_serializer = s.ManufacturerData


class Products(Managed, reads.Products):
    management_serializer = s.Product
    related_permissions = {"category": "inventory.view_assetcategory", "manufacturer": "inventory.view_manufacturer"}


class Warehouses(Managed, reads.Warehouses):
    management_serializer = s.WarehouseData


class Locations(Managed, reads.Locations):
    management_serializer = s.Location
    related_permissions = {"warehouse": "warehouse.view_warehouse", "parent": "warehouse.view_storagelocation"}


class Assets(Managed, reads.Assets):
    management_serializer = s.AssetMetadata
    registration_serializer = s.AssetRegistration
    related_permissions = {"product_model": "inventory.view_productmodel", "current_location": "warehouse.view_storagelocation"}
