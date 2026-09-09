"""Certificate issuance, its three guards, revocation and public verification."""

from decimal import Decimal

import pytest

from apps.billing.dev import simulate_payment
from apps.billing.services import generate_bill_for_order
from apps.certificates.models import Certificate, CertificateAccessLog
from apps.certificates.selectors import certification_worklist
from apps.certificates.services import issue_certificate, revoke_certificate
from apps.core.exceptions import ServiceError
from apps.gems.enums import CertificateStatus, StoneStatus
from apps.gems.tests.factories import ColorFactory, OriginFactory, StoneTypeFactory
from apps.identification.services import create_report, finalize_report
from apps.orders.models import StatusHistory
from apps.orders.services import add_stone
from apps.orders.tests.factories import OrderFactory

pytestmark = pytest.mark.django_db


def _paid_stone(settings, *, weight=Decimal("2.500")):
    """A stone whose order is billed and settled."""
    settings.GEPG_SIMULATE = True
    order = OrderFactory(stone_count=1)
    stone = add_stone(
        order, stone_type=StoneTypeFactory(price=Decimal("50000.00")), weight=weight
    )
    simulate_payment(generate_bill_for_order(order))
    stone.refresh_from_db()
    return stone


@pytest.fixture
def certifiable_stone(settings, user):
    """A paid stone with a finalized report - ready to certify."""
    stone = _paid_stone(settings)
    report = create_report(
        stone=stone,
        user=user,
        color=ColorFactory(name="Red"),
        origin=OriginFactory(name="Tanzania"),
    )
    finalize_report(report, user=user)
    return stone


def test_issuing_freezes_the_findings(certifiable_stone, user):
    """The snapshot is the point: the document must keep saying the same thing."""
    certificate = issue_certificate(certifiable_stone, user=user)

    assert certificate.certificate_number.startswith("CERT-")
    assert len(certificate.verification_token) == 64
    assert certificate.stone_type_snapshot == certifiable_stone.stone_type.name
    assert certificate.weight_snapshot == Decimal("2.500")
    assert certificate.color_snapshot == "Red"
    assert certificate.origin_snapshot == "Tanzania"
    assert certificate.status == CertificateStatus.ISSUED


def test_snapshots_survive_the_lookup_being_renamed(certifiable_stone, user):
    """Renaming a colour must not rewrite a certificate already issued."""
    certificate = issue_certificate(certifiable_stone, user=user)
    color = certifiable_stone.report.color
    color.name = "Crimson"
    color.save(update_fields=["name"])

    certificate.refresh_from_db()
    assert certificate.color_snapshot == "Red"


def test_issuing_certifies_the_stone(certifiable_stone, user):
    """Certification is the stone's last status move, and it is recorded."""
    certificate = issue_certificate(certifiable_stone, user=user)

    certifiable_stone.refresh_from_db()
    assert certifiable_stone.status == StoneStatus.CERTIFIED

    entry = StatusHistory.objects.filter(
        stone=certifiable_stone, to_status=StoneStatus.CERTIFIED
    ).latest("changed_at")
    assert certificate.certificate_number in entry.note


def test_a_stone_cannot_be_certified_twice(certifiable_stone, user):
    """One certificate per stone."""
    issue_certificate(certifiable_stone, user=user)

    with pytest.raises(ServiceError, match="already has a certificate"):
        issue_certificate(certifiable_stone, user=user)


def test_a_revoked_certificate_still_blocks_reissue(certifiable_stone, user):
    """Ported behaviour: the existence check is not status-aware.

    Revoking does not free the stone to be certified again - there is no
    re-issue path, which is why ``CertificateStatus.REISSUED`` is unreachable.
    """
    certificate = issue_certificate(certifiable_stone, user=user)
    revoke_certificate(certificate, user=user)

    with pytest.raises(ServiceError, match="already has a certificate"):
        issue_certificate(certifiable_stone, user=user)


def test_certification_needs_a_finalized_report(settings, user):
    """A draft is not evidence."""
    stone = _paid_stone(settings)
    create_report(stone=stone, user=user)

    with pytest.raises(ServiceError, match="no finalized identification report"):
        issue_certificate(stone, user=user)


def test_certification_needs_a_report_at_all(settings, user):
    """Nothing to certify without findings."""
    stone = _paid_stone(settings)

    with pytest.raises(ServiceError, match="no finalized identification report"):
        issue_certificate(stone, user=user)


def test_certification_needs_a_settled_bill(certifiable_stone, user):
    """Payment gates the document, not just the bench work.

    The bill is un-settled directly rather than by building an unpaid stone,
    because the guards run in order: a stone with no finalized report is refused
    on the report guard and never reaches this one. And a report cannot be
    created before payment in the first place - so this guard is defence in
    depth against a bill that is later reversed.
    """
    from apps.gems.enums import BillStatus

    bill = certifiable_stone.order.bill
    bill.status = BillStatus.PARTIALLY_PAID
    bill.save(update_fields=["status"])

    with pytest.raises(ServiceError, match="bill must be fully paid"):
        issue_certificate(certifiable_stone, user=user)


def test_certification_needs_a_recorded_weight(settings, user):
    """A certificate states a weight, so it must have one.

    The snapshot column is non-null and weight is optional until this point, so
    without the guard this would surface as an IntegrityError rather than the
    rule it actually expresses.
    """
    stone = _paid_stone(settings, weight=None)
    finalize_report(create_report(stone=stone, user=user), user=user)

    with pytest.raises(ServiceError, match="no recorded weight"):
        issue_certificate(stone, user=user)


