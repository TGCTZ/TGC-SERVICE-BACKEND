"""Reads that encode a workflow gate.

These are the queues the lab actually works from, and each one is a predicate
the whitelist filter backend cannot express - an aggregate, or a comparison
against another column. Keeping them here rather than in a view means the gate
is testable on its own and cannot drift between the screen that lists it and the
service that acts on it.

``billing_worklist`` joins to the bill and therefore lands with ``apps.billing``.
"""

from django.db.models import Count, F

from apps.gems.enums import BillStatus, OrderHold, OrderStage, StoneStatus

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
    queryset = annotate_identified(Order.objects.select_related("customer", "bill"))
    return queryset.filter(identified__lt=F("stone_count"))


def order_stage(order) -> str:
    """Where an order has got to, as an :class:`OrderStage` value.

    Derived, never stored. The rule is deliberately pessimistic: an order is
    only as far along as its **least advanced** stone, because a customer
    collecting their stones cares about the last one, not the first. The same
    reasoning makes a single held or cancelled stone dominate the whole order -
    that is the exception worth surfacing in a list.

    Ordering matters. Identification and billing are checked before stone
    statuses, because both are properties of the order as a whole: a partly
    identified order has no stone to be behind, and an unpaid bill outranks
    every stone sitting at ``billed``.

    An order-level hold or cancellation wins over everything else, since it is a
    decision somebody made about the visit rather than a consequence of work.

    Reads ``order.bill`` through the reverse relation rather than importing
    ``apps.billing``, which sits above this module. Callers should
    ``select_related("bill")`` and prefetch stones, or this is a query per row.

    Args:
        order: The order to place.

    Returns:
        One of :class:`~apps.gems.enums.OrderStage`.
    """
    # A decision about the whole visit outranks everything its stones are doing.
    # This is the one part of the stage that is stored rather than derived - see
    # `Order.hold_status`.
    if order.hold_status == OrderHold.CANCELLED:
        return OrderStage.CANCELLED
    if order.hold_status == OrderHold.ON_HOLD:
        return OrderStage.ON_HOLD

    stones = list(order.stones.all())
    if not stones:
        return OrderStage.EMPTY

    statuses = {stone.status for stone in stones}

    # An exception on any *stone* outranks ordinary progress too: these are the
    # rows a supervisor needs to find, and averaging them away would bury them.
    if StoneStatus.CANCELLED in statuses:
        return OrderStage.CANCELLED
    if StoneStatus.ON_HOLD in statuses:
        return OrderStage.ON_HOLD

    if len(stones) < order.stone_count:
        return OrderStage.IDENTIFYING

    bill = getattr(order, "bill", None)
    if bill is None:
        return OrderStage.READY_TO_BILL
    if bill.status == BillStatus.PARTIALLY_PAID:
        return OrderStage.PART_PAID
    if bill.status != BillStatus.PAID:
        return OrderStage.AWAITING_PAYMENT

    # Paid, so the bench has the stones. Report the furthest-behind one.
    rank = {
        StoneStatus.COLLECTED: OrderStage.COLLECTED,
        StoneStatus.READY_FOR_COLLECTION: OrderStage.READY_FOR_COLLECTION,
        StoneStatus.CERTIFIED: OrderStage.CERTIFIED,
    }
    order_of_progress = [
        StoneStatus.COLLECTED,
        StoneStatus.READY_FOR_COLLECTION,
        StoneStatus.CERTIFIED,
    ]
    for status in order_of_progress:
        # Every stone at this stage or beyond it.
        if statuses <= {status, *order_of_progress[: order_of_progress.index(status)]}:
            return rank[status]

    return OrderStage.IN_FINDINGS
