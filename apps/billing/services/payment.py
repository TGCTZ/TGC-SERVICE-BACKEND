"""Payment notifications received from GePG."""

import logging
from decimal import Decimal
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException

from django.db import transaction

from apps.core.exceptions import ServiceError
from apps.gems.enums import BillStatus, StoneStatus
from apps.orders.services import transition_stone

from ..gateways.gepg import build_payment_ack, parse_payment_notification
from ..models import Bill, Payment

logger = logging.getLogger(__name__)


def process_payment_notification(xml_content: str) -> str:
    """Handle a GePG payment notification callback; return a signed ack XML.

    Every exit path returns well-formed XML, because the gateway is not a
    browser: an unparseable body or a failure mid-way still has to answer with a
    ``7102`` ack rather than an error page, or GePG will keep redelivering.
    """
    try:
        header, transactions = parse_payment_notification(xml_content)
    except (ValueError, ParseError, DefusedXmlException) as exc:
        logger.error("Invalid GePG payment notification: %s", exc)
        return build_payment_ack("ERROR", "7102")

    req_id = header["req_id"]
    try:
        for txn in transactions:
            _apply_payment(header, txn, xml_content)
    except Exception:
        logger.exception("Failed to process GePG payment notification")
        return build_payment_ack(req_id or "ERROR", "7102")
    return build_payment_ack(req_id, "7101")


@transaction.atomic
def _apply_payment(header: dict, txn: dict, raw: str) -> None:
    """Record one payment transaction and settle its bill if fully paid.

    Idempotent on ``trx_id``: GePG redelivers a notification until it is
    acknowledged, so a repeat updates the stored row and returns without
    recomputing the settlement - otherwise a redelivery would re-transition
    every stone and write a second history entry each time.
    """
    bill = (
        Bill.objects.filter(bill_number=txn["gepg_bill_id"]).first()
        or Bill.objects.filter(control_number=txn["bill_ctr_num"]).first()
    )
    if bill is None:
        raise ServiceError(f"Bill '{txn['gepg_bill_id']}' not found.")

    defaults = {**header, **txn, "bill": bill, "is_processed": True, "raw_request": raw}
    defaults.pop("trx_id", None)
    payment, created = Payment.objects.get_or_create(
        trx_id=txn["trx_id"], defaults=defaults
    )
    if not created:
        for field, value in defaults.items():
            setattr(payment, field, value)
        payment.save()
        return

    paid = sum((p.paid_amount or Decimal("0") for p in bill.payments.all()), Decimal("0"))
    if paid >= bill.total_amount:
        bill.status = BillStatus.PAID
        # The gateway is the actor here, so there is no user to attribute.
        for stone in bill.order.stones.all():
            transition_stone(stone, StoneStatus.PAID, note="Bill settled via GePG")
    else:
        bill.status = BillStatus.PARTIALLY_PAID
    bill.save(update_fields=["status", "updated_at"])
