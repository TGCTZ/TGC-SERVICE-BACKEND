"""Bill generation, GePG payment notifications and settlement."""

from decimal import Decimal

import pytest

from apps.billing.dev import simulate_payment
from apps.billing.models import BillItem, Payment
from apps.billing.selectors import billing_worklist
from apps.billing.services import generate_bill_for_order
from apps.core.exceptions import ServiceError
from apps.gems.enums import BillStatus, StoneStatus
from apps.gems.tests.factories import StoneTypeFactory
from apps.orders.models import StatusHistory
from apps.orders.services import add_stone
from apps.orders.tests.factories import OrderFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def billable_order(settings):
    """An order whose three stones are all registered and priced."""
    settings.GEPG_SIMULATE = True
    order = OrderFactory(stone_count=3)
    stone_type = StoneTypeFactory(price=Decimal("50000.00"))
    for _ in range(3):
        add_stone(order, stone_type=stone_type)
    return order


def test_generating_a_bill_prices_every_stone(billable_order):
    """The total is the sum of each stone type's flat fee."""
    bill = generate_bill_for_order(billable_order)

    assert bill.bill_number.startswith("BILL-")
    assert bill.total_amount == Decimal("150000.00")
    assert bill.items.count() == 3
    assert bill.status == BillStatus.PENDING


def test_generating_a_bill_transitions_every_stone(billable_order):
    """Billing moves the whole order's stones together."""
    generate_bill_for_order(billable_order)

    statuses = set(billable_order.stones.values_list("status", flat=True))
    assert statuses == {StoneStatus.BILLED}


def test_bill_items_snapshot_the_price(billable_order):
    """Repricing a stone type later must not rewrite an issued bill."""
    bill = generate_bill_for_order(billable_order)
    stone_type = billable_order.stones.first().stone_type

    stone_type.price = Decimal("999999.00")
    stone_type.save(update_fields=["price"])

    bill.refresh_from_db()
    assert bill.total_amount == Decimal("150000.00")
    assert BillItem.objects.filter(bill=bill, amount=Decimal("50000.00")).count() == 3


def test_an_order_cannot_be_billed_twice(billable_order):
    """One bill per order; the second attempt is refused."""
    generate_bill_for_order(billable_order)

    with pytest.raises(ServiceError, match="already has a bill"):
        generate_bill_for_order(billable_order)


def test_an_unpriced_stone_type_refuses_to_bill(settings):
    """An unpriced type is a configuration gap, not a free identification."""
    settings.GEPG_SIMULATE = True
    order = OrderFactory(stone_count=1)
    add_stone(order, stone_type=StoneTypeFactory(price=None))

    with pytest.raises(ServiceError, match="No price set"):
        generate_bill_for_order(order)


def test_an_order_with_no_stones_refuses_to_bill(settings):
    """There is nothing to charge for."""
    settings.GEPG_SIMULATE = True
    order = OrderFactory(stone_count=2)

    with pytest.raises(ServiceError, match="no stones"):
        generate_bill_for_order(order)


def test_payment_settles_the_bill_and_pays_the_stones(billable_order):
    """A full payment moves the bill and every stone to paid."""
    bill = generate_bill_for_order(billable_order)
    simulate_payment(bill)

    bill.refresh_from_db()
    assert bill.status == BillStatus.PAID
    assert set(billable_order.stones.values_list("status", flat=True)) == {
        StoneStatus.PAID
    }


def test_payment_is_attributed_to_the_system(billable_order):
    """The gateway has no user, so the history entry names no actor."""
    bill = generate_bill_for_order(billable_order)
    simulate_payment(bill)

    stone = billable_order.stones.first()
    entry = StatusHistory.objects.filter(stone=stone, to_status=StoneStatus.PAID).latest(
        "changed_at"
    )
    assert entry.changed_by is None
    assert entry.note == "Bill settled via GePG"


def test_a_redelivered_notification_is_idempotent(billable_order):
    """GePG redelivers until acknowledged; a repeat must not double-count.

    Without the ``trx_id`` guard the second delivery would record a second
    payment, re-transition every stone and write another history row each time.
    """
    from apps.billing.dev import _payment_xml
    from apps.billing.services import process_payment_notification

    bill = generate_bill_for_order(billable_order)
    bill.control_number = "991234567890"
    bill.save(update_fields=["control_number"])

    xml = _payment_xml(bill, bill.total_amount, "TRX-REPEAT-1")
    process_payment_notification(xml)
    process_payment_notification(xml)

    assert Payment.objects.filter(trx_id="TRX-REPEAT-1").count() == 1
    stone = billable_order.stones.first()
    assert (
        StatusHistory.objects.filter(stone=stone, to_status=StoneStatus.PAID).count() == 1
    )


