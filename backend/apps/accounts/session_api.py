"""Session endpoints use Django views so CSRF also applies to anonymous login."""
import json
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.cache import caches
from django.http import JsonResponse
from django.middleware.csrf import get_token, rotate_token
from django.utils.crypto import salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_POST


def csrf_failure(request, reason=""):
    return JsonResponse({"detail": "CSRF verification failed. Refresh and try again."}, status=403)


def identity(user):
    # No email, contact details, password hash or evidence permissions are disclosed.
    return {"id": user.pk, "username": user.get_username(),
            "permissions": sorted(p for p in user.get_all_permissions()
                                  if p.startswith(("inventory.view_asset", "inventory.view_manufacturer",
                                                   "inventory.view_productmodel", "inventory.view_stock",
                                                   "warehouse.view_", "transactions.view_stockmovement"))
                                  and "import" not in p)}


def budget(username, address):
    """Fixed-window account and peer limits; ignore untrusted forwarding headers."""
    cache = caches["login"]
    for scope, value, limit in (("peer", address, settings.LOGIN_PEER_LIMIT),
                                ("account", username.casefold(), settings.LOGIN_ACCOUNT_LIMIT)):
        key = "login:" + salted_hmac(scope, value).hexdigest()
        if cache.add(key, 1, timeout=settings.LOGIN_WINDOW_SECONDS):
            count = 1
        else:
            count = cache.incr(key)
        if count > limit:
            return False
    return True


@never_cache
@require_GET
@ensure_csrf_cookie
def csrf(request):
    return JsonResponse({"csrfToken": get_token(request)})


@never_cache
@require_GET
def me(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)
    return JsonResponse({"user": identity(request.user)})


@never_cache
@require_POST
@csrf_protect
@sensitive_post_parameters("password")
def sign_in(request):
    if request.content_type != "application/json":
        return JsonResponse({"detail": "JSON request required."}, status=415)
    try:
        if len(request.body) > 8192:
            raise ValueError
        data = json.loads(request.body)
        username, password = data["username"], data["password"]
        if (type(username) is not str or type(password) is not str
                or not 1 <= len(username) <= 150 or not 1 <= len(password) <= 1024):
            raise ValueError
    except (ValueError, KeyError, TypeError, UnicodeError):
        return JsonResponse({"detail": "Provide a username and password."}, status=400)
    try:
        permitted = budget(username, request.META.get("REMOTE_ADDR", "unknown"))
    except Exception:
        # No authentication if throttle storage is unavailable; never log request bodies.
        return JsonResponse({"detail": "Sign-in temporarily unavailable."}, status=503)
    if not permitted:
        response = JsonResponse({"detail": "Too many attempts. Try again shortly."}, status=429)
        response["Retry-After"] = str(settings.LOGIN_WINDOW_SECONDS)
        return response
    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"detail": "Invalid username or password."}, status=401)
    login(request, user)  # Django cycles the session key and rotates the CSRF secret.
    return JsonResponse({"user": identity(user), "csrfToken": get_token(request)})


@never_cache
@require_POST
@csrf_protect
def sign_out(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)
    logout(request)
    rotate_token(request)
    return JsonResponse({"csrfToken": get_token(request)})
