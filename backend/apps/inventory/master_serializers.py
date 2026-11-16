"""Strict master-data contracts; never accept ledger state or actor identity."""
from rest_framework import serializers
from apps.inventory.models import Asset, AssetCategory, Manufacturer, ProductModel
from apps.warehouse.models import Warehouse, StorageLocation


class StrictMaster(serializers.ModelSerializer):
    change_reason = serializers.CharField(write_only=True, max_length=500, trim_whitespace=True)
    expected_version = serializers.IntegerField(write_only=True, required=False, min_value=0, max_value=2**63-1)

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:
            for name, field in fields.items():
                if isinstance(field, serializers.PrimaryKeyRelatedField) and field.queryset is not None:
                    current = getattr(self.instance, name + "_id", None)
                    if current is not None:
                        field.queryset = field.queryset | field.queryset.model.objects.filter(pk=current)
        return fields

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError({"detail": "A JSON object is required."})
        allowed = {name for name, field in self.fields.items() if not field.read_only}
        unknown = set(data) - allowed
        if unknown:
            raise serializers.ValidationError({key: "This field cannot be supplied." for key in sorted(unknown)})
        data = data.copy()
        for key in ("code", "sku_code"):
            if isinstance(data.get(key), str):
                data[key] = data[key].strip().upper()
        return super().to_internal_value(data)

    def validate(self, attrs):
        if self.instance:
            if "expected_version" not in attrs:
                raise serializers.ValidationError({"expected_version": "Refresh the record and supply its version."})
            for field in ("code", "sku_code"):
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError({field: "Existing identifiers are immutable."})
        elif "expected_version" in attrs:
            raise serializers.ValidationError({"expected_version": "Only updates accept a version."})
        # PATCH still requires a meaningful reason; DRF skips required fields on partial requests.
        if not attrs.get("change_reason"):
            raise serializers.ValidationError({"change_reason": "A reason is required."})
        return attrs


class Category(StrictMaster):
    class Meta:
        model = AssetCategory
        fields = ("id", "code", "name", "description", "is_active", "version", "change_reason", "expected_version")
        read_only_fields = ("id", "version")


class ManufacturerData(Category):
    class Meta(Category.Meta):
        model = Manufacturer


class Product(StrictMaster):
    category = serializers.PrimaryKeyRelatedField(queryset=AssetCategory.objects.filter(is_active=True))
    manufacturer = serializers.PrimaryKeyRelatedField(queryset=Manufacturer.objects.filter(is_active=True), allow_null=True, required=False)
    category_name = serializers.CharField(source="category.name", read_only=True)
    manufacturer_name = serializers.CharField(source="manufacturer.name", read_only=True, default=None)

    class Meta:
        model = ProductModel
        fields = ("id", "sku_code", "name", "category", "category_name", "manufacturer", "manufacturer_name",
                  "model_number", "part_number", "tracking_mode", "description", "is_active",
                  "version", "change_reason", "expected_version")
        read_only_fields = ("id", "version")


class WarehouseData(StrictMaster):
    class Meta:
        model = Warehouse
        fields = ("id", "code", "name", "description", "address", "is_active", "version", "change_reason", "expected_version")
        read_only_fields = ("id", "version")


class Location(StrictMaster):
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.filter(is_active=True))
    parent = serializers.PrimaryKeyRelatedField(queryset=StorageLocation.objects.filter(is_active=True), allow_null=True, required=False)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)

    class Meta:
        model = StorageLocation
        fields = ("id", "code", "name", "warehouse", "warehouse_name", "parent", "parent_name", "kind",
                  "is_active", "version", "change_reason", "expected_version")
        read_only_fields = ("id", "version")


class AssetMetadata(StrictMaster):
    product_name = serializers.CharField(source="product_model.name", read_only=True)
    location_name = serializers.CharField(source="current_location.name", read_only=True, default=None)

    class Meta:
        model = Asset
        fields = ("id", "asset_tag", "product_model_id", "product_name", "current_location_id", "location_name",
                  "condition", "lifecycle_status", "serial_review_state", "device_name", "serial_raw",
                  "description", "remarks", "version", "change_reason", "expected_version")
        read_only_fields = ("id", "asset_tag", "product_model_id", "current_location_id", "condition",
                            "lifecycle_status", "serial_review_state", "version")


class AssetRegistration(StrictMaster):
    product_model = serializers.PrimaryKeyRelatedField(queryset=ProductModel.objects.filter(is_active=True, tracking_mode="SERIALIZED"))
    current_location = serializers.PrimaryKeyRelatedField(queryset=StorageLocation.objects.filter(is_active=True))

    class Meta:
        model = Asset
        fields = ("product_model", "current_location", "device_name", "serial_raw", "description", "remarks",
                  "change_reason", "expected_version")
