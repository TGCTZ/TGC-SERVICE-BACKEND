"""Bill creation and submission to GePG."""

import logging
from datetime import timedelta
from decimal import Decimal
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceError
from apps.core.services import generate_reference_number
from apps.gems.enums import BillStatus, StoneStatus
from apps.orders.services import transition_stone

from ..gateways.gepg import build_bill_response_ack, parse_bill_response, submit_bill
from ..models import Bill, BillItem

logger = logging.getLogger(__name__)


def _price_for(stone) -> Decimal:
    """The fixed identification fee for a stone's type.

    Raises:
        ServiceError: If the type has no price set. An unpriced type is a
            configuration gap, and billing zero would be worse than refusing.
    """
    price = stone.stone_type.price
    if price is None:
        raise ServiceError(f"No price set for stone type '{stone.stone_type}'.")
    return price


@transaction.atomic
def _create_local_bill(order, service_provider, user) -> Bill:
    """Create the bill and its snapshotted line items; mark stones billed."""
    if Bill.objects.filter(order=order).exists():
        raise ServiceError(f"Order {order.reference_number} already has a bill.")
    stones = list(order.stones.all())
    if not stones:
        raise ServiceError("Order has no stones to bill.")

    now = timezone.now()
    bill = Bill(
        order=order,
        bill_number=generate_reference_number(Bill, "bill_number", "BILL"),
        service_provider=service_provider,
        status=BillStatus.PENDING,
        issued_at=now,
        expiry_at=now + timedelta(days=settings.GEPG_BILL_EXPIRY_DAYS),
    )
    if user is not None:
        bill.created_by = user
    bill.save()

    total = Decimal("0")
    for stone in stones:
        amount = _price_for(stone)
        item = BillItem(
            bill=bill,
            stone=stone,
            description=stone.stone_type.name,
            unit_price=amount,
            # Weight is unknown at billing time; findings come after payment.
            weight=None,
            amount=amount,
            gfs_code=settings.GEPG_GFS_CODE,
            item_ref=f"B{bill.id}IT-{stone.id}",
        )
        if user is not None:
            item.created_by = user
        item.save()
        total += amount
        transition_stone(
            stone, StoneStatus.BILLED, user=user, note=f"Billed on {bill.bill_number}"
        )

    bill.total_amount = total
    bill.save(update_fields=["total_amount", "updated_at"])
    return bill


def generate_bill_for_order(order, *, service_provider=None, user=None) -> Bill:
    """Create a bill for an order and submit it to GePG for a control number.

    The local bill is committed first and the gateway call happens outside that
    transaction: a network failure must not roll back a bill the lab has already
    issued, and the control number can still arrive later on the async callback.
    """
    bill = _create_local_bill(order, service_provider, user)

    username = user.get_username() if user is not None else "System"
    result = submit_bill(bill, order.customer, username)

    bill.is_gepg_submitted = True
    bill.gepg_submitted_at = timezone.now()
    # Truncate to the columns' limits - gateway and connection errors are verbose.
    bill.status_code = (result["status_code"] or "")[:30]
    bill.status_desc = (result["status_desc"] or "")[:255]
    if result["success"] and result["control_number"] not in (None, "PENDING"):
        bill.control_number = result["control_number"]
    bill.save(
        update_fields=[
            "is_gepg_submitted",
            "gepg_submitted_at",
            "status_code",
            "status_desc",
            "control_number",
            "updated_at",
        ]
    )
    return bill


@transaction.atomic
def handle_bill_response_callback(xml_content: str) -> str:
    """Handle an async billSubRes callback: store the control number, return an ack."""
    try:
        data = parse_bill_response(xml_content)
    except (ValueError, ParseError, DefusedXmlException) as exc:
        logger.error("Invalid GePG bill response: %s", exc)
        return build_bill_response_ack("ERROR", "7102")

    bill = Bill.objects.filter(bill_number=data["bill_id"]).first()
    if bill is not None and data["control_number"]:
        bill.control_number = data["control_number"]
        bill.status_code = data["status_code"]
        bill.status_desc = data["status_desc"]
        bill.save(
            update_fields=["control_number", "status_code", "status_desc", "updated_at"]
        )
    return build_bill_response_ack(data["res_id"], "7101")
