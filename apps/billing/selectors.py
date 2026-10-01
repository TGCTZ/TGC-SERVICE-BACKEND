"""Reads that encode a billing workflow gate."""

from django.db.models import Count, F

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
