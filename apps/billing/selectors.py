"""Reads that encode a billing workflow gate."""

from django.conf import settings
from django.db.models import Count, F, Q

from apps.gems.enums import BillStatus, OrderHold
from apps.orders.models import Order


def billing_worklist():
    """Orders ready to be billed.

    Every submitted stone has been identified and typed - which is what makes a
    price available for each one - and no bill exists yet.
    """
    return (
        Order.objects.select_related("customer", "bill")
        .annotate(identified=Count("stones"))
        .filter(bill__isnull=True, stone_count__gt=0, identified=F("stone_count"))
        # Oldest first - a queue is worked in the order it arrived - with `pk` as
        # the tiebreaker, since several orders share a received date and an
        # ambiguous sort makes a paginated page unstable.
        .order_by("received_date", "pk")
    )


def billing_attention_worklist():
    """Completed orders whose automatic bill failed pricing or submission."""
    return (
        Order.objects.select_related("customer", "bill")
        .annotate(identified=Count("stones"))
        .filter(
            hold_status=OrderHold.ACTIVE,
            stone_count__gt=0,
            identified=F("stone_count"),
        )
        .filter(
            Q(bill__isnull=True)
            | (
                Q(bill__control_number="")
                & Q(bill__status=BillStatus.PENDING)
                & ~Q(bill__status_code__in=settings.GEPG_ACK_SUCCESS_CODES)
            )
        )
        .order_by("received_date", "pk")
    )
