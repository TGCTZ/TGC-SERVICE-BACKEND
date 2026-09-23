"""Certificate issuance and revocation."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.exceptions import ServiceError
from apps.core.services import generate_reference_number
from apps.gems.enums import BillStatus, CertificateStatus, StoneStatus
from apps.gems.models import Instrument
from apps.orders.services import transition_stone

from ..models import Certificate


def _name(related) -> str:
    """A lookup row's name, or an empty string when the finding was not recorded."""
    return related.name if related is not None else ""


def _person(user) -> str:
    """A user's display name, frozen as text.

    Stored as a string rather than read through the FK at render time so that a
    staff member leaving, being renamed, or being deleted cannot change what an
    issued certificate says it was signed by.
    """
    if user is None:
        return ""
    return user.get_full_name() or user.username


def _instruments(report) -> list[dict]:
    """Every instrument the lab has, each marked used or not.

    The certificate prints the full checklist, so the snapshot freezes the list
    as it stood at issue - adding an instrument later must not add an unticked
    row to an old document. An inactive instrument still appears when this
    report used it: the tick is a fact about the stone.
    """
    used_ids = set(report.instruments_used.values_list("instrument_id", flat=True))
    instruments = Instrument.objects.filter(
        Q(is_active=True) | Q(pk__in=used_ids)
    ).order_by("name")
    return [
        {"name": instrument.name, "used": instrument.pk in used_ids}
        for instrument in instruments
    ]


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

    certificate = Certificate(
        stone=stone,
        report=report,
        certificate_number=generate_reference_number(
            Certificate, "certificate_number", "CERT"
        ),
        stone_type_snapshot=stone.stone_type.name,
        weight_snapshot=stone.weight,
        weight_unit_snapshot=stone.weight_unit,
        color_snapshot=_name(report.color),
        origin_snapshot=_name(report.origin),
        species_snapshot=_name(report.species),
        variety_snapshot=_name(report.variety),
        shape_cut_snapshot=_name(report.shape_cut),
        # Enum *labels*, not stored codes: a customer reads "Singly refractive",
        # not "sr". Frozen for the same reason as everything else here - the
        # label is part of what the document says.
        transparency_snapshot=report.get_transparency_display() or "",
        optic_character_snapshot=report.get_optic_character_display() or "",
        treatment_snapshot=report.get_treatment_display() or "",
        nature_type_snapshot=report.get_nature_type_display() or "",
        refractive_index_snapshot=report.refractive_index,
        specific_gravity_snapshot=(
            "" if report.specific_gravity is None else str(report.specific_gravity)
        ),
        comments_snapshot=report.conclusion,
        instruments_snapshot=_instruments(report),
        report_number_snapshot=report.report_number,
        gemmologist=_person(report.identified_by),
        gemmologist_two=_person(report.verified_by),
        photo_snapshot=stone.photo or None,
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

    The row stays, and so does its number, so the certificate still downloads -
    watermarked REVOKED. That is the whole point: whoever is holding the paper
    copy has to be able to learn that it no longer stands.

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
