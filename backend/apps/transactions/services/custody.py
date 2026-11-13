from apps.transactions.models import AssetAssignment


def current_custody(asset_id):
    return AssetAssignment.objects.select_related("recipient", "issue_movement").filter(
        asset_id=asset_id, returned_at__isnull=True,
    ).first()
