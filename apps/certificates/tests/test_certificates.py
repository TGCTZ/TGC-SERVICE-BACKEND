"""Certificate issuance, its three guards, revocation and PDF download."""

from decimal import Decimal

import pytest

from apps.billing.dev import simulate_payment
from apps.billing.services import generate_bill_for_order
from apps.certificates.models import Certificate
from apps.certificates.selectors import certification_worklist
from apps.certificates.services import issue_certificate, revoke_certificate
from apps.certificates.services.pdf import certificate_context
from apps.core.exceptions import ServiceError
from apps.gems.enums import (
    CertificateStatus,
    NatureType,
    OpticCharacter,
    StoneStatus,
    Transparency,
    Treatment,
    WeightUnit,
)
from apps.gems.tests.factories import (
    ColorFactory,
    InstrumentFactory,
    OriginFactory,
    ShapeCutFactory,
    SpeciesFactory,
    StoneTypeFactory,
    VarietyFactory,
)
from apps.identification.models import InstrumentUsed
from apps.identification.services import create_report, finalize_report
from apps.orders.models import StatusHistory
from apps.orders.services import add_stone, update_stone
from apps.orders.tests.factories import OrderFactory

pytestmark = pytest.mark.django_db


def _paid_stone(settings, *, weight=Decimal("2.500")):
    """A stone whose order is billed and settled, and weighed at the bench.

    Weight arrives after the refresh, not with ``add_stone``: identification
    records the type only, and the bench weighs the stone during the findings.
    """
    settings.GEPG_SIMULATE = True
    order = OrderFactory(stone_count=1)
    stone = add_stone(order, stone_type=StoneTypeFactory(price=Decimal("50000.00")))
    simulate_payment(generate_bill_for_order(order))
    stone.refresh_from_db()
    if weight is not None:
        update_stone(stone, weight=weight)
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
    assert certificate.stone_type_snapshot == certifiable_stone.stone_type.name
    assert certificate.weight_snapshot == Decimal("2.500")
    assert certificate.weight_unit_snapshot == WeightUnit.CARAT
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


def test_pdf_download_returns_a_pdf(certifiable_stone, admin_user, auth_client):
    """The PDF is how a certificate leaves the system."""
    certificate = issue_certificate(certifiable_stone)

    response = auth_client(admin_user).get(f"/api/v1/certificates/{certificate.pk}/pdf/")

    assert response.status_code == 200, response.content
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert certificate.certificate_number in response["Content-Disposition"]


def test_pdf_download_requires_the_view_permission(
    certifiable_stone, viewer_user, auth_client
):
    """Reception holds no certificate permissions, so it cannot pull documents."""
    certificate = issue_certificate(certifiable_stone)

    response = auth_client(viewer_user).get(f"/api/v1/certificates/{certificate.pk}/pdf/")

    assert response.status_code == 403


def test_a_revoked_certificate_still_downloads(
    certifiable_stone, admin_user, auth_client
):
    """Refusing would leave staff unable to reconcile paperwork."""
    certificate = issue_certificate(certifiable_stone)
    revoke_certificate(certificate)

    response = auth_client(admin_user).get(f"/api/v1/certificates/{certificate.pk}/pdf/")

    assert response.status_code == 200
    assert "-revoked.pdf" in response["Content-Disposition"]


def test_the_document_says_what_it_said_when_issued(certifiable_stone, user):
    """Renaming a colour afterwards must not rewrite a document already handed over.

    Asserted against the template context rather than the PDF bytes: the
    guarantee is about which values reach the page, and parsing a PDF to prove
    it would test WeasyPrint instead.
    """
    certificate = issue_certificate(certifiable_stone, user=user)
    report = certificate.report
    report.color.name = "Crimson"
    report.color.save()

    context = certificate_context(certificate)

    assert context["certificate"].color_snapshot == "Red"
    assert context["order_reference"] == certifiable_stone.order.reference_number
    assert context["customer_name"] == certifiable_stone.order.customer.full_name
    assert context["is_revoked"] is False


