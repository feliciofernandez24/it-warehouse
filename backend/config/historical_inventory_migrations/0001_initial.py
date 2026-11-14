"""Alias, not a rewrite, of the original inventory migration."""
from importlib import import_module

Migration = import_module("apps.inventory.migrations.0001_initial").Migration
