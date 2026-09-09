"""Reads that encode a workflow gate.

These are the queues the lab actually works from, and each one is a predicate
the whitelist filter backend cannot express - an aggregate, or a comparison
against another column. Keeping them here rather than in a view means the gate
is testable on its own and cannot drift between the screen that lists it and the
service that acts on it.

``billing_worklist`` joins to the bill and therefore lands with ``apps.billing``.
"""

from django.db.models import Count, F

from .models import Order


def registration_worklist():
    """Orders with stones still to register.

    The customer said how many stones they brought; reception has typed fewer
    than that so far.
    """
    return (
        Order.objects.select_related("customer")
        .annotate(registered=Count("stones"))
        .filter(registered__lt=F("stone_count"))
    )
