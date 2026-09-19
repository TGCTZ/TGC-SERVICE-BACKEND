"""Reads that encode a findings workflow gate."""

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
        Stone.objects.select_related(
            "order",
            "order__customer",
            "stone_type",
            # The row serialises the stone type, which renders its
            # category - one query per row without this join.
            "stone_type__category",
        )
        # `reports` is a reverse FK, so it is prefetched rather than joined; the
        # rows read it back through `Stone.report`.
        .prefetch_related("reports")
        .filter(order__bill__status=BillStatus.PAID)
        # A soft-deleted report does not count as findings, so the join is
        # narrowed to live rows - a database join sees every row, including the
        # ones the model's default manager hides.
        .exclude(reports__is_finalized=True, reports__deleted_at__isnull=True)
        # Grouped by the parcel they came in on, which is how they sit on the
        # bench; `pk` breaks the tie so a paginated page is stable.
        .order_by("order__received_date", "order_id", "label", "pk")
    )
