"""Order intake, identification and status transitions."""

from decimal import Decimal

import pytest

from apps.billing.services import generate_bill_for_order
from apps.core.exceptions import ServiceError
from apps.gems.enums import StoneStatus, WeightUnit
from apps.gems.tests.factories import StoneTypeFactory
from apps.orders.models import Customer, Order, StatusHistory, Stone
from apps.orders.selectors import identification_worklist
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
    """Stones are lettered in the order they are identified."""
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
    """A newly identified stone starts its trail with an entry from nowhere."""
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


def test_preliminary_worklist_holds_only_incomplete_orders():
    """The queue empties as the last stone is identified."""
    order = OrderFactory(stone_count=2)
    stone_type = StoneTypeFactory()

    add_stone(order, stone_type=stone_type)
    assert order in identification_worklist()

    add_stone(order, stone_type=stone_type)
    assert order not in identification_worklist()


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


def test_add_stone_endpoint_identifies_and_caps(admin_user, auth_client):
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
    assert "already been identified" in str(second.data)


def test_transition_endpoint_requires_the_transition_permission(admin_user, auth_client):
    """A custom action is gated on its own permission, not on add_stone.

    Regression test for the whole point of ActionPermissions: the transition
    route is a POST, so the method-based map would ask for ``add_stone`` and let
    anyone who can identify a stone also move it to certified.
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


def test_an_order_can_register_its_customer(admin_user, auth_client):
    """Reception meets most customers while receiving their first order."""
    response = auth_client(admin_user).post(
        "/api/v1/orders/",
        {
            "customer_data": {
                "first_name": "Asha",
                "last_name": "Mwinyi",
                "phone": "0754123456",
            },
            "stone_count": 2,
            "received_date": "2026-09-13",
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["customer_detail"]["full_name"] == "Asha Mwinyi"
    assert Customer.objects.filter(phone="0754123456").count() == 1


def test_an_order_refuses_both_a_customer_and_new_details(admin_user, auth_client):
    """Sending both means the client does not know whose order this is."""
    before = Order.objects.count()

    response = auth_client(admin_user).post(
        "/api/v1/orders/",
        {
            "customer": CustomerFactory().pk,
            "customer_data": {
                "first_name": "Asha",
                "last_name": "Mwinyi",
                "phone": "0754123456",
            },
            "stone_count": 1,
            "received_date": "2026-09-13",
        },
        format="json",
    )

    assert response.status_code == 400
    assert Order.objects.count() == before


def test_an_order_needs_a_customer_one_way_or_the_other(admin_user, auth_client):
    """Neither field given is the ordinary missing-required-field case."""
    response = auth_client(admin_user).post(
        "/api/v1/orders/",
        {"stone_count": 1, "received_date": "2026-09-13"},
        format="json",
    )

    assert response.status_code == 400
    assert "customer" in response.data


def test_registering_a_customer_needs_the_customer_permission(user, auth_client, roles):
    """The nested write must not route around orders.add_customer."""
    from django.contrib.auth.models import Permission

    user.user_permissions.add(
        Permission.objects.get(codename="add_order", content_type__app_label="orders"),
        Permission.objects.get(codename="view_order", content_type__app_label="orders"),
    )

    response = auth_client(user).post(
        "/api/v1/orders/",
        {
            "customer_data": {
                "first_name": "Asha",
                "last_name": "Mwinyi",
                "phone": "0754123456",
            },
            "stone_count": 1,
            "received_date": "2026-09-13",
        },
        format="json",
    )

    assert response.status_code == 403
    assert not Customer.objects.filter(phone="0754123456").exists()


def test_a_failed_order_leaves_no_orphan_customer(monkeypatch):
    """The customer is created inside the order's transaction, not before it."""
    import apps.orders.services.order as order_service

    def boom(*args, **kwargs):
        raise RuntimeError("reference allocation failed")

    monkeypatch.setattr(order_service, "generate_reference_number", boom)

    with pytest.raises(RuntimeError):
        create_order(
            customer_data={
                "first_name": "Asha",
                "last_name": "Mwinyi",
                "phone": "0754123456",
            },
            stone_count=1,
        )

    assert not Customer.objects.filter(phone="0754123456").exists()


def test_a_duplicate_phone_names_the_existing_customer(admin_user, auth_client):
    """An opaque integrity error would tell reception nothing and offer no way out."""
    existing = CustomerFactory(first_name="Asha", last_name="Mwinyi", phone="0754123456")

    response = auth_client(admin_user).post(
        "/api/v1/customers/",
        {"first_name": "Aisha", "last_name": "M", "phone": "0754123456"},
        format="json",
    )

    assert response.status_code == 400
    assert existing.full_name in str(response.data["phone"])


def test_a_gemmologist_may_identify_a_stone(gemmologist_user, auth_client):
    """Identification is the bench's work, so the bench can do it."""
    order = OrderFactory(stone_count=1)

    response = auth_client(gemmologist_user).post(
        f"/api/v1/orders/{order.pk}/stones/", {"stone_type": StoneTypeFactory().pk}
    )

    assert response.status_code == 201, response.data
    assert response.data["label"] == "A"


def test_a_receptionist_may_no_longer_identify_a_stone(viewer_user, auth_client):
    """Reception records how many stones arrived, not what they are.

    Typing a stone fixes its price, so it belongs to the gemmologist. Reception
    keeps `view_stone` and `transition_stone` for handover.
    """
    order = OrderFactory(stone_count=1)

    response = auth_client(viewer_user).post(
        f"/api/v1/orders/{order.pk}/stones/", {"stone_type": StoneTypeFactory().pk}
    )

    assert response.status_code == 403
    assert not order.stones.exists()


