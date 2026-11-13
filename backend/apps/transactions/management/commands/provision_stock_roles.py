from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

ROLES = {
    "Administrator": {"receive_stock", "issue_stock", "transfer_stock", "return_stock", "request_adjustment", "request_disposal", "approve_adjustment", "approve_disposal", "review_audit_adjustment"},
    "Warehouse Operator": {"receive_stock", "issue_stock", "transfer_stock", "return_stock", "request_adjustment", "request_disposal"},
    "IT Engineer": {"transfer_stock", "return_stock"},
    "Auditor": {"view_stockmovement", "view_stockoperation", "view_assetassignment", "review_audit_adjustment"},
}


class Command(BaseCommand):
    help = "Provision stock capability groups; grants no user memberships and removes no existing grants"

    @transaction.atomic
    def handle(self, **options):
        for name, capabilities in ROLES.items():
            group, _ = Group.objects.get_or_create(name=name)
            permissions = Permission.objects.filter(content_type__app_label="transactions", codename__in=capabilities)
            if permissions.count() != len(capabilities):
                raise CommandError("Run migrate to create all permissions first")
            group.permissions.add(*permissions)
        self.stdout.write(self.style.SUCCESS("Stock groups provisioned; review membership and pre-existing grants separately"))
