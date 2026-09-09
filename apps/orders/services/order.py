"""Order intake."""

from django.utils import timezone

from apps.core.services import generate_reference_number

from ..models import Order


def create_order(*, customer, stone_count: int, received_date=None, user=None) -> Order:
    """Register an order and how many stones the customer submitted.

    Reception records only the count. The individual stones, with the type that
    prices them, are registered afterwards via ``add_stone`` - which is what
    stops an order from quietly holding more stones than were handed over.

    Args:
        customer: The submitting customer.
        stone_count: How many stones were handed over.
        received_date: Defaults to today.
        user: The acting user.
    """
    order = Order(
        reference_number=generate_reference_number(Order, "reference_number", "ORD"),
        customer=customer,
        received_date=received_date or timezone.now().date(),
        stone_count=stone_count,
    )
    if user is not None:
        order.created_by = user
    order.save()
    return order
