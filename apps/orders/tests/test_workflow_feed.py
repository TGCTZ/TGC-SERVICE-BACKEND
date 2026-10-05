"""The Identification page can read both waiting and completed orders."""

from decimal import Decimal

import pytest

from apps.billing.services import generate_bill_for_order
from apps.gems.tests.factories import StoneTypeFactory
from apps.orders.services import add_stone
from apps.orders.tests.factories import OrderFactory, StoneFactory

pytestmark = pytest.mark.django_db


def test_identification_feed_only_contains_unbilled_actionable_orders(
    settings, admin_user, auth_client
):
    """Billed work leaves the page; partial and editable orders remain."""
    settings.GEPG_SIMULATE = True
    waiting = OrderFactory(stone_count=2, received_date="2026-09-01")
    completed = OrderFactory(stone_count=1, received_date="2026-10-01")
    StoneFactory(order=completed)
    billed = OrderFactory(stone_count=1)
    add_stone(billed, stone_type=StoneTypeFactory(price=Decimal("50000.00")))
    generate_bill_for_order(billed, user=admin_user)

    response = auth_client(admin_user).get("/api/v1/orders/workflow-feed/")

    assert response.status_code == 200
    assert response.data["count"] == 2
    assert response.data["results"][0]["record_id"] == waiting.pk
    assert response.data["results"][0]["waiting"] is True
    assert response.data["results"][1]["record_id"] == completed.pk
    assert response.data["results"][1]["waiting"] is False


def test_identification_count_accepts_a_stones_only_page_viewer(viewer_user, auth_client):
    """A stone viewer without order-list access still sees the badge count."""
    OrderFactory(stone_count=2)

    response = auth_client(viewer_user).get("/api/v1/orders/identification-count/")

    assert response.status_code == 200
    assert response.data == {"count": 1}
