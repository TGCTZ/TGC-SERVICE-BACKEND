"""Findings, the payment gate and the finalize lock."""

from decimal import Decimal

import pytest

from apps.billing.dev import simulate_payment
from apps.billing.services import generate_bill_for_order
from apps.core.exceptions import ServiceError
from apps.gems.tests.factories import (
    ColorFactory,
    InstrumentFactory,
    SpeciesFactory,
    StoneTypeFactory,
)
from apps.identification.models import IdentificationReport, InstrumentUsed
from apps.identification.selectors import findings_worklist
from apps.identification.services import create_report, finalize_report, update_report
from apps.orders.services import add_stone
from apps.orders.tests.factories import OrderFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def paid_stone(settings):
    """A stone whose order has been billed and settled."""
    settings.GEPG_SIMULATE = True
    order = OrderFactory(stone_count=1)
    stone = add_stone(order, stone_type=StoneTypeFactory(price=Decimal("50000.00")))
    simulate_payment(generate_bill_for_order(order))
    stone.refresh_from_db()
    return stone


@pytest.fixture
def billed_stone(settings):
    """A stone billed but not yet paid for."""
    settings.GEPG_SIMULATE = True
    order = OrderFactory(stone_count=1)
    stone = add_stone(order, stone_type=StoneTypeFactory(price=Decimal("50000.00")))
    generate_bill_for_order(order)
    stone.refresh_from_db()
    return stone


def test_create_report_allocates_a_number(paid_stone, user):
    """The service, not the client, mints RPT-YYYY-NNNN."""
    report = create_report(stone=paid_stone, user=user)

    assert report.report_number.startswith("RPT-")
    assert report.identified_by == user
    assert not report.is_finalized


def test_findings_are_refused_before_payment(billed_stone):
    """Work starts only once the customer has paid.

    The gate lives in the service rather than the view, because an API offers
    more than one route to a report.
    """
    with pytest.raises(ServiceError, match="bill must be paid"):
        create_report(stone=billed_stone)


def test_findings_are_refused_when_the_order_has_no_bill():
    """A stone that was never billed cannot be worked on either."""
    order = OrderFactory(stone_count=1)
    stone = add_stone(order, stone_type=StoneTypeFactory(price=Decimal("1000.00")))

    with pytest.raises(ServiceError, match="bill must be paid"):
        create_report(stone=stone)


def test_a_draft_report_can_be_edited(paid_stone, user):
    """Findings are built up over a sitting, so a draft stays open."""
    report = create_report(stone=paid_stone, user=user)
    species = SpeciesFactory(name="Corundum")

    update_report(report, user=user, species=species, refractive_index="1.762-1.770")

    report.refresh_from_db()
    assert report.species == species
    assert report.refractive_index == "1.762-1.770"


def test_finalizing_locks_the_report(paid_stone, user):
    """The lock is one-way and stamps who signed it off."""
    report = create_report(stone=paid_stone, user=user)
    finalize_report(report, user=user)

    report.refresh_from_db()
    assert report.is_finalized
    assert report.identified_at is not None
    assert report.identified_by == user


def test_a_finalized_report_cannot_be_edited(paid_stone, user):
    """The strongest guard in the system.

    A certificate quotes the report, so findings that could still change after
    finalization would make an issued certificate a claim about nothing.
    """
    report = create_report(stone=paid_stone, user=user)
    finalize_report(report, user=user)

    with pytest.raises(ServiceError, match="finalized report cannot be edited"):
        update_report(report, conclusion="Actually, no.")


def test_a_report_cannot_be_finalized_twice(paid_stone, user):
    """There is no un-finalize, so a second call is a mistake worth reporting."""
    report = create_report(stone=paid_stone, user=user)
    finalize_report(report, user=user)

    with pytest.raises(ServiceError, match="already finalized"):
        finalize_report(report, user=user)


def test_findings_worklist_holds_paid_unfinalized_stones(paid_stone, billed_stone, user):
    """The queue is exactly the bench's inbox."""
    assert paid_stone in findings_worklist()
    assert billed_stone not in findings_worklist()

    report = create_report(stone=paid_stone, user=user)
    assert paid_stone in findings_worklist(), "a draft is still work in progress"

    finalize_report(report, user=user)
    assert paid_stone not in findings_worklist()


