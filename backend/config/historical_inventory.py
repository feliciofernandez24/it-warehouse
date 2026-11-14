"""Test-only historical app registry; never used by production settings."""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.inventory.apps import InventoryConfig


class HistoricalInventoryConfig(InventoryConfig):
    def ready(self):
        if not getattr(settings, "ISOLATED_HISTORICAL_TESTS", False):
            raise ImproperlyConfigured("Historical registry requires isolated test settings")
        # No review tables exist in this separate database. Remove only new models
        # from this process's test app registry and expire reverse-relation caches.
        registry = self.apps.all_models[self.label]
        for name in ("importsourceprofile", "importpreparationrevision", "importrevisionparticipant",
                     "importpreviewsnapshot", "importreviewevent"):
            registry.pop(name, None)
        self.apps.clear_cache()
