"""Explicit, permission-gated catalog reads. Import/review models are never serialized."""
from django.conf import settings
from django.db.models import BigIntegerField, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import filters, serializers, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.inventory.models import Asset, AssetCategory, Manufacturer, ProductModel, StockBalance, StockThreshold
from apps.transactions.models import StockMovement
from apps.warehouse.models import Warehouse, StorageLocation


class SessionAuth(SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"


class ViewPermission(BasePermission):
    def has_permission(self, request, view):
        model = view.queryset.model
        return request.user.has_perm(f"{model._meta.app_label}.view_{model._meta.model_name}")


class Pages(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_page_size(self, request):
        self.page_size = settings.API_PAGE_SIZE
        return super().get_page_size(request)


class AssetSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product_model.name", read_only=True)
    sku_code = serializers.CharField(source="product_model.sku_code", read_only=True)
    category_name = serializers.CharField(source="product_model.category.name", read_only=True)
    location_name = serializers.CharField(source="current_location.name", read_only=True, default=None)

    class Meta:
        model = Asset
        fields = ("id", "asset_tag", "device_name", "product_model_id", "product_name", "sku_code",
                  "category_name", "condition", "lifecycle_status", "current_location_id", "location_name")


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetCategory
        fields = ("id", "code", "name", "description", "is_active")


class ManufacturerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Manufacturer
        fields = ("id", "code", "name", "description", "is_active")


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    manufacturer_name = serializers.CharField(source="manufacturer.name", read_only=True, default=None)

    class Meta:
        model = ProductModel
        fields = ("id", "sku_code", "name", "category_id", "category_name", "manufacturer_id",
                  "manufacturer_name", "model_number", "tracking_mode", "is_active")


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ("id", "code", "name", "address", "is_active")


class LocationSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = StorageLocation
        fields = ("id", "warehouse_id", "warehouse_name", "parent_id", "code", "name", "kind", "is_active")


class PrivateResponses:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class ReadOnly(PrivateResponses, viewsets.ReadOnlyModelViewSet):
    authentication_classes = (SessionAuth,)
    permission_classes = (IsAuthenticated, ViewPermission)
    pagination_class = Pages
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    ordering = ("id",)
    ordering_fields = ("id", "name")
    exact_filters = {}

    def get_queryset(self):
        qs = super().get_queryset()
        for parameter, (field, kind) in self.exact_filters.items():
            value = self.request.query_params.get(parameter)
            if value is None or value == "":
                continue
            if kind == "id":
                if len(value) > 19 or not value.isascii() or not value.isdecimal() or not 0 < int(value) < 2**63:
                    raise ValidationError({parameter: "Use a positive integer."})
                value = int(value)
            elif kind == "bool":
                if value not in ("true", "false"):
                    raise ValidationError({parameter: "Use true or false."})
                value = value == "true"
            elif value not in kind:
                raise ValidationError({parameter: "Invalid choice."})
            qs = qs.filter(**{field: value})
        return qs


class Assets(ReadOnly):
    queryset = Asset.objects.select_related("product_model__category", "current_location")
    serializer_class = AssetSerializer
    search_fields = ("asset_tag", "device_name", "product_model__sku_code", "product_model__name")
    ordering_fields = ("id", "asset_tag", "device_name", "created_at")
    exact_filters = {"category": ("product_model__category_id", "id"),
                     "product_model": ("product_model_id", "id"),
                     "warehouse": ("current_location__warehouse_id", "id"),
                     "lifecycle_status": ("lifecycle_status", ("AVAILABLE", "QUARANTINED", "ASSIGNED", "DISPOSED", "LOST"))}


class Categories(ReadOnly):
    queryset = AssetCategory.objects.all()
    serializer_class = CategorySerializer
    search_fields = ("name", "code")
    exact_filters = {"is_active": ("is_active", "bool")}


class Manufacturers(ReadOnly):
    queryset = Manufacturer.objects.all()
    serializer_class = ManufacturerSerializer
    search_fields = ("name", "code")
    exact_filters = {"is_active": ("is_active", "bool")}


class Products(ReadOnly):
    queryset = ProductModel.objects.select_related("category", "manufacturer")
    serializer_class = ProductSerializer
    search_fields = ("name", "sku_code", "model_number")
    ordering_fields = ("id", "name", "sku_code")
    exact_filters = {"category": ("category_id", "id"), "manufacturer": ("manufacturer_id", "id"),
                     "tracking_mode": ("tracking_mode", ("BULK", "SERIALIZED")), "is_active": ("is_active", "bool")}


class Warehouses(ReadOnly):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    search_fields = ("name", "code")
    exact_filters = {"is_active": ("is_active", "bool")}

    @action(detail=True, methods=["get"])
    def locations(self, request, pk=None):
        warehouse = self.get_object()
        if not request.user.has_perm("warehouse.view_storagelocation"):
            self.permission_denied(request)
        qs = StorageLocation.objects.filter(warehouse=warehouse).select_related("warehouse").order_by("id")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(LocationSerializer(page, many=True).data)


class Locations(ReadOnly):
    queryset = StorageLocation.objects.select_related("warehouse")
    serializer_class = LocationSerializer
    search_fields = ("name", "code", "warehouse__name")
    exact_filters = {"warehouse": ("warehouse_id", "id"), "is_active": ("is_active", "bool")}


class Dashboard(PrivateResponses, APIView):
    authentication_classes = (SessionAuth,)
    permission_classes = (IsAuthenticated,)
    required = ("inventory.view_asset", "warehouse.view_warehouse", "inventory.view_assetcategory",
                "inventory.view_stockbalance", "inventory.view_stockthreshold")

    def get(self, request):
        if not all(request.user.has_perm(p) for p in self.required):
            self.permission_denied(request)
        # Sum available bulk stock per product/site, not one alert per condition bucket.
        balances = StockBalance.objects.filter(
            product_model_id=OuterRef("product_model_id"), location__warehouse_id=OuterRef("warehouse_id"),
            stock_state="AVAILABLE").order_by().values("product_model_id").annotate(q=Sum("quantity")).values("q")
        low = StockThreshold.objects.annotate(
            available_quantity=Coalesce(Subquery(balances, output_field=BigIntegerField()), Value(0), output_field=BigIntegerField())
        ).filter(available_quantity__lt=F("minimum_quantity")).order_by("warehouse_id", "product_model_id")
        total_alerts = low.count()
        recent = []
        if request.user.has_perm("transactions.view_stockmovement"):
            # No reason, actor, recipient, external reference, audit or import linkage.
            recent = list(StockMovement.objects.order_by("-recorded_at", "-pk").values(
                "id", "operation_type", "quantity", "recorded_at")[:10])
        return Response({
            "total_assets": Asset.objects.count(), "total_warehouses": Warehouse.objects.count(),
            "total_categories": AssetCategory.objects.count(),
            "stock_totals": {"all": StockBalance.objects.aggregate(q=Sum("quantity"))["q"] or 0,
                             "available": StockBalance.objects.filter(stock_state="AVAILABLE").aggregate(q=Sum("quantity"))["q"] or 0},
            "low_stock_count": total_alerts,
            "low_stock": list(low.values("product_model_id", "warehouse_id", "minimum_quantity", "available_quantity")[:20]),
            "recent_activity": recent,
            "recent_activity_permitted": request.user.has_perm("transactions.view_stockmovement"),
        })
