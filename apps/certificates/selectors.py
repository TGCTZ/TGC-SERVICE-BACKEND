"""Reads that encode a certification workflow gate."""

from django.db.models import Max

from apps.gems.enums import BillStatus
from apps.orders.models import Stone


def certification_worklist():
    """Stones ready to be certified.

    Findings signed off, bill settled, no certificate yet - the three issuance
    guards expressed as a queue, so the screen and the service agree.
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
        # rows read the live one back through `Stone.report`.
        .prefetch_related("reports")
        .filter(
            # Live reports only. A database join sees soft-deleted rows too -
            # the model's default manager does not reach into a join - and a
            # discarded report is not findings.
            reports__is_finalized=True,
            reports__deleted_at__isnull=True,
            order__bill__status=BillStatus.PAID,
            certificate__isnull=True,
        )
        # Annotated rather than ordered on `reports__identified_at` directly:
        # ordering across a multi-valued relation adds a second join, which
        # would repeat a stone once per report it has ever had.
        .annotate(signed_off_at=Max("reports__identified_at"))
        .order_by(
            # Signed-off stones in the order they were signed off, `pk` breaking
            # the tie so a paginated page is stable.
            "signed_off_at",
            "pk",
        )
    )
