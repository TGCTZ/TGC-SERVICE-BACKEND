"""Identification report creation and finalization."""

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceError
from apps.core.services import generate_reference_number
from apps.gems.enums import BillStatus

from ..models import IdentificationReport


def _assert_payment_settled(stone) -> None:
    """Refuse findings until the stone's order is paid for.

    The gate lives here rather than in the view because it is a business rule,
    and an API exposes more than one route to a report. Reached by attribute
    traversal (``stone.order.bill``) rather than by importing ``apps.billing``,
    which sits at the same layer and must not be imported from here.

    Raises:
        ServiceError: If the order has no bill, or it is not settled.
    """
    bill = getattr(stone.order, "bill", None)
    if bill is None or bill.status != BillStatus.PAID:
        raise ServiceError("The bill must be paid before recording findings.")


@transaction.atomic
def create_report(*, stone, user=None, **fields) -> IdentificationReport:
    """Create an identification report for a stone.

    Findings are recorded after payment, so the stone's status is deliberately
    left alone - the pipeline moves it, not the report.

    Args:
        stone: The stone the findings belong to.
        user: The gemmologist, recorded as the identifier.
        **fields: Any report field - species, colour, refractive index and so on.
    """
    _assert_payment_settled(stone)

    report = IdentificationReport(
        stone=stone,
        report_number=generate_reference_number(
            IdentificationReport, "report_number", "RPT"
        ),
        **fields,
    )
    if user is not None:
        report.created_by = user
        report.identified_by = user
    report.save()
    return report


@transaction.atomic
def update_report(
    report: IdentificationReport, *, user=None, **fields
) -> IdentificationReport:
    """Update a report's findings.

    Raises:
        ServiceError: If the report is finalized. This is the strongest guard in
            the system: a certificate quotes the report, so a finalized report
            that could still change would make an issued certificate a claim
            about nothing in particular.
    """
    if report.is_finalized:
        raise ServiceError("A finalized report cannot be edited.")
    _assert_payment_settled(report.stone)
    for name, value in fields.items():
        setattr(report, name, value)
    if user is not None:
        report.updated_by = user
    report.save()
    return report


def finalize_report(report: IdentificationReport, *, user=None) -> IdentificationReport:
    """Lock a report against further edits.

    One-way: there is no un-finalize service. A mistake after this point is
    corrected by revoking the certificate, not by quietly rewriting the findings.

    Raises:
        ServiceError: If the report is already finalized.
    """
    if report.is_finalized:
        raise ServiceError("Report is already finalized.")
    report.is_finalized = True
    report.identified_at = timezone.now()
    if user is not None:
        report.identified_by = user
        report.updated_by = user
    report.save(
        update_fields=[
            "is_finalized",
            "identified_at",
            "identified_by",
            "updated_at",
            "updated_by",
        ]
    )
    return report
