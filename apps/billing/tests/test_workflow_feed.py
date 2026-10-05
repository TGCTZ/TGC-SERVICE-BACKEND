"""Bills feed mixes issued bills with orders that can now be billed."""

from decimal import Decimal

import pytest

from apps.billing.dev import simulate_payment
from apps.billing.services import generate_bill_for_order
from apps.gems.tests.factories import StoneTypeFactory
from apps.orders.services import add_stone
from apps.orders.tests.factories import OrderFactory

pytestmark = pytest.mark.django_db


def test_bills_feed_contains_bills_and_waiting_orders(settings, admin_user, auth_client):
    """Issued bills and billable orders appear in the same result page."""
    settings.GEPG_SIMULATE = True
    stone_type = StoneTypeFactory(price=Decimal("50000.00"))
    billed_order = OrderFactory(stone_count=1)
    add_stone(billed_order, stone_type=stone_type)
    bill = generate_bill_for_order(billed_order, user=admin_user)
    paid_order = OrderFactory(stone_count=1)
    add_stone(paid_order, stone_type=stone_type)
    paid_bill = generate_bill_for_order(paid_order, user=admin_user)
    simulate_payment(paid_bill)
    waiting_order = OrderFactory(stone_count=1)
    add_stone(waiting_order, stone_type=stone_type)

    response = auth_client(admin_user).get("/api/v1/bills/workflow-feed/")

    assert response.status_code == 200
    assert response.data["count"] == 2
    rows = {row["kind"]: row for row in response.data["results"]}
    assert rows["bill"]["record_id"] == bill.pk
    assert rows["bill"]["waiting"] is False
    assert rows["order"]["record_id"] == waiting_order.pk
    assert rows["order"]["waiting"] is True
    assert all(row["record_id"] != paid_bill.pk for row in response.data["results"])
