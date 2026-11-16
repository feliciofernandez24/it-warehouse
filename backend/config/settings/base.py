import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = [host.strip() for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.accounts.apps.AccountsConfig",
    "apps.inventory.apps.InventoryConfig",
    "apps.warehouse.apps.WarehouseConfig",
    "apps.transactions.apps.TransactionsConfig",
    "apps.audits.apps.AuditsConfig",
    "apps.reports.apps.ReportsConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("POSTGRES_DB", "it_warehouse"),
    "USER": os.environ.get("POSTGRES_USER", "it_warehouse"),
    "PASSWORD": os.environ["POSTGRES_PASSWORD"],
    "HOST": os.environ.get("POSTGRES_HOST", "db"),
    "PORT": os.environ.get("POSTGRES_PORT", "5432"),
}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Tokyo"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Phase 4A: same-origin sessions and bounded API reads.
# Cookies default to Secure outside explicitly enabled DEBUG development.
_COOKIE_SECURE_DEFAULT = "false" if os.environ.get("DJANGO_DEBUG", "false").lower() in {"true", "1", "yes"} else "true"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = os.environ.get("DJANGO_SESSION_COOKIE_SECURE", _COOKIE_SECURE_DEFAULT).lower() == "true"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = os.environ.get("DJANGO_CSRF_COOKIE_SECURE", _COOKIE_SECURE_DEFAULT).lower() == "true"
SESSION_COOKIE_AGE = 8 * 60 * 60
CSRF_FAILURE_VIEW = "apps.accounts.session_api.csrf_failure"
API_PAGE_SIZE = min(100, max(1, int(os.environ.get("API_PAGE_SIZE", "25"))))
LOGIN_WINDOW_SECONDS = 60
LOGIN_ACCOUNT_LIMIT = 5
LOGIN_PEER_LIMIT = 30
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "itw-default"},
    "login": {
        "BACKEND": os.environ.get("LOGIN_CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"),
        "LOCATION": os.environ.get("LOGIN_CACHE_LOCATION", "itw-login"),
    },
}

# Manual posting requires an explicit reviewed deployment opt-in.
MANUAL_INVENTORY_ENABLED = os.environ.get("ITW_MANUAL_INVENTORY_ENABLED", "0") == "1"
