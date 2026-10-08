"""Automatic preliminary identification-to-billing handoff."""

from decimal import Decimal

import pytest

from apps.billing.models import Bill
from apps.gems.enums import OrderStage, StoneStatus
from apps.gems.tests.factories import StoneTypeFactory
from apps.orders.selectors import order_stage, orders_at_stage
from apps.orders.tests.factories import OrderFactory

pytestmark = pytest.mark.django_db


def test_last_identification_generates_bill_and_control_number(
    settings, admin_user, auth_client
):
    """The final type pick replaces the edit and Generate bill handoffs."""
    settings.AUTO_BILL_AFTER_IDENTIFICATION = True
    settings.GEPG_SIMULATE = True
    order = OrderFactory(stone_count=2)
    stone_type = StoneTypeFactory(price=Decimal("1000.00"))
    client = auth_client(admin_user)

    first = client.post(
        f"/api/v1/orders/{order.pk}/stones/", {"stone_type": stone_type.pk}
    )
    assert first.status_code == 201
    assert first.data["bill_number"] is None
    assert not Bill.objects.filter(order=order).exists()

    last = client.post(
        f"/api/v1/orders/{order.pk}/stones/", {"stone_type": stone_type.pk}
    )
    assert last.status_code == 201, last.data
    bill = Bill.objects.get(order=order)
    assert last.data["bill_number"] == bill.bill_number
    assert last.data["control_number"] == bill.control_number
    assert bill.control_number
    assert set(order.stones.values_list("status", flat=True)) == {StoneStatus.BILLED}
    order.refresh_from_db()
    assert order_stage(order) == OrderStage.AWAITING_PAYMENT
    assert client.get("/api/v1/bills/worklist/").status_code == 404
    assert client.post("/api/v1/bills/generate/", {"order": order.pk}).status_code == 404


def test_missing_price_keeps_identification_for_retry(settings, admin_user, auth_client):
    """A pricing error leaves a visible exception without a duplicate stone."""
    settings.AUTO_BILL_AFTER_IDENTIFICATION = True
    settings.GEPG_SIMULATE = True
    order = OrderFactory(stone_count=1)
    stone_type = StoneTypeFactory(price=None)
    client = auth_client(admin_user)

    response = client.post(
        f"/api/v1/orders/{order.pk}/stones/", {"stone_type": stone_type.pk}
    )
    assert response.status_code == 201
    assert "No price set" in response.data["billing_attention"]
    assert order.stones.count() == 1
    assert not Bill.objects.filter(order=order).exists()
    assert order_stage(order) == OrderStage.BILLING_ATTENTION
    assert list(orders_at_stage(type(order).objects.all(), "billing_attention")) == [
        order
    ]
    attention = client.get("/api/v1/bills/attention/")
    assert [row["id"] for row in attention.data["results"]] == [order.pk]

    category = stone_type.category
    category.price = Decimal("1000.00")
    category.save(update_fields=["price"])
    retried = client.post("/api/v1/bills/retry/", {"order": order.pk})
    assert retried.status_code == 200, retried.data
    assert Bill.objects.filter(order=order).count() == 1
    assert retried.data["control_number"]
    assert client.get("/api/v1/bills/attention/").data["count"] == 0


def test_gateway_failure_retries_the_same_bill(
    settings, admin_user, auth_client, monkeypatch
):
    """A failed submission cannot lead to a second bill or second price snapshot."""
    settings.AUTO_BILL_AFTER_IDENTIFICATION = True
    order = OrderFactory(stone_count=1)
    stone_type = StoneTypeFactory(price=Decimal("1000.00"))
    outcomes = iter(
        [
            {
                "success": False,
                "control_number": None,
                "status_code": "CONNECTION_ERROR",
                "status_desc": "Gateway unavailable",
            },
            {
                "success": True,
                "control_number": "991234567890",
                "status_code": "7101",
                "status_desc": "Accepted",
            },
        ]
    )
    monkeypatch.setattr(
        "apps.billing.services.bill.submit_bill", lambda *args: next(outcomes)
    )
    client = auth_client(admin_user)

    identified = client.post(
        f"/api/v1/orders/{order.pk}/stones/", {"stone_type": stone_type.pk}
    )
    assert identified.status_code == 201
    assert identified.data["billing_attention"] == "Gateway unavailable"
    bill = Bill.objects.get(order=order)
    assert order_stage(order) == OrderStage.BILLING_ATTENTION

    retried = client.post("/api/v1/bills/retry/", {"order": order.pk})
    assert retried.status_code == 200
    assert retried.data["bill_number"] == bill.bill_number
    assert retried.data["control_number"] == "991234567890"
    assert Bill.objects.filter(order=order).count() == 1
    order.refresh_from_db()
    assert order_stage(order) == OrderStage.AWAITING_PAYMENT


def test_accepted_async_submission_waits_for_callback(
    settings, admin_user, auth_client, monkeypatch
):
    """No immediate control number is normal for an accepted async response."""
    settings.AUTO_BILL_AFTER_IDENTIFICATION = True
    order = OrderFactory(stone_count=1)
    stone_type = StoneTypeFactory(price=Decimal("1000.00"))
    monkeypatch.setattr(
        "apps.billing.services.bill.submit_bill",
        lambda *args: {
            "success": True,
            "control_number": "PENDING",
            "status_code": "7101",
            "status_desc": "Awaiting control number",
        },
    )
    client = auth_client(admin_user)
    response = client.post(
        f"/api/v1/orders/{order.pk}/stones/", {"stone_type": stone_type.pk}
    )
    assert response.status_code == 201
    assert response.data["billing_attention"] is None
    assert response.data["control_number"] is None
    assert client.get("/api/v1/bills/attention/").data["count"] == 0
    order.refresh_from_db()
    assert order_stage(order) == OrderStage.AWAITING_PAYMENT


def test_auto_mode_blocks_retyping_a_saved_identification(
    settings, admin_user, auth_client
):
    """UI hiding is backed by the stone update endpoint."""
    settings.AUTO_BILL_AFTER_IDENTIFICATION = True
    order = OrderFactory(stone_count=2)
    first_type = StoneTypeFactory(price=Decimal("1000.00"))
    other_type = StoneTypeFactory(price=Decimal("1000.00"))
    client = auth_client(admin_user)
    response = client.post(
        f"/api/v1/orders/{order.pk}/stones/", {"stone_type": first_type.pk}
    )
    stone_id = response.data["id"]

    changed = client.patch(f"/api/v1/stones/{stone_id}/", {"stone_type": other_type.pk})
    deleted = client.delete(f"/api/v1/stones/{stone_id}/")
    assert changed.status_code == 400
    assert deleted.status_code == 403
