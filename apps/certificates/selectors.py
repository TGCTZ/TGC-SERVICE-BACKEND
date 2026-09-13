"""Reads that encode a certification workflow gate."""

from apps.gems.enums import BillStatus
from apps.orders.models import Stone


def certification_worklist():
    """Stones ready to be certified.

    Findings signed off, bill settled, no certificate yet - the three issuance
    guards expressed as a queue, so the screen and the service agree.
    """
    return Stone.objects.select_related(
        "order", "order__customer", "stone_type", "report"
    ).filter(
        report__is_finalized=True,
        order__bill__status=BillStatus.PAID,
        certificate__isnull=True,
    )