# ---------------------------------------------------------------------------
# The full snapshot set, the QR, and public verification
# ---------------------------------------------------------------------------
def test_certificate_freezes_every_finding_it_prints(settings, user):
    """The document keeps its own copy of each word, not a live reference.

    The point of the whole snapshot block: editing the lookup rows afterwards
    must not change what an issued certificate says.
    """
    stone = _paid_stone(settings)
    species = SpeciesFactory(name="Corundum")
    variety = VarietyFactory(name="Ruby")
    shape = ShapeCutFactory(name="Oval")
    report = create_report(
        stone=stone,
        user=user,
        species=species,
        variety=variety,
        shape_cut=shape,
        color=ColorFactory(name="Pigeon blood"),
        origin=OriginFactory(name="Mogok"),
        transparency=Transparency.TRANSPARENT,
        optic_character=OpticCharacter.DR,
        treatment=Treatment.HEATED,
        nature_type=NatureType.NATURAL,
        refractive_index="1.762-1.770",
        dimensions="8.1 x 6.0 x 4.2 mm",
        conclusion="Natural ruby, heated.",
    )
    finalize_report(report, user=user)

    certificate = issue_certificate(stone, user=user)

    assert certificate.species_snapshot == "Corundum"
    assert certificate.variety_snapshot == "Ruby"
    assert certificate.shape_cut_snapshot == "Oval"
    assert certificate.origin_snapshot == "Mogok"
    assert certificate.refractive_index_snapshot == "1.762-1.770"
    assert certificate.dimensions_snapshot == "8.1 x 6.0 x 4.2 mm"
    assert certificate.comments_snapshot == "Natural ruby, heated."
    assert certificate.report_number_snapshot == report.report_number

    # Enum labels, not stored codes - the document is read by a customer.
    assert certificate.transparency_snapshot == "Transparent"
    assert certificate.treatment_snapshot == "Heated"
    assert "refractive" in certificate.optic_character_snapshot.lower()

    # Now rewrite the world the findings came from.
    species.name = "Renamed later"
    species.save()
    variety.name = "Also renamed"
    variety.save()

    certificate.refresh_from_db()
    assert certificate.species_snapshot == "Corundum"
    assert certificate.variety_snapshot == "Ruby"


def test_certificate_names_both_gemmologists(settings, user, admin_user):
    """Two signatories, because the document claims two examined the stone."""
    stone = _paid_stone(settings)
    report = create_report(stone=stone, user=user)
    finalize_report(report, user=user, verified_by=admin_user)

    certificate = issue_certificate(stone, user=user)

    assert certificate.gemmologist == (user.get_full_name() or user.username)
    assert certificate.gemmologist_two == (
        admin_user.get_full_name() or admin_user.username
    )


def test_the_second_gemmologist_must_be_someone_else(settings, user):
    """A second opinion from the same head is not a second opinion."""
    stone = _paid_stone(settings)
    report = create_report(stone=stone, user=user)

    with pytest.raises(ServiceError, match="different person"):
        finalize_report(report, user=user, verified_by=user)


def test_certificate_snapshots_the_instruments_used(settings, user):
    """Instruments print as words on the document, so they freeze as words."""
    stone = _paid_stone(settings)
    report = create_report(stone=stone, user=user)
    instrument = InstrumentFactory(name="Refractometer")
    InstrumentUsed.objects.create(
        report=report, instrument=instrument, reading="1.762-1.770"
    )
    finalize_report(report, user=user)

    certificate = issue_certificate(stone, user=user)

    assert certificate.instruments_snapshot == [
        {"name": "Refractometer", "reading": "1.762-1.770"}
    ]

    instrument.name = "Renamed instrument"
    instrument.save()
    certificate.refresh_from_db()
    assert certificate.instruments_snapshot[0]["name"] == "Refractometer"


def test_certificate_context_carries_a_qr_and_the_lab_marks(settings, user):
    """The QR is built at render time and points at the public verify URL."""
    settings.CERTIFICATE_VERIFY_BASE_URL = "https://tgc.example"
    stone = _paid_stone(settings)
    report = create_report(stone=stone, user=user)
    finalize_report(report, user=user)
    certificate = issue_certificate(stone, user=user)

    context = certificate_context(certificate)

    assert context["verify_url"] == (
        f"https://tgc.example/verify/{certificate.certificate_number}/"
    )
    assert context["qr_code"].startswith("data:image/png;base64,")
    # Assets are optional: a lab that has not supplied its stamp still gets a
    # certificate, so the key is present and may be None.
    assert "official_stamp" in context


def test_verify_page_is_public_and_reports_a_valid_certificate(settings, user, client):
    """Whoever holds the paper can check it without an account."""
    stone = _paid_stone(settings)
    report = create_report(stone=stone, user=user)
    finalize_report(report, user=user)
    certificate = issue_certificate(stone, user=user)

    response = client.get(f"/verify/{certificate.certificate_number}/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "Valid certificate" in body
    assert certificate.certificate_number in body
    # The public page identifies the stone, never its owner.
    assert stone.order.customer.full_name not in body


def test_verify_page_says_so_when_a_certificate_is_revoked(settings, user, client):
    """The whole reason a revoked certificate keeps its number and its row."""
    stone = _paid_stone(settings)
    report = create_report(stone=stone, user=user)
    finalize_report(report, user=user)
    certificate = issue_certificate(stone, user=user)
    revoke_certificate(certificate, user=user)

    response = client.get(f"/verify/{certificate.certificate_number}/")

    assert response.status_code == 200
    assert "no longer stands" in response.content.decode()


def test_verify_page_answers_plainly_for_an_unknown_number(client):
    """A 404 page would tell whoever scanned it nothing useful."""
    response = client.get("/verify/CERT-2026-9999/")

    assert response.status_code == 404
    assert "Not found" in response.content.decode()
