"""Certificates feed combines issued certificates and ready stones."""

from decimal import Decimal

import pytest

from apps.billing.dev import simulate_payment
from apps.billing.services import generate_bill_for_order
from apps.certificates.services import issue_certificate
from apps.gems.tests.factories import StoneTypeFactory
from apps.identification.services import finalize_report
from apps.identification.tests.factories import create_finalizable_report
from apps.orders.services import add_stone
from apps.orders.tests.factories import OrderFactory

pytestmark = pytest.mark.django_db


def _ready_stone(settings, user):
    settings.GEPG_SIMULATE = True
    order = OrderFactory(stone_count=1)
    stone = add_stone(order, stone_type=StoneTypeFactory(price=Decimal("50000.00")))
    simulate_payment(generate_bill_for_order(order))
    report = create_finalizable_report(stone, user)
    finalize_report(report, user=user)
    return stone


def test_certificates_feed_contains_issued_and_ready_stones(
    settings, admin_user, auth_client
):
    """Issued certificates and certifiable stones share one feed."""
    issued_stone = _ready_stone(settings, admin_user)
    certificate = issue_certificate(issued_stone, user=admin_user)
    waiting_stone = _ready_stone(settings, admin_user)

    response = auth_client(admin_user).get("/api/v1/certificates/workflow-feed/")

    assert response.status_code == 200
    assert response.data["count"] == 2
    rows = {row["kind"]: row for row in response.data["results"]}
    assert rows["certificate"]["record_id"] == certificate.pk
    assert rows["certificate"]["waiting"] is False
    assert rows["stone"]["record_id"] == waiting_stone.pk
    assert rows["stone"]["waiting"] is True
