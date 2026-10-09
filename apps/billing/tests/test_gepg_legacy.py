"""Compatibility checks for the old GePG contract, using mocked HTTP only."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from django.urls import resolve

from apps.billing.gateways.gepg import send_control_number_sms
from apps.billing.gateways.signing import sign_payload
from apps.billing.models import (
    Bill,
)
from apps.billing.services import (
    cancel_bill,
    handle_cancel_response,
    handle_reconciliation_response,
    request_reconciliation,
)
from apps.orders.tests.factories import OrderFactory

pytestmark = pytest.mark.django_db


class FakeResponse:
    """Minimal HTTP response fake for gateway tests."""

    status_code = 200

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        """Match requests.Response.raise_for_status for successful responses."""
        return None


def _bill(**kwargs):
    return Bill.objects.create(
        order=OrderFactory(), bill_number=f"GB-{uuid4().hex[:16]}", **kwargs
    )


def test_legacy_callback_paths_resolve_to_new_handlers():
    """Every old registered URL resolves to a webhook in the new deployment."""
    assert resolve("/billing/api/payments/notification/").url_name is None
    assert resolve("/billing/api/bill/response/").url_name is None
    assert (
        resolve("/billing/api/bill/cancel-response/").func.view_class.__name__
        == "BillCancelResponseView"
    )
    assert (
        resolve("/billing/reconciliation/response/").func.view_class.__name__
        == "ReconciliationResponseView"
    )


def test_new_private_pfx_produces_a_real_signature(settings):
    """The copied identity signs a payload without leaving the placeholder."""
    settings.GEPG_USE_DIGITAL_SIGNATURE = True
    signed = sign_payload(
        "<Gepg><billSubReq/><signature>SignatureGoesHere</signature></Gepg>"
    )
    assert "SignatureGoesHere" not in signed
    assert "<signature>" in signed


def test_cancellation_uses_legacy_headers_xml_and_records_result(
    settings, monkeypatch, admin_user
):
    """Cancellation preserves the old request headers and persists its result."""
    settings.GEPG_SIMULATE = False
    settings.GEPG_USE_DIGITAL_SIGNATURE = False
    settings.GEPG_SP_GRP_CODE, settings.GEPG_SYS_CODE, settings.GEPG_SP_CODE = (
        "GRP",
        "SYS",
        "SP",
    )
    bill = _bill()
    captured = {}

    def post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(
            "<Gepg><billCanclRes><CanclStsCode>7283</CanclStsCode><CanclStsDesc>Cancelled</CanclStsDesc></billCanclRes></Gepg>"
        )

    monkeypatch.setattr("apps.billing.services.gepg_operations.requests.post", post)
    record = cancel_bill(bill, reason="retire & replace", user=admin_user)

    assert captured["headers"] == {
        "Content-Type": "application/xml",
        "Gepg-Com": "changebill.sp.in",
        "Gepg-Code": "SP",
    }
    assert "<CanclReasn>retire &amp; replace</CanclReasn>" in captured["data"].decode()
    bill.refresh_from_db()
    assert record.status_code == "7283"
    assert bill.status == "cancelled"


def test_async_cancellation_callback_updates_bill_and_acknowledges(settings):
    """An asynchronous 7283 callback updates the bill and receives XML ack."""
    settings.GEPG_USE_DIGITAL_SIGNATURE = False
    bill = _bill()
    ack = handle_cancel_response(
        f"<Gepg><billCanclRes><ReqId>R1</ReqId><GrpBillId>{bill.bill_number}</GrpBillId><CanclStsCode>7283</CanclStsCode><CanclStsDesc>done</CanclStsDesc></billCanclRes></Gepg>"
    )
    bill.refresh_from_db()
    assert bill.status == "cancelled"
    assert "7283" in ack


def test_unknown_bill_response_callback_returns_7102(settings):
    """Do not claim a callback was applied when its bill is not in this DB."""
    settings.GEPG_USE_DIGITAL_SIGNATURE = False
    from apps.billing.services import handle_bill_response_callback

    ack = handle_bill_response_callback(
        "<Gepg><billSubRes><BillHdr><ResId>R1</ResId></BillHdr>"
        "<BillDtls><BillDtl><BillId>OLD-BILL</BillId>"
        "<BillCntrNum>991234567890</BillCntrNum></BillDtl></BillDtls></billSubRes></Gepg>"
    )

    assert "7102" in ack


def test_reconciliation_request_and_callback_are_persisted(
    settings, monkeypatch, admin_user
):
    """Reconciliation preserves request format and stores callback transactions."""
    settings.GEPG_USE_DIGITAL_SIGNATURE = False
    settings.GEPG_SP_GRP_CODE, settings.GEPG_SYS_CODE, settings.GEPG_SP_CODE = (
        "GRP",
        "SYS",
        "SP",
    )
    settings.GEPG_RECONCILIATION_URL = "https://local.test/recon"
    captured = {}

    def post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(
            "<Gepg><sucSpPmtReqAck><AckId>A1</AckId><ReqId>R1</ReqId><AckStsCode>7101</AckStsCode><AckStsDesc>Accepted</AckStsDesc></sucSpPmtReqAck></Gepg>"
        )

    monkeypatch.setattr("apps.billing.services.gepg_operations.requests.post", post)
    record = request_reconciliation(date(2026, 10, 8), user=admin_user)
    assert "<sucSpPmtReq>" in captured["data"].decode()
    assert captured["headers"]["Gepg-Com"] == "default.sp.in"
    assert record.status == "acknowledged"

    body = f"""<Gepg><sucSpPmtRes><BatchHdr><ResId>RES-1</ResId>
<ReqId>{record.req_id}</ReqId><PayStsCode>7101</PayStsCode><PayStsDesc>OK</PayStsDesc>
</BatchHdr><PmtDtls><PmtTrxDtl><TrxId>TX-1</TrxId><BillId>BILL-1</BillId>
<PaidAmt>10.00</PaidAmt><BillAmt>10.00</BillAmt></PmtTrxDtl></PmtDtls></sucSpPmtRes></Gepg>"""
    ack = handle_reconciliation_response(body)
    record.refresh_from_db()
    assert record.status == "completed"
    assert record.transactions.get().trx_id == "TX-1"
    assert "sucSpPmtResAck" in ack


def test_control_number_sms_is_sent_once(settings, monkeypatch):
    """The successful provider send is idempotent for a bill control number."""
    settings.GEPG_SIMULATE = False
    settings.BEEM_AFRICA_API_KEY = "test-key"
    settings.BEEM_AFRICA_SECRET_KEY = "test-secret"
    bill = _bill(control_number="991234567890", total_amount=Decimal("1000.00"))
    calls = []
    monkeypatch.setattr(
        "apps.billing.gateways.gepg.requests.post",
        lambda *a, **k: calls.append(k) or FakeResponse("{}"),
    )

    assert send_control_number_sms(bill)
    assert not send_control_number_sms(bill)
    bill.refresh_from_db()
    assert bill.control_number_sms_sent_at is not None
    assert len(calls) == 1


def test_cancel_action_requires_the_billing_permission(admin_user, auth_client):
    """Only a user with the billing permission can initiate cancellation."""
    bill = _bill()
    client = auth_client(admin_user)
    admin_user.groups.clear()
    admin_user.user_permissions.clear()
    admin_user.is_superuser = False
    admin_user.save()

    response = client.post(f"/api/v1/bills/{bill.pk}/cancel/", {"reason": "duplicate"})

    assert response.status_code == 403
