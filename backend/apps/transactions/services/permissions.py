from django.contrib.auth.models import Permission
from django.db.models import Q
from .exceptions import AuthorizationError

CAPABILITIES = {
    "STOCK_IN": "receive_stock", "STOCK_OUT": "issue_stock",
    "TRANSFER": "transfer_stock", "RETURN": "return_stock",
    "ADJUSTMENT_IN": "request_adjustment", "ADJUSTMENT_OUT": "request_adjustment",
    "DISPOSAL": "request_disposal",
}


def require(actor, capability):
    # Query explicit grants, never User.has_perm's implicit superuser bypass/cache.
    if not actor.pk or not actor.is_active or not Permission.objects.filter(
        Q(user=actor) | Q(group__user=actor), content_type__app_label="transactions",
        codename=capability,
    ).exists():
        raise AuthorizationError(f"Explicit transactions.{capability} permission required")
