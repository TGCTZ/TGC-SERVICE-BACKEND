"""Order intake."""

from django.db import transaction
from django.utils import timezone

from apps.core.services import generate_reference_number

from ..models import Customer, Order


@transaction.atomic
def create_order(
    *,
    customer=None,
    customer_data: dict | None = None,
    stone_count: int,
    received_date=None,
    user=None,
) -> Order:
    """Register an order and how many stones the customer submitted.

    Reception records only the count. The individual stones, with the type that
    prices them, are identified afterwards via ``add_stone`` - which is what
    stops an order from quietly holding more stones than were handed over.

    A customer arrives one of two ways: ``customer`` for somebody already on
    file, or ``customer_data`` to register them now. Reception meets most
    customers for the first time *because* an order is being received, so
    demanding they exist beforehand would be a step that serves nobody. Creating
    them inside this transaction is what keeps a failed order from leaving an
    orphan customer behind.

    Args:
        customer: The submitting customer, if already on file.
        customer_data: Validated fields for a customer to register now.
        stone_count: How many stones were handed over.
        received_date: Defaults to today.
        user: The acting user.

    Raises:
        ValueError: If neither a customer nor customer_data was given.
    """
    if customer is None:
        if not customer_data:
            raise ValueError("create_order needs a customer or customer_data.")
        customer = Customer(**customer_data)
        if user is not None:
            customer.created_by = user
        customer.save()

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
