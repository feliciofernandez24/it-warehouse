from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from apps.transactions.services.posting import _lock


class Command(BaseCommand):
    help = "Read-only reconciliation of bulk balances, serialized positions and custody"

    @transaction.atomic
    def handle(self, **options):
        _lock()
        with connection.cursor() as cursor:
            cursor.execute("""SELECT b.id FROM inventory_stockbalance b WHERE b.quantity<>(
                SELECT coalesce(sum(CASE WHEN m.destination_balance_id=b.id THEN m.quantity ELSE 0 END
                - CASE WHEN m.source_balance_id=b.id THEN m.quantity ELSE 0 END),0)
                FROM transactions_stockmovement m WHERE m.source_balance_id=b.id OR m.destination_balance_id=b.id)""")
            buckets = [row[0] for row in cursor.fetchall()]
            cursor.execute("""SELECT a.id FROM inventory_asset a LEFT JOIN LATERAL (
                SELECT * FROM transactions_stockmovement WHERE asset_id=a.id ORDER BY id DESC LIMIT 1
                ) m ON true WHERE m.id IS NULL OR (a.current_location_id,a.condition,a.lifecycle_status)
                IS DISTINCT FROM (m.destination_location_id,m.condition_after,m.lifecycle_after)
                OR (a.lifecycle_status='ASSIGNED') IS DISTINCT FROM EXISTS(
                SELECT 1 FROM transactions_assetassignment x WHERE x.asset_id=a.id AND x.returned_at IS NULL)""")
            assets = [row[0] for row in cursor.fetchall()]
        if buckets or assets:
            raise CommandError(f"Reconciliation failed: buckets={buckets}; assets={assets}")
        self.stdout.write(self.style.SUCCESS("Ledger, balances, asset positions and custody reconcile"))
