"""Order intake, stone registration and status transitions."""

import pytest

from apps.core.exceptions import ServiceError
from apps.gems.enums import StoneStatus
from apps.gems.tests.factories import StoneTypeFactory
from apps.orders.models import Order, StatusHistory
from apps.orders.selectors import registration_worklist
from apps.orders.services import add_stone, create_order, transition_stone
from apps.orders.tests.factories import CustomerFactory, OrderFactory, StoneFactory

pytestmark = pytest.mark.django_db


def test_create_order_allocates_a_reference_number():
    """The service, not the client, mints ORD-YYYY-NNNN."""
    order = create_order(customer=CustomerFactory(), stone_count=2)

    assert order.reference_number.startswith("ORD-")
    assert order.reference_number.endswith("-0001")


def test_reference_numbers_do_not_reuse_a_deleted_one():
    """Numbering scans all rows, so a soft-deleted number is never reissued.

    Reusing a reference number would make two different orders indistinguishable
    in any record that kept only the string.
    """
    first = create_order(customer=CustomerFactory(), stone_count=1)
    first.delete()
    second = create_order(customer=CustomerFactory(), stone_count=1)

    assert second.reference_number != first.reference_number


def test_add_stone_labels_stones_in_sequence():
    """Stones are lettered in registration order."""
    order = OrderFactory(stone_count=3)
    stone_type = StoneTypeFactory()

    labels = [
        add_stone(order, stone_type=stone_type).label,
        add_stone(order, stone_type=stone_type).label,
        add_stone(order, stone_type=stone_type).label,
    ]

    assert labels == ["A", "B", "C"]


def test_add_stone_refuses_more_than_the_customer_submitted():
    """The count the customer declared is the cap.

    Registering a fourth stone against a three-stone order would mean the lab is
    holding something nobody handed over.
    """
    order = OrderFactory(stone_count=1)
    stone_type = StoneTypeFactory()
    add_stone(order, stone_type=stone_type)

    with pytest.raises(ServiceError):
        add_stone(order, stone_type=stone_type)


def test_add_stone_records_the_first_history_entry():
    """A registered stone starts its trail with an entry from nowhere."""
    order = OrderFactory(stone_count=1)
    stone = add_stone(order, stone_type=StoneTypeFactory())

    entry = StatusHistory.objects.get(stone=stone)
    assert entry.from_status == ""
    assert entry.to_status == StoneStatus.RECEIVED


def test_transition_writes_history_and_records_the_actor(user):
    """Every status change leaves a trail naming who made it."""
    stone = StoneFactory()
    transition_stone(stone, StoneStatus.BILLED, user=user, note="Billed on BILL-1")

    stone.refresh_from_db()
    assert stone.status == StoneStatus.BILLED

    entry = StatusHistory.objects.filter(stone=stone).latest("changed_at")
    assert entry.from_status == StoneStatus.RECEIVED
    assert entry.to_status == StoneStatus.BILLED
    assert entry.changed_by == user
    assert entry.note == "Billed on BILL-1"


def test_transition_to_the_same_status_is_a_no_op():
    """A redelivered notification must not double up the history."""
    stone = StoneFactory(status=StoneStatus.PAID)
    transition_stone(stone, StoneStatus.PAID)

    assert not StatusHistory.objects.filter(stone=stone).exists()


def test_transition_without_a_user_is_attributed_to_the_system():
    """A payment callback has no request user, and that must not fail."""
    stone = StoneFactory()
    transition_stone(stone, StoneStatus.PAID, note="Bill settled via GePG")

    entry = StatusHistory.objects.filter(stone=stone).latest("changed_at")
    assert entry.changed_by is None


def test_registration_worklist_holds_only_incomplete_orders():
    """The queue empties as the last stone is registered."""
    order = OrderFactory(stone_count=2)
    stone_type = StoneTypeFactory()

    add_stone(order, stone_type=stone_type)
    assert order in registration_worklist()

    add_stone(order, stone_type=stone_type)
    assert order not in registration_worklist()


