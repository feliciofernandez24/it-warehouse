"""Shared abstract models and constraint builders; not a Django application."""
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.db.models import Q


def check(name, condition):
    return models.CheckConstraint(name=name, condition=condition)


def enum_check(name, field, choices, nullable=False):
    condition = Q(**{f"{field}__in": choices.values})
    if nullable:
        condition |= Q(**{f"{field}__isnull": True})
    return check(name, condition)


def xor_fields(left, right):
    return Q(**{f"{left}__isnull": False, f"{right}__isnull": True}) | Q(
        **{f"{left}__isnull": True, f"{right}__isnull": False}
    )


def require_tracking(product, expected):
    if product.tracking_mode != expected:
        raise ValidationError({"product_model": f"Requires a {expected} product."})


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveBigIntegerField(default=0)

    class Meta:
        abstract = True


class NamedMaster(TimestampedModel):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        constraints = [
            check("%(app_label)s_%(class)s_code_text", ~Q(code="") & Q(code__regex=r"^[A-Z0-9][A-Z0-9_.-]*$")),
            check("%(app_label)s_%(class)s_name_text", Q(name__regex=r"\S")),
        ]

    def clean(self):
        super().clean()
        if self.code != self.code.strip().upper():
            raise ValidationError({"code": "Use a trimmed uppercase code."})

    def __str__(self):
        return f"{self.code}: {self.name}"


def related_or_error(instance, field):
    """Keep clean() helpful when a required/invalid FK cannot be resolved."""
    try:
        return getattr(instance, field)
    except ObjectDoesNotExist as exc:
        raise ValidationError({field: "Select an existing related record."}) from exc
