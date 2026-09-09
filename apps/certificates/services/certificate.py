"""Certificate issuance and revocation."""

import secrets

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceError
from apps.core.services import generate_reference_number
from apps.gems.enums import BillStatus, CertificateStatus, StoneStatus
from apps.orders.services import transition_stone

from ..models import Certificate


@transaction.atomic
def issue_certificate(stone, *, user=None) -> Certificate:
    """Issue a certificate for a stone, freezing the report's findings into it.

    Three guards, in the order a doubt would occur to you: has this stone
    already been certified, are the findings signed off, and has the customer
    paid. The report and bill are reached by traversal rather than by importing
    ``apps.identification`` or ``apps.billing`` - the enum comes from ``gems``,
    so no upward dependency is needed.

    Args:
        stone: The stone to certify.
        user: The issuing gemmologist or administrator.

    Raises:
        ServiceError: If the stone is already certified, its report is missing
            or unfinalized, its bill is unpaid, or no weight was recorded.
    """
    if Certificate.objects.filter(stone=stone).exists():
        raise ServiceError("Stone already has a certificate.")

    report = getattr(stone, "report", None)
    if report is None or not report.is_finalized:
        raise ServiceError("Stone has no finalized identification report.")

    bill = getattr(stone.order, "bill", None)
    if bill is None or bill.status != BillStatus.PAID:
        raise ServiceError("Stone's bill must be fully paid before certification.")

    # The snapshot column is non-null, and weight is optional right up to this
    # point. Refusing here turns what would otherwise be an IntegrityError into
    # the rule it actually expresses: a certificate states a weight.
    if stone.weight is None:
        raise ServiceError("Stone has no recorded weight to certify.")

    gemmologist = ""
    if report.identified_by is not None:
        gemmologist = (
            report.identified_by.get_full_name() or report.identified_by.username
        )

    certificate = Certificate(
        stone=stone,
        report=report,
        certificate_number=generate_reference_number(
            Certificate, "certificate_number", "CERT"
        ),
        verification_token=secrets.token_hex(32),
        stone_type_snapshot=stone.stone_type.name,
        weight_snapshot=stone.weight,
        color_snapshot=report.color.name if report.color else "",
        origin_snapshot=report.origin.name if report.origin else "",
        gemmologist=gemmologist,
        status=CertificateStatus.ISSUED,
        issued_by=user,
        issued_at=timezone.now(),
    )
    if user is not None:
        certificate.created_by = user
    certificate.save()

    transition_stone(
        stone,
        StoneStatus.CERTIFIED,
        user=user,
        note=f"Certified {certificate.certificate_number}",
    )
    return certificate


def revoke_certificate(certificate: Certificate, *, user=None) -> Certificate:
    """Withdraw a certificate.

    The row stays, and so does its number: a revoked certificate must still
    resolve at its public verification URL, because the whole point is to tell
    whoever is holding the paper copy that it no longer stands.

    Raises:
        ServiceError: If the certificate is already revoked.
    """
    if certificate.status == CertificateStatus.REVOKED:
        raise ServiceError("Certificate is already revoked.")
    certificate.status = CertificateStatus.REVOKED
    if user is not None:
        certificate.updated_by = user
    certificate.save(update_fields=["status", "updated_at", "updated_by"])
    return certificate