def test_a_partial_payment_leaves_the_bill_unsettled(billable_order):
    """Stones stay billed until the full amount arrives."""
    from apps.billing.dev import _payment_xml
    from apps.billing.services import process_payment_notification

    bill = generate_bill_for_order(billable_order)
    bill.control_number = "991234567891"
    bill.save(update_fields=["control_number"])

    process_payment_notification(_payment_xml(bill, Decimal("50000.00"), "TRX-PARTIAL-1"))

    bill.refresh_from_db()
    assert bill.status == BillStatus.PARTIALLY_PAID
    assert set(billable_order.stones.values_list("status", flat=True)) == {
        StoneStatus.BILLED
    }


def test_an_unparseable_notification_returns_a_failure_ack():
    """A malformed body still gets well-formed XML, or GePG keeps retrying."""
    from apps.billing.services import process_payment_notification

    ack = process_payment_notification("not xml at all")

    assert "7102" in ack
    assert ack.strip().startswith("<")


def test_a_notification_matching_only_the_control_number_still_settles(billable_order):
    """The bill is looked up by number or by control number.

    GePG echoes back whichever identifier it holds, so a notification quoting an
    unrecognised bill id but the right control number must still be applied.
    """
    from apps.billing.dev import _payment_xml
    from apps.billing.services import process_payment_notification

    bill = generate_bill_for_order(billable_order)
    assert bill.control_number, "simulate mode should have issued a control number"

    xml = _payment_xml(bill, bill.total_amount, "TRX-CTRL-1").replace(
        bill.bill_number, "BILL-9999-9999"
    )
    ack = process_payment_notification(xml)

    assert "7101" in ack
    bill.refresh_from_db()
    assert bill.status == BillStatus.PAID


def test_a_notification_for_an_unknown_bill_returns_a_failure_ack(billable_order):
    """An unmatched bill is a failure ack, not an exception."""
    from apps.billing.dev import _payment_xml
    from apps.billing.services import process_payment_notification

    bill = generate_bill_for_order(billable_order)
    xml = (
        _payment_xml(bill, bill.total_amount, "TRX-GHOST-1")
        .replace(bill.bill_number, "BILL-9999-9999")
        .replace(bill.control_number, "990000000000")
    )

    ack = process_payment_notification(xml)

    assert "7102" in ack
    assert not Payment.objects.filter(trx_id="TRX-GHOST-1").exists()


def test_billing_worklist_holds_only_fully_registered_unbilled_orders(settings):
    """An order enters the queue when its last stone is typed, and leaves when billed."""
    settings.GEPG_SIMULATE = True
    order = OrderFactory(stone_count=2)
    stone_type = StoneTypeFactory(price=Decimal("1000.00"))

    add_stone(order, stone_type=stone_type)
    assert order not in billing_worklist()

    add_stone(order, stone_type=stone_type)
    assert order in billing_worklist()

    generate_bill_for_order(order)
    assert order not in billing_worklist()


def test_generate_endpoint_requires_the_generate_permission(
    billable_order, viewer_user, auth_client
):
    """Billing is the accountant's job; a receptionist is refused."""
    response = auth_client(viewer_user).post(
        "/api/v1/bills/generate/", {"order": billable_order.pk}
    )

    assert response.status_code == 403


def test_generate_endpoint_creates_the_bill(billable_order, admin_user, auth_client):
    """The endpoint delegates to the service and returns the bill."""
    response = auth_client(admin_user).post(
        "/api/v1/bills/generate/", {"order": billable_order.pk}
    )

    assert response.status_code == 201, response.data
    assert response.data["total_amount"] == "150000.00"
    assert len(response.data["items"]) == 3


def test_bills_are_not_client_writable(billable_order, admin_user, auth_client):
    """A bill is written by the service and the gateway, never by a client."""
    bill = generate_bill_for_order(billable_order)

    response = auth_client(admin_user).patch(
        f"/api/v1/bills/{bill.pk}/", {"status": BillStatus.PAID}
    )

    assert response.status_code == 405
    bill.refresh_from_db()
    assert bill.status == BillStatus.PENDING


def test_payment_webhook_needs_no_authentication(billable_order, client):
    """The gateway has no credentials; the callback must not 401.

    This is the URL GePG posts to, so a 401 here would silently strand every
    payment in the system.
    """
    from apps.billing.dev import _payment_xml

    bill = generate_bill_for_order(billable_order)
    bill.control_number = "991234567892"
    bill.save(update_fields=["control_number"])
    xml = _payment_xml(bill, bill.total_amount, "TRX-WEBHOOK-1")

    response = client.post(
        "/gepg/payments/notification/", data=xml, content_type="application/xml"
    )

    assert response.status_code == 200
    assert b"7101" in response.content

    bill.refresh_from_db()
    assert bill.status == BillStatus.PAID


def test_listing_bills_does_not_n_plus_one(
    billable_order, admin_user, auth_client, django_assert_max_num_queries
):
    """Joins are explicit, so the query count does not grow with the page."""
    for _ in range(5):
        order = OrderFactory(stone_count=1)
        add_stone(order, stone_type=StoneTypeFactory(price=Decimal("1000.00")))
        generate_bill_for_order(order)

    client = auth_client(admin_user)
    with django_assert_max_num_queries(12):
        response = client.get("/api/v1/bills/")

    assert response.status_code == 200
    assert response.data["count"] == 5
