"""Reads that encode a certification workflow gate."""

from django.db.models import Max

from apps.gems.enums import BillStatus
from apps.gems.models import Instrument
from apps.orders.models import Stone

from .models import Certificate


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


def instrument_checklist(certificate: Certificate) -> list[dict]:
    """Every active instrument, ticked where the certificate recorded its use.

    Built at render time rather than read straight from the snapshot, so every
    certificate prints the lab's full instrument list - including those issued
    before the checklist, whose snapshot held only the instruments used (rows
    with no ``used`` key, each of them ticked). What was *used* still comes
    from the snapshot; only the list of names around it is live. An instrument
    in the snapshot that has since been retired or renamed stays on, under its
    name as issued.
    """
    used = {
        row["name"]
        for row in certificate.instruments_snapshot or []
        if row.get("used", True)
    }
    names = set(Instrument.objects.filter(is_active=True).values_list("name", flat=True))
    names |= {row["name"] for row in certificate.instruments_snapshot or []}
    return [{"name": name, "used": name in used} for name in sorted(names)]