def test_the_preliminary_worklist_belongs_to_the_bench(
    gemmologist_user, viewer_user, auth_client
):
    """The queue is gated on the verb that works it, not on viewing orders."""
    assert (
        auth_client(gemmologist_user).get("/api/v1/orders/worklist/").status_code == 200
    )
    assert auth_client(viewer_user).get("/api/v1/orders/worklist/").status_code == 403


def test_a_receptionist_may_still_hand_a_stone_over(viewer_user, auth_client):
    """Narrowing reception's stone permissions must not break handover."""
    stone = StoneFactory()

    response = auth_client(viewer_user).post(
        f"/api/v1/stones/{stone.pk}/transition/",
        {"to_status": StoneStatus.COLLECTED, "note": "Collected at the front desk"},
    )

    assert response.status_code == 200, response.data


def test_identification_does_not_record_a_weight(admin_user, auth_client):
    """Identification assigns a type; the bench weighs the stone later.

    A weight in the payload is ignored rather than refused - the field does not
    exist here any more, and 400-ing a client that has not caught up would block
    an identification over a value we discard anyway.
    """
    order = OrderFactory(stone_count=1)

    response = auth_client(admin_user).post(
        f"/api/v1/orders/{order.pk}/stones/",
        {"stone_type": StoneTypeFactory().pk, "weight": "2.500"},
    )

    assert response.status_code == 201, response.data
    assert response.data["weight"] is None

    stone = Stone.objects.get(pk=response.data["id"])
    assert stone.weight is None
    assert stone.weight_unit == WeightUnit.CARAT


def test_identification_filter_splits_the_list_in_two(admin_user, auth_client):
    """Pending and complete are disjoint, and together are the whole list."""
    stone_type = StoneTypeFactory()
    pending = OrderFactory(stone_count=2)
    add_stone(pending, stone_type=stone_type)
    complete = OrderFactory(stone_count=1)
    add_stone(complete, stone_type=stone_type)

    client = auth_client(admin_user)

    def refs(params=""):
        response = client.get(f"/api/v1/orders/{params}")
        assert response.status_code == 200, response.data
        return {row["reference_number"] for row in response.data["results"]}

    assert refs("?identification=pending") == {pending.reference_number}
    assert refs("?identification=complete") == {complete.reference_number}
    assert refs() == {pending.reference_number, complete.reference_number}


def test_an_unknown_identification_value_is_ignored(admin_user, auth_client):
    """A stale link degrades to the plain list rather than erroring."""
    OrderFactory(stone_count=1)

    response = auth_client(admin_user).get("/api/v1/orders/?identification=nonsense")

    assert response.status_code == 200, response.data
    assert response.data["count"] == 1


def test_a_billed_stone_cannot_be_retyped(settings, admin_user, auth_client):
    """The type is what priced the bill, so changing it would falsify the bill."""
    settings.GEPG_SIMULATE = True
    order = OrderFactory(stone_count=1)
    stone = add_stone(order, stone_type=StoneTypeFactory(price=Decimal("30000.00")))
    generate_bill_for_order(order)
    stone.refresh_from_db()

    response = auth_client(admin_user).patch(
        f"/api/v1/stones/{stone.pk}/", {"stone_type": StoneTypeFactory().pk}
    )

    assert response.status_code == 400
    assert "priced the bill" in str(response.data)

    original = stone.stone_type_id
    stone.refresh_from_db()
    assert stone.stone_type_id == original


def test_a_billed_stone_still_accepts_its_weight(settings, admin_user, auth_client):
    """Weight arrives after billing by design - the bench weighs at the findings."""
    settings.GEPG_SIMULATE = True
    order = OrderFactory(stone_count=1)
    stone = add_stone(order, stone_type=StoneTypeFactory(price=Decimal("30000.00")))
    generate_bill_for_order(order)
    stone.refresh_from_db()

    response = auth_client(admin_user).patch(
        f"/api/v1/stones/{stone.pk}/", {"weight": "4.250"}
    )

    assert response.status_code == 200, response.data
    stone.refresh_from_db()
    assert stone.weight == Decimal("4.250")


def test_a_received_stone_can_still_be_retyped(admin_user, auth_client):
    """The lock starts at billing, not before."""
    order = OrderFactory(stone_count=1)
    stone = add_stone(order, stone_type=StoneTypeFactory())
    wanted = StoneTypeFactory()

    response = auth_client(admin_user).patch(
        f"/api/v1/stones/{stone.pk}/", {"stone_type": wanted.pk}
    )

    assert response.status_code == 200, response.data
    stone.refresh_from_db()
    assert stone.stone_type_id == wanted.pk


def test_a_billed_stone_cannot_be_deleted(settings, admin_user, auth_client):
    """Deletion bypasses the service, so the viewset repeats the guard."""
    settings.GEPG_SIMULATE = True
    order = OrderFactory(stone_count=1)
    stone = add_stone(order, stone_type=StoneTypeFactory(price=Decimal("30000.00")))
    generate_bill_for_order(order)

    response = auth_client(admin_user).delete(f"/api/v1/stones/{stone.pk}/")

    assert response.status_code == 400
    stone.refresh_from_db()
    assert stone.deleted_at is None
