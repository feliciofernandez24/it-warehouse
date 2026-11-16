"""Strict manual commands; no arbitrary stock or review writes."""
from rest_framework import serializers
from apps.inventory.choices import Condition, StockState

class Command(serializers.Serializer):
    operation_key = serializers.UUIDField()
    reason = serializers.CharField(max_length=500)
    external_reference = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data)-set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["Unknown or read-only fields."]})
        return super().to_internal_value(data)

class Receipt(Command):
    product_model_id = serializers.IntegerField(min_value=1)
    destination_location_id = serializers.IntegerField(min_value=1)
    condition = serializers.ChoiceField(choices=Condition.choices)
    state = serializers.ChoiceField(choices=StockState.choices)

class Registration(Receipt):
    device_name = serializers.CharField(max_length=200)
    serial_raw = serializers.CharField(max_length=200, allow_blank=True, trim_whitespace=False)
    description = serializers.CharField(max_length=4000, allow_blank=True, required=False, default="")

class BulkReceipt(Receipt):
    quantity = serializers.IntegerField(min_value=1, max_value=2**63-1)

class Movement(Command):
    asset_id = serializers.IntegerField(min_value=1, required=False)
    product_model_id = serializers.IntegerField(min_value=1, required=False)
    quantity = serializers.IntegerField(min_value=1, max_value=2**63-1)
    source_location_id = serializers.IntegerField(min_value=1)
    source_condition = serializers.ChoiceField(choices=Condition.choices)
    source_state = serializers.ChoiceField(choices=StockState.choices)
    def validate(self, data):
        if bool(data.get("asset_id")) == bool(data.get("product_model_id")):
            raise serializers.ValidationError("Choose one asset or bulk product.")
        if data.get("asset_id") and data["quantity"] != 1:
            raise serializers.ValidationError("Serialized quantity must be one.")
        return data

class Transfer(Movement):
    destination_location_id = serializers.IntegerField(min_value=1)
    condition = serializers.ChoiceField(choices=Condition.choices)
    state = serializers.ChoiceField(choices=StockState.choices)

class Issue(Movement):
    recipient_id = serializers.IntegerField(min_value=1)
    destination_reference = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    purpose = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    def validate(self, data):
        data = super().validate(data)
        if not data.get("asset_id"):
            raise serializers.ValidationError("This endpoint supports serialized custody only.")
        return data

class Return(Command):
    asset_id = serializers.IntegerField(min_value=1)
    assignment_id = serializers.IntegerField(min_value=1)
    destination_location_id = serializers.IntegerField(min_value=1)
    condition = serializers.ChoiceField(choices=Condition.choices)
    state = serializers.ChoiceField(choices=StockState.choices)
