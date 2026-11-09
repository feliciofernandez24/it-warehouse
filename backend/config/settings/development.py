import os
from .base import *  # noqa: F403

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() in {"true", "1", "yes"}
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]