def test_report_endpoint_creates_via_the_service(paid_stone, admin_user, auth_client):
    """POST mints the number and ignores a client-supplied one."""
    response = auth_client(admin_user).post(
        "/api/v1/identification-reports/",
        {
            "stone": paid_stone.pk,
            "report_number": "CLIENT-SUPPLIED",
            "conclusion": "Natural ruby.",
            "color": ColorFactory().pk,
        },
    )

    assert response.status_code == 201, response.data
    assert response.data["report_number"].startswith("RPT-")
    assert response.data["identified_by_label"] is not None


def test_report_endpoint_refuses_before_payment(billed_stone, admin_user, auth_client):
    """The service's refusal surfaces as a 400 carrying its message."""
    response = auth_client(admin_user).post(
        "/api/v1/identification-reports/", {"stone": billed_stone.pk}
    )

    assert response.status_code == 400
    assert "bill must be paid" in str(response.data)


def test_finalize_endpoint_requires_the_finalize_permission(
    paid_stone, viewer_user, auth_client
):
    """Signing off findings is the gemmologist's job, not reception's."""
    report = create_report(stone=paid_stone)
    response = auth_client(viewer_user).post(
        f"/api/v1/identification-reports/{report.pk}/finalize/"
    )

    assert response.status_code == 403
    report.refresh_from_db()
    assert not report.is_finalized


def test_patching_a_finalized_report_is_refused(paid_stone, admin_user, auth_client):
    """The lock holds over the API, not just in the service."""
    report = create_report(stone=paid_stone)
    client = auth_client(admin_user)
    client.post(f"/api/v1/identification-reports/{report.pk}/finalize/")

    response = client.patch(
        f"/api/v1/identification-reports/{report.pk}/",
        {"conclusion": "Rewritten after the fact."},
    )

    assert response.status_code == 400
    report.refresh_from_db()
    assert report.conclusion == ""


def test_is_finalized_is_not_directly_writable(paid_stone, admin_user, auth_client):
    """A report must not be locked by a field write, bypassing the stamp.

    Setting the flag directly would leave identified_at and identified_by empty,
    so the certificate would name no gemmologist.
    """
    report = create_report(stone=paid_stone)
    response = auth_client(admin_user).patch(
        f"/api/v1/identification-reports/{report.pk}/", {"is_finalized": True}
    )

    assert response.status_code == 200, response.data
    report.refresh_from_db()
    assert not report.is_finalized
    assert report.identified_at is None


def test_instruments_cannot_be_added_to_a_finalized_report(
    paid_stone, admin_user, auth_client
):
    """The lock covers the readings too, or it means nothing."""
    report = create_report(stone=paid_stone)
    client = auth_client(admin_user)

    first = client.post(
        "/api/v1/instruments-used/",
        {"report": report.pk, "instrument": InstrumentFactory().pk, "reading": "1.76"},
    )
    assert first.status_code == 201, first.data

    client.post(f"/api/v1/identification-reports/{report.pk}/finalize/")

    second = client.post(
        "/api/v1/instruments-used/",
        {"report": report.pk, "instrument": InstrumentFactory().pk, "reading": "1.54"},
    )
    assert second.status_code == 400
    assert InstrumentUsed.objects.filter(report=report).count() == 1


def test_findings_worklist_endpoint_lists_stones(paid_stone, admin_user, auth_client):
    """The queue endpoint returns stones, not reports."""
    response = auth_client(admin_user).get("/api/v1/identification-reports/worklist/")

    assert response.status_code == 200, response.data
    assert response.data["count"] == 1
    assert response.data["results"][0]["label"] == paid_stone.label


def test_listing_reports_does_not_n_plus_one(
    settings, admin_user, auth_client, django_assert_max_num_queries
):
    """Every lookup a report expands is joined up front."""
    settings.GEPG_SIMULATE = True
    for _ in range(5):
        order = OrderFactory(stone_count=1)
        stone = add_stone(order, stone_type=StoneTypeFactory(price=Decimal("1000.00")))
        simulate_payment(generate_bill_for_order(order))
        create_report(stone=stone, species=SpeciesFactory(), color=ColorFactory())

    client = auth_client(admin_user)
    with django_assert_max_num_queries(12):
        response = client.get("/api/v1/identification-reports/")

    assert response.status_code == 200
    assert response.data["count"] == 5
    assert IdentificationReport.objects.count() == 5
