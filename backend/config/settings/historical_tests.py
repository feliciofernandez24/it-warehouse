"""Disposable historical registry/database only; never development settings."""
import os
from django.core.exceptions import ImproperlyConfigured
from .development import *  # noqa: F403

if (os.environ.get("ITW_ISOLATED_TESTS") != "1"
        or os.environ.get("POSTGRES_DB") != "phase3b2a_history"
        or os.environ.get("POSTGRES_HOST") != "127.0.0.1"):
    raise ImproperlyConfigured("Historical tests require the explicit isolated database")
ISOLATED_HISTORICAL_TESTS = True
INSTALLED_APPS = [
    "config.historical_inventory.HistoricalInventoryConfig"
    if entry == "apps.inventory.apps.InventoryConfig" else entry
    for entry in INSTALLED_APPS  # noqa: F405
]
MIGRATION_MODULES = {"inventory": "config.historical_inventory_migrations"}
