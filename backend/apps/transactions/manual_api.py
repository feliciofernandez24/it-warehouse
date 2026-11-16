"""Authenticated session/CSRF API over the existing guarded stock service."""
from django.core.exceptions import ObjectDoesNotExist, ValidationError as ModelError
from django.db import DatabaseError
from django.conf import settings
from rest_framework.exceptions import APIException
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.inventory.read_api import PrivateResponses, SessionAuth, ReadOnly
from apps.accounts.models import AssetRecipient
from apps.inventory.models import StockBalance
from .models import StockMovement, AssetAssignment
from . import manual_serializers as commands
from .manual_service import execute
from .services.exceptions import AuthorizationError, IdempotencyConflict, StockError

class Disabled(APIException):
    status_code=503
    default_detail="Manual inventory posting is not enabled in this deployment."

class Enabled:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not settings.MANUAL_INVENTORY_ENABLED: raise Disabled()

class Command(Enabled,PrivateResponses,APIView):
    authentication_classes=(SessionAuth,)
    permission_classes=(IsAuthenticated,)
    def post(self,request,action):
        types={"register":commands.Registration,"receive":commands.BulkReceipt,"transfer":commands.Transfer,"issue":commands.Issue,"return":commands.Return}
        if action not in types:return Response({"detail":"Unknown operation."},status=404)
        serializer=types[action](data=request.data);serializer.is_valid(raise_exception=True)
        try:
            result=execute(actor=request.user,action=action,data=serializer.validated_data)
            return Response(result,status=200 if result["replayed"] else 201)
        except AuthorizationError:raise PermissionDenied()
        except IdempotencyConflict:return Response({"detail":"Operation key conflicts. Do not reuse it for changed requests."},status=409)
        except (StockError,ObjectDoesNotExist,ModelError):return Response({"detail":"Operation rejected. Refresh inventory and check the selected values."},status=409)
        except DatabaseError:return Response({"detail":"Operation unavailable; no changes committed. Retry the identical request with the same key."},status=503)

class MovementData(serializers.ModelSerializer):
    operator=serializers.CharField(source="actor.username",read_only=True)
    class Meta:
        model=StockMovement
        fields=("id","operation_key","operation_type","asset_id","product_model_id","quantity","source_location_id","destination_location_id","operator","occurred_at","recorded_at","external_reference")
class Movements(Enabled,ReadOnly):
    queryset=StockMovement.objects.select_related("actor")
    serializer_class=MovementData
    ordering=("-recorded_at","-id")
    ordering_fields=("id","recorded_at")
    exact_filters={"asset":("asset_id","id"),"product_model":("product_model_id","id")}
class RecipientData(serializers.ModelSerializer):
    class Meta:
        model=AssetRecipient
        fields=("id","code","name","kind","is_active")
class Recipients(Enabled,ReadOnly):
    queryset=AssetRecipient.objects.filter(is_active=True)
    serializer_class=RecipientData
    search_fields=("name","code")
class AssignmentData(serializers.ModelSerializer):
    class Meta:
        model=AssetAssignment
        fields=("id","asset_id","recipient_id","assigned_at","issue_movement_id")
class Assignments(Enabled,ReadOnly):
    queryset=AssetAssignment.objects.filter(returned_at__isnull=True)
    serializer_class=AssignmentData
    ordering_fields=("id","assigned_at")
    exact_filters={"asset":("asset_id","id")}
class BalanceData(serializers.ModelSerializer):
    class Meta:
        model=StockBalance
        fields=("id","product_model_id","location_id","condition","stock_state","quantity")
class Balances(Enabled,ReadOnly):
    queryset=StockBalance.objects.all()
    serializer_class=BalanceData
    ordering_fields=("id",)
    exact_filters={"product_model":("product_model_id","id"),"location":("location_id","id")}
