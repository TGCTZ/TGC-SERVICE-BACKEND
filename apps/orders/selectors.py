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


def preliminary_identification_worklist():
    """Orders with stones still to identify.

    The customer said how many stones they brought; the bench has typed fewer
    than that so far. Typing a stone is preliminary identification - it is what
    fixes the price, so nothing can be billed until this queue empties.

    The alias is ``identified`` rather than ``identified_count``: the latter is a
    property on ``Order``, and an annotation of that name would silently shadow
    it on every row this returns.
    """
    return (
        Order.objects.select_related("customer")
        .annotate(identified=Count("stones"))
        .filter(identified__lt=F("stone_count"))
    )
