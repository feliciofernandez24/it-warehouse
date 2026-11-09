"""Recipient identities; Django auth.User remains unchanged."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.common import NamedMaster, check, enum_check


class RecipientKind(models.TextChoices):
    PERSON = "PERSON", "Person"
    DEPARTMENT = "DEPARTMENT", "Department"
    TEAM = "TEAM", "Team"
    ORGANIZATION = "ORGANIZATION", "Organization"


class AssetRecipient(NamedMaster):
    kind = models.CharField(max_length=16, choices=RecipientKind.choices, default=RecipientKind.PERSON)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="asset_recipient",
    )
    external_reference = models.CharField(max_length=200, blank=True)
    contact_details = models.TextField(blank=True)

    class Meta(NamedMaster.Meta):
        constraints = NamedMaster.Meta.constraints + [
            enum_check("recipient_kind_valid", "kind", RecipientKind),
            check("recipient_user_person", Q(user__isnull=True) | Q(kind=RecipientKind.PERSON)),
        ]

    def clean(self):
        super().clean()
        if self.user_id and self.kind != RecipientKind.PERSON:
            raise ValidationError({"user": "Only a person recipient can link to a login account."})
