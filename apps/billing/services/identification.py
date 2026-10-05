"""Complete preliminary identification and hand off to automatic billing."""

from django.conf import settings

from apps.core.exceptions import ServiceError
from apps.orders.services import add_stone

from .bill import bill_needs_attention, generate_bill_for_order


def identify_stone(order, *, stone_type, user=None):
    """Save the stone, then bill the completed order when automation is enabled.

    The stone commits before the bill is issued. If pricing fails, the order
    remains identified and appears in Billing needs attention for a safe retry.
    """
    stone = add_stone(order, stone_type=stone_type, user=user)
    if not settings.AUTO_BILL_AFTER_IDENTIFICATION:
        return stone, None, None
    if order.stones.count() != order.stone_count:
        return stone, None, None
    if order.is_held:
        return stone, None, "Release the order before billing."

    try:
        bill = generate_bill_for_order(order, user=user)
    except ServiceError as exc:
        return stone, None, str(exc)

    if bill_needs_attention(bill):
        return stone, bill, bill.status_desc or "GePG did not accept the bill."
    return stone, bill, None