def test_revoking_is_one_way(certifiable_stone, user):
    """A withdrawn certificate cannot be withdrawn twice."""
    certificate = issue_certificate(certifiable_stone, user=user)
    revoke_certificate(certificate, user=user)

    certificate.refresh_from_db()
    assert certificate.status == CertificateStatus.REVOKED

    with pytest.raises(ServiceError, match="already revoked"):
        revoke_certificate(certificate, user=user)


def test_certification_worklist_is_the_three_guards_as_a_queue(
    settings, certifiable_stone, user
):
    """A stone enters when its report is signed off, and leaves when certified."""
    unfinalized = _paid_stone(settings)
    create_report(stone=unfinalized, user=user)

    assert certifiable_stone in certification_worklist()
    assert unfinalized not in certification_worklist()

    issue_certificate(certifiable_stone, user=user)
    assert certifiable_stone not in certification_worklist()


def test_issue_endpoint_requires_the_issue_permission(
    certifiable_stone, viewer_user, auth_client
):
    """Reception hands the certificate over; it does not issue it."""
    response = auth_client(viewer_user).post(
        "/api/v1/certificates/", {"stone": certifiable_stone.pk}
    )

    assert response.status_code == 403
    assert not Certificate.objects.filter(stone=certifiable_stone).exists()


def test_issue_endpoint_creates_the_certificate(
    certifiable_stone, admin_user, auth_client
):
    """The endpoint delegates wholly to the service."""
    response = auth_client(admin_user).post(
        "/api/v1/certificates/", {"stone": certifiable_stone.pk}
    )

    assert response.status_code == 201, response.data
    assert response.data["certificate_number"].startswith("CERT-")
    assert response.data["stone_label"] == certifiable_stone.label


def test_certificate_fields_are_not_client_writable(
    certifiable_stone, admin_user, auth_client
):
    """The snapshots are the document; a client must not edit them."""
    certificate = issue_certificate(certifiable_stone)

    response = auth_client(admin_user).patch(
        f"/api/v1/certificates/{certificate.pk}/",
        {"stone_type_snapshot": "Something else", "status": CertificateStatus.REVOKED},
    )

    assert response.status_code == 200, response.data
    certificate.refresh_from_db()
    assert certificate.stone_type_snapshot != "Something else"
    assert certificate.status == CertificateStatus.ISSUED


def test_public_verification_needs_no_authentication(certifiable_stone, client):
    """Anyone holding the printed certificate can check it."""
    certificate = issue_certificate(certifiable_stone)

    response = client.get(
        f"/api/v1/certificates/verify/{certificate.verification_token}/"
    )

    assert response.status_code == 200, response.content
    assert response.data["certificate_number"] == certificate.certificate_number
    assert response.data["is_valid"] is True


def test_public_verification_exposes_only_the_document(certifiable_stone, client):
    """The customer, the order and the audit trail are nobody else's business."""
    certificate = issue_certificate(certifiable_stone)

    response = client.get(
        f"/api/v1/certificates/verify/{certificate.verification_token}/"
    )

    assert set(response.data) == {
        "certificate_number",
        "status",
        "is_valid",
        "issued_at",
        "stone_type_snapshot",
        "weight_snapshot",
        "color_snapshot",
        "origin_snapshot",
        "gemmologist",
    }


def test_a_revoked_certificate_verifies_but_does_not_stand(certifiable_stone, client):
    """It must still resolve, so the holder learns it was withdrawn."""
    certificate = issue_certificate(certifiable_stone)
    revoke_certificate(certificate)

    response = client.get(
        f"/api/v1/certificates/verify/{certificate.verification_token}/"
    )

    assert response.status_code == 200
    assert response.data["status"] == CertificateStatus.REVOKED
    assert response.data["is_valid"] is False


def test_verification_is_logged(certifiable_stone, client):
    """Who checked a certificate, and when, is part of the trail."""
    certificate = issue_certificate(certifiable_stone)

    client.get(
        f"/api/v1/certificates/verify/{certificate.verification_token}/",
        HTTP_USER_AGENT="Mozilla/5.0 (test)",
    )

    log = CertificateAccessLog.objects.get(certificate=certificate)
    assert log.user_agent == "Mozilla/5.0 (test)"
    assert log.ip_address is not None


def test_an_unknown_token_is_a_404_and_logs_nothing(client):
    """A guessed token must not create a log entry."""
    response = client.get(f"/api/v1/certificates/verify/{'0' * 64}/")

    assert response.status_code == 404
    assert not CertificateAccessLog.objects.exists()


def test_listing_certificates_does_not_n_plus_one(
    settings, admin_user, auth_client, django_assert_max_num_queries, user
):
    """Every relation a certificate renders is joined up front.

    Rows are created with an actor so ``created_by``/``updated_by`` are set: a
    factory-built row leaves them null, and the audit labels then short-circuit
    without a lookup, hiding the very N+1 this is meant to catch.
    """
    for _ in range(5):
        stone = _paid_stone(settings)
        finalize_report(create_report(stone=stone, user=user), user=user)
        issue_certificate(stone, user=user)

    client = auth_client(admin_user)
    with django_assert_max_num_queries(8):
        response = client.get("/api/v1/certificates/")

    assert response.status_code == 200
    assert response.data["count"] == 5