def test_order_create_endpoint_delegates_to_the_service(admin_user, auth_client):
    """POST /orders/ mints the reference number rather than trusting the client."""
    customer = CustomerFactory()
    response = auth_client(admin_user).post(
        "/api/v1/orders/",
        {
            "customer": customer.pk,
            "stone_count": 2,
            "received_date": "2026-09-09",
            "reference_number": "CLIENT-SUPPLIED",
        },
    )

    assert response.status_code == 201, response.data
    assert response.data["reference_number"].startswith("ORD-")
    assert Order.objects.get(pk=response.data["id"]).stone_count == 2


def test_add_stone_endpoint_registers_and_caps(admin_user, auth_client):
    """The cap surfaces as a 400 carrying the service's message."""
    order = OrderFactory(stone_count=1)
    stone_type = StoneTypeFactory()
    client = auth_client(admin_user)

    first = client.post(
        f"/api/v1/orders/{order.pk}/stones/", {"stone_type": stone_type.pk}
    )
    assert first.status_code == 201, first.data
    assert first.data["label"] == "A"

    second = client.post(
        f"/api/v1/orders/{order.pk}/stones/", {"stone_type": stone_type.pk}
    )
    assert second.status_code == 400
    assert "already registered" in str(second.data)


def test_transition_endpoint_requires_the_transition_permission(admin_user, auth_client):
    """A custom action is gated on its own permission, not on add_stone.

    Regression test for the whole point of ActionPermissions: the transition
    route is a POST, so the method-based map would ask for ``add_stone`` and let
    anyone who can register a stone also move it to certified.
    """
    from django.contrib.auth.models import Permission

    stone = StoneFactory()
    admin_user.user_permissions.add(
        *Permission.objects.filter(
            codename__in=["view_stone", "add_stone", "change_stone"]
        )
    )
    admin_user.groups.clear()

    response = auth_client(admin_user).post(
        f"/api/v1/stones/{stone.pk}/transition/", {"to_status": StoneStatus.CERTIFIED}
    )

    assert response.status_code == 403


def test_transition_endpoint_writes_history(admin_user, auth_client):
    """The endpoint records the acting user in the trail."""
    stone = StoneFactory()
    response = auth_client(admin_user).post(
        f"/api/v1/stones/{stone.pk}/transition/",
        {"to_status": StoneStatus.BILLED, "note": "via API"},
    )

    assert response.status_code == 200, response.data
    assert response.data["status"] == StoneStatus.BILLED

    entry = StatusHistory.objects.filter(stone=stone).latest("changed_at")
    assert entry.changed_by == admin_user
    assert entry.note == "via API"


def test_stone_status_is_not_directly_writable(admin_user, auth_client):
    """PATCHing status must not bypass the history.

    If the field were writable, a client could move a stone to certified without
    leaving any record of who did it or when.
    """
    stone = StoneFactory()
    response = auth_client(admin_user).patch(
        f"/api/v1/stones/{stone.pk}/", {"status": StoneStatus.CERTIFIED}
    )

    assert response.status_code == 200, response.data
    stone.refresh_from_db()
    assert stone.status == StoneStatus.RECEIVED


def test_listing_stones_does_not_n_plus_one(
    admin_user, auth_client, django_assert_max_num_queries
):
    """select_related keeps the query count flat as rows grow."""
    order = OrderFactory(stone_count=10)
    stone_type = StoneTypeFactory()
    for _ in range(10):
        add_stone(order, stone_type=stone_type)

    client = auth_client(admin_user)
    with django_assert_max_num_queries(10):
        response = client.get("/api/v1/stones/")

    assert response.status_code == 200
    assert response.data["count"] == 10


def test_status_history_is_read_only(admin_user, auth_client):
    """The ledger cannot be written through the API.

    Refused twice over: the viewset is read-only so no create route exists, and
    no role is granted ``add_statushistory``. Which of the two answers first is
    an implementation detail - the guarantee is that nothing is written.
    """
    stone = StoneFactory()
    transition_stone(stone, StoneStatus.BILLED)

    client = auth_client(admin_user)
    listing = client.get(f"/api/v1/status-history/?filter[stone]={stone.pk}")
    assert listing.status_code == 200
    assert listing.data["count"] == 1

    before = StatusHistory.objects.count()
    write = client.post(
        "/api/v1/status-history/",
        {"stone": stone.pk, "to_status": StoneStatus.PAID},
    )

    assert write.status_code in (403, 405)
    assert StatusHistory.objects.count() == before
