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


def annotate_identified(queryset):
    """Annotate each order with how many of its stones have been identified.

    The alias is ``identified`` rather than ``identified_count``: the latter is
    a property on ``Order``, and an annotation of that name would silently
    shadow it on every row returned.
    """
    return queryset.annotate(identified=Count("stones"))


def identification_worklist():
    """Orders with stones still to identify.

    The customer said how many stones they brought; the bench has typed fewer
    than that so far. Typing a stone is its identification - it is what
    fixes the price, so nothing can be billed until this queue empties.

    """
    queryset = annotate_identified(Order.objects.select_related("customer"))
    return queryset.filter(identified__lt=F("stone_count"))
