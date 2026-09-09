"""Reads that encode an identification workflow gate."""

from apps.gems.enums import BillStatus
from apps.orders.models import Stone


def findings_worklist():
    """Stones waiting for findings.

    The bill must be settled before a gemmologist starts work, and a stone
    leaves the queue once its report is finalized. Reached through the bill on
    the stone's order, which is why the enum lives in ``apps.gems`` rather than
    in ``apps.billing`` - the join itself needs no import.
    """
    return (
        Stone.objects.select_related("order", "order__customer", "stone_type", "report")
        .filter(order__bill__status=BillStatus.PAID)
        .exclude(report__is_finalized=True)
    )
