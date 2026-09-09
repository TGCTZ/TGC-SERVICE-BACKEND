"""Reads that encode a billing workflow gate."""

from django.db.models import Count, F

from apps.orders.models import Order


def billing_worklist():
    """Orders ready to be billed.

    Every submitted stone is registered and typed - which is what makes a price
    available for each one - and no bill exists yet.
    """
    return (
        Order.objects.select_related("customer")
        .annotate(registered=Count("stones"))
        .filter(bill__isnull=True, stone_count__gt=0, registered=F("stone_count"))
    )
