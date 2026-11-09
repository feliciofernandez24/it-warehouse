"""Warehouse storage hierarchy; racks are storage locations, not rack units."""
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.common import NamedMaster, TimestampedModel, check, enum_check, related_or_error


class LocationKind(models.TextChoices):
    AREA = "AREA", "Area"
    RACK = "RACK", "Rack"
    SHELF = "SHELF", "Shelf"
    BIN = "BIN", "Bin"


class Warehouse(NamedMaster):
    address = models.TextField(blank=True)


class StorageLocation(TimestampedModel):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="locations")
    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="children")
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, choices=LocationKind.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["warehouse", "code"], name="location_warehouse_code_unique"),
            check("location_code_text", Q(code__regex=r"^[A-Z0-9][A-Z0-9_.-]*$")),
            check("location_name_text", Q(name__regex=r"\S")),
            enum_check("location_kind_valid", "kind", LocationKind),
            check("location_not_self_parent", ~Q(parent=F("pk"))),
            check("location_root_kind", Q(parent__isnull=False) | Q(kind__in=[LocationKind.AREA, LocationKind.RACK])),
        ]
        indexes = [models.Index(fields=["warehouse", "parent"], name="location_warehouse_parent")]

    def clean(self):
        super().clean()
        if self.code != self.code.strip().upper():
            raise ValidationError({"code": "Use a trimmed uppercase code."})
        if not self.parent_id:
            return
        allowed = {
            LocationKind.AREA: set(LocationKind.values),
            LocationKind.RACK: {LocationKind.SHELF, LocationKind.BIN},
            LocationKind.SHELF: {LocationKind.BIN},
            LocationKind.BIN: set(),
        }
        parent = related_or_error(self, "parent")
        if parent.warehouse_id != self.warehouse_id:
            raise ValidationError({"parent": "Parent must be in the same warehouse."})
        if self.kind not in allowed.get(parent.kind, set()):
            raise ValidationError({"parent": "This parent kind cannot contain the selected location kind."})
        visited = {self.pk} if self.pk else set()
        current = parent
        while current is not None:
            if current.pk in visited:
                raise ValidationError({"parent": "Location hierarchy cannot contain a cycle."})
            visited.add(current.pk)
            current = current.parent

    def __str__(self):
        return f"{self.warehouse_id}/{self.code}"
