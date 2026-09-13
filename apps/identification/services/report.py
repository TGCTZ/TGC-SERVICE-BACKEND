"""Identification report creation and finalization."""

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceError
from apps.core.services import generate_reference_number
from apps.gems.enums import BillStatus
from apps.orders.services import update_stone

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
        raise ServiceError("The bill must be paid before recording the findings.")


# Weight is a finding, but it lives on the Stone: the certificate snapshots the
# stone, and two places to record one number is one place to disagree. The
# findings form carries it and hands it straight on, inside this transaction.
#
# No permission check accompanies it, unlike the nested customer write on orders.
# That one creates a row of another model, which is a real route around
# ``orders.add_customer``; this writes one column of the stone the report is
# already about, and that column is a finding this endpoint exists to record.
_STONE_FIELDS = ("weight", "weight_unit")


def _pop_stone_fields(fields: dict) -> dict:
    """Split off the submitted fields that belong to the stone, not the report."""
    return {name: fields.pop(name) for name in _STONE_FIELDS if name in fields}


@transaction.atomic
def create_report(*, stone, user=None, **fields) -> IdentificationReport:
    """Create an identification report for a stone.

    The findings are recorded after payment, so the stone's status is
    deliberately left alone - the pipeline moves it, not the report.

    Args:
        stone: The stone being identified.
        user: The gemmologist, recorded as the identifier.
        **fields: Any report field - species, colour, refractive index and so
            on - plus ``weight``/``weight_unit``, which are applied to the stone.
    """
    _assert_payment_settled(stone)
    stone_fields = _pop_stone_fields(fields)

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

    if stone_fields:
        update_stone(stone, user=user, **stone_fields)
    return report


@transaction.atomic
def update_report(
    report: IdentificationReport, *, user=None, **fields
) -> IdentificationReport:
    """Update a report's findings.

    Args:
        report: The report to update.
        user: The acting gemmologist.
        **fields: Any report field, plus ``weight``/``weight_unit``, which are
            applied to the stone.

    Raises:
        ServiceError: If the report is finalized. This is the strongest guard in
            the system: a certificate quotes the report, so a finalized report
            that could still change would make an issued certificate a claim
            about nothing in particular.
    """
    if report.is_finalized:
        raise ServiceError("A finalized report cannot be edited.")
    _assert_payment_settled(report.stone)
    stone_fields = _pop_stone_fields(fields)

    for name, value in fields.items():
        setattr(report, name, value)
    if user is not None:
        report.updated_by = user
    report.save()

    if stone_fields:
        update_stone(report.stone, user=user, **stone_fields)
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
