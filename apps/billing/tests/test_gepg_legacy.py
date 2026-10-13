"""Compatibility checks for the old GePG contract, using mocked HTTP only."""

import base64
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from django.urls import resolve

from apps.billing.gateways.gepg import _parse_bill_response, send_control_number_sms
from apps.billing.gateways.signing import (
    _load_gateway_public_key,
    _load_private_key,
    sign_if_enabled,
    sign_payload,
    verify_payload,
)
from apps.billing.gepg_transport import retry_gepg_request, send_gepg_request
from apps.billing.models import (
    Bill,
    GePGCallback,
    GePGRequest,
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


def test_new_private_pfx_produces_a_real_signature(settings, tmp_path):
    """A test-only PKCS#12 identity produces a verifiable payload signature."""
    password = "ci-test-certificate-password"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "GePG CI signing test")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(private_key, hashes.SHA256())
    )
    pfx_path = tmp_path / "ci-private.pfx"
    pfx_path.write_bytes(
        pkcs12.serialize_key_and_certificates(
            name=b"gepg-ci-test",
            key=private_key,
            cert=certificate,
            cas=None,
            encryption_algorithm=serialization.BestAvailableEncryption(
                password.encode("utf-8")
            ),
        )
    )

    settings.GEPG_PRIVATE_KEY_PATH = pfx_path
    settings.GEPG_CERTIFICATE_PASSWORD = password
    settings.GEPG_USE_DIGITAL_SIGNATURE = True
    _load_private_key.cache_clear()
    try:
        signed = sign_payload(
            "<Gepg><billSubReq/><signature>SignatureGoesHere</signature></Gepg>"
        )
        signature = signed.partition("<signature>")[2].partition("</signature>")[0]
        assert signature != "SignatureGoesHere"
        private_key.public_key().verify(
            base64.b64decode(signature),
            b"<billSubReq/>",
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    finally:
        _load_private_key.cache_clear()


def test_inbound_signature_verifies_and_rejects_tampering(settings, tmp_path):
    """Verify GePG signatures with the registered certificate and reject edits."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "GePG callback test")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(private_key, hashes.SHA256())
    )
    cert_path = tmp_path / "gepg-public.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    settings.GEPG_PUBLIC_CERT_PATH = cert_path
    _load_gateway_public_key.cache_clear()
    body = "<Gepg><sample>accepted</sample></Gepg>"
    signature = private_key.sign(
        b"<sample>accepted</sample>", padding.PKCS1v15(), hashes.SHA256()
    )
    signed = body.replace(
        "</Gepg>",
        f"<signature>{base64.b64encode(signature).decode()}</signature></Gepg>",
    )
    try:
        assert verify_payload(signed)
        assert not verify_payload(signed.replace("accepted", "tampered"))
    finally:
        _load_gateway_public_key.cache_clear()


def test_unsigned_payload_fails_closed_outside_development(settings):
    """Production-mode signing cannot silently send an unsigned request."""
    settings.DEBUG = False
    settings.GEPG_SIMULATE = False
    settings.GEPG_USE_DIGITAL_SIGNATURE = False

    with pytest.raises(RuntimeError, match="required outside development"):
        sign_if_enabled("<Gepg><request /></Gepg>")


@pytest.mark.parametrize(
    ("status_code", "control_number", "accepted"),
    [
        ("7101", "991234567890", True),
        ("7101", "0", False),
        ("7241", "991234567890", False),
    ],
)
def test_bill_submission_requires_success_code_and_real_control_number(
    status_code, control_number, accepted
):
    """A business rejection or zero sentinel can never become a control number."""
    response = (
        "<Gepg><billSubRes><BillHdr><ResStsCode>7101</ResStsCode></BillHdr>"
        f"<BillDtls><BillDtl><BillCntrNum>{control_number}</BillCntrNum>"
        f"<BillStsCode>{status_code}</BillStsCode></BillDtl></BillDtls>"
        "</billSubRes></Gepg>"
    )
    assert _parse_bill_response(response)["success"] is accepted


def test_callback_is_persisted_before_success_ack(settings, client, monkeypatch):
    """A callback response follows durable inbox storage and successful enqueue."""
    settings.DEBUG = True
    settings.GEPG_USE_DIGITAL_SIGNATURE = False
    queued = []
    monkeypatch.setattr(
        "apps.billing.webhooks.process_gepg_callback.delay",
        lambda callback_id: queued.append(callback_id),
    )
    payload = (
        "<Gepg><billSubRes><BillHdr><ResId>RES-DURABLE-1</ResId></BillHdr>"
        "<BillDtls><BillDtl><BillId>BILL-1</BillId></BillDtl></BillDtls>"
        "</billSubRes></Gepg>"
    )

    response = client.post(
        "/billing/api/bill/response/", data=payload, content_type="application/xml"
    )

    callback = GePGCallback.objects.get(kind=GePGCallback.Kind.BILL)
    assert response.status_code == 200
    assert "7101" in response.content.decode()
    assert callback.payload == payload
    assert queued == [callback.pk]


def test_callback_returns_retryable_failure_when_broker_unavailable(
    settings, client, monkeypatch
):
    """A broker outage leaves the verified event durable and asks GePG to retry."""
    settings.DEBUG = True
    settings.GEPG_USE_DIGITAL_SIGNATURE = False

    def unavailable(_callback_id):
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr("apps.billing.webhooks.process_gepg_callback.delay", unavailable)
    payload = (
        "<Gepg><billSubRes><BillHdr><ResId>RES-DURABLE-2</ResId></BillHdr>"
        "<BillDtls><BillDtl><BillId>BILL-1</BillId></BillDtl></BillDtls>"
        "</billSubRes></Gepg>"
    )

    response = client.post(
        "/billing/api/bill/response/", data=payload, content_type="application/xml"
    )

    assert response.status_code == 503
    assert GePGCallback.objects.get(event_id="RES-DURABLE-2").status == "pending"


def test_outbound_retry_reuses_persisted_payload_and_headers(settings, monkeypatch):
    """A retry sends the exact stored XML and registered communication headers."""
    settings.GEPG_COM = "registered.com"
    settings.GEPG_ALG = "RSA-SHA256"
    settings.GEPG_SP_CODE = "SP"
    settings.GEPG_RETRY_INITIAL_SECONDS = 60
    settings.GEPG_RETRY_MAX_SECONDS = 1800
    payload = "<Gepg><billSubReq><ReqId>RETRY-1</ReqId></billSubReq></Gepg>"
    captured = {}

    class SuccessResponse(FakeResponse):
        status_code = 200

    def fail_once(url, **kwargs):
        captured.update(kwargs)
        raise __import__("requests").ConnectionError("network timeout")

    monkeypatch.setattr("apps.billing.gepg_transport.requests.post", fail_once)
    outbound, response = send_gepg_request(
        GePGRequest.Operation.BILL,
        "https://local.test/bill",
        payload,
    )
    outbound.refresh_from_db()
    assert response is None
    assert outbound.status == GePGRequest.Status.RETRY
    assert outbound.payload == payload

    def succeed(url, **kwargs):
        captured.update(kwargs)
        return SuccessResponse("<Gepg><billSubReqAck /></Gepg>")

    monkeypatch.setattr("apps.billing.gepg_transport.requests.post", succeed)
    response = retry_gepg_request(outbound)

    assert response == "<Gepg><billSubReqAck /></Gepg>"
    assert captured["data"] == payload.encode()
    assert captured["headers"]["Gepg-Com"] == "registered.com"
    assert captured["headers"]["Gepg-Alg"] == "RSA-SHA256"


def test_cancellation_uses_legacy_headers_xml_and_records_result(
    settings, monkeypatch, admin_user
):
    """Cancellation preserves the old request headers and persists its result."""
    settings.GEPG_SIMULATE = False
    settings.DEBUG = True
    settings.GEPG_USE_DIGITAL_SIGNATURE = False
    settings.GEPG_SP_GRP_CODE, settings.GEPG_SYS_CODE, settings.GEPG_SP_CODE = (
        "GRP",
        "SYS",
        "SP",
    )
    settings.GEPG_COM, settings.GEPG_ALG = "registered.com", "RSA-SHA256"
    bill = _bill()
    captured = {}

    def post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(
            "<Gepg><billCanclRes><CanclStsCode>7283</CanclStsCode><CanclStsDesc>Cancelled</CanclStsDesc></billCanclRes></Gepg>"
        )

    monkeypatch.setattr("apps.billing.gepg_transport.requests.post", post)
    record = cancel_bill(bill, reason="retire & replace", user=admin_user)

    assert captured["headers"] == {
        "Content-Type": "application/xml",
        "Gepg-Com": "registered.com",
        "Gepg-Code": "SP",
        "Gepg-Alg": "RSA-SHA256",
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


def test_unknown_bill_response_callback_returns_7204(settings):
    """Do not claim a callback was applied when its bill is not in this DB."""
    settings.GEPG_USE_DIGITAL_SIGNATURE = False
    from apps.billing.services import handle_bill_response_callback

    ack = handle_bill_response_callback(
        "<Gepg><billSubRes><BillHdr><ResId>R1</ResId></BillHdr>"
        "<BillDtls><BillDtl><BillId>OLD-BILL</BillId>"
        "<BillCntrNum>991234567890</BillCntrNum></BillDtl></BillDtls></billSubRes></Gepg>"
    )

    assert "7204" in ack
    assert "<AckId>" in ack


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
    settings.GEPG_COM, settings.GEPG_ALG = "registered.com", "RSA-SHA256"
    settings.GEPG_RECONCILIATION_URL = "https://local.test/recon"
    captured = {}

    def post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(
            "<Gepg><sucSpPmtReqAck><AckId>A1</AckId><ReqId>R1</ReqId><AckStsCode>7101</AckStsCode><AckStsDesc>Accepted</AckStsDesc></sucSpPmtReqAck></Gepg>"
        )

    monkeypatch.setattr("apps.billing.gepg_transport.requests.post", post)
    record = request_reconciliation(date(2026, 10, 8), user=admin_user)
    assert "<sucSpPmtReq>" in captured["data"].decode()
    assert captured["headers"]["Gepg-Com"] == "registered.com"
    assert captured["headers"]["Gepg-Alg"] == "RSA-SHA256"
    assert record.status == "acknowledged"

    bill = _bill(total_amount=Decimal("10.00"))
    body = f"""<Gepg><sucSpPmtRes><BatchHdr><ResId>RES-1</ResId>
<ReqId>{record.req_id}</ReqId><PayStsCode>7101</PayStsCode><PayStsDesc>OK</PayStsDesc>
</BatchHdr><PmtDtls><PmtTrxDtl><SpCode>SP</SpCode><BillId>{bill.bill_number}</BillId>
<BillCtrNum>991234567890</BillCtrNum><PspCode>PSP</PspCode><PspName>Bank</PspName>
<TrxId>TX-1</TrxId><PayRefId>REF-1</PayRefId><BillAmt>10.00</BillAmt>
<PaidAmt>10.00</PaidAmt><BillPayOpt>3</BillPayOpt><Ccy>TZS</Ccy>
<CollAccNum>ACC-1</CollAccNum><TrxDtTm>2026-10-08T10:00:00</TrxDtTm>
<UsdPayChnl>Bank</UsdPayChnl></PmtTrxDtl></PmtDtls></sucSpPmtRes></Gepg>"""
    ack = handle_reconciliation_response(body)
    record.refresh_from_db()
    assert record.status == "completed"
    assert record.transactions.get().trx_id == "TX-1"
    assert bill.payments.get().trx_id == "TX-1"
    bill.refresh_from_db()
    assert bill.status == "paid"
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
