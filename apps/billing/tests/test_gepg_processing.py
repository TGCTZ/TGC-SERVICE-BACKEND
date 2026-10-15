"""Tests for the PostgreSQL-backed GePG processor."""

from datetime import timedelta

import pytest
import requests

from django.core.management import call_command
from django.utils import timezone

from apps.billing.models import Bill, GePGCallback, GePGRequest
from apps.billing.processing import (
    _recover_stale_outbound_requests,
    process_gepg_callback,
)
from apps.orders.tests.factories import OrderFactory

pytestmark = pytest.mark.django_db


PAYMENT_ACK = (
    "<Gepg><pmtSpNtfReqAck><AckStsCode>7101</AckStsCode></pmtSpNtfReqAck></Gepg>"
)


def _callback(**kwargs):
    return GePGCallback.objects.create(
        kind=GePGCallback.Kind.PAYMENT,
        event_id="EVENT-1",
        payload="<Gepg><payment /></Gepg>",
        **kwargs,
    )


def test_management_command_processes_persisted_callback(monkeypatch):
    """The timer command processes durable inbox rows without a broker."""
    callback = _callback()
    monkeypatch.setattr(
        "apps.billing.services.payment.process_payment_notification",
        lambda _payload: PAYMENT_ACK,
    )

    call_command("process_gepg_queue")

    callback.refresh_from_db()
    assert callback.status == GePGCallback.Status.PROCESSED
    assert callback.attempts == 1
    assert callback.processed_at is not None


def test_callback_retry_is_scheduled_in_postgres(settings, monkeypatch):
    """Transient handler errors return to pending with the configured backoff."""
    settings.GEPG_RETRY_INITIAL_SECONDS = 60
    settings.GEPG_RETRY_MAX_SECONDS = 1800
    callback = _callback()

    def fail(_payload):
        raise TimeoutError("temporary database failure")

    monkeypatch.setattr(
        "apps.billing.services.payment.process_payment_notification", fail
    )
    before = timezone.now()

    assert process_gepg_callback(callback.pk)

    callback.refresh_from_db()
    assert callback.status == GePGCallback.Status.PENDING
    assert callback.attempts == 1
    assert before + timedelta(seconds=59) <= callback.next_attempt_at
    assert callback.next_attempt_at <= timezone.now() + timedelta(seconds=61)
    assert "temporary database failure" in callback.last_error


def test_callback_business_rejection_is_not_retried(monkeypatch):
    """A non-success GePG business result is staff-visible and terminal."""
    callback = _callback()
    monkeypatch.setattr(
        "apps.billing.services.payment.process_payment_notification",
        lambda _payload: (
            "<Gepg><pmtSpNtfReqAck><AckStsCode>7204</AckStsCode></pmtSpNtfReqAck></Gepg>"
        ),
    )

    assert process_gepg_callback(callback.pk)

    callback.refresh_from_db()
    assert callback.status == GePGCallback.Status.FAILED
    assert callback.next_attempt_at is None
    assert "7204" in callback.last_error
    assert not process_gepg_callback(callback.pk)


def test_stale_processing_callback_is_recovered_and_not_applied_twice(monkeypatch):
    """A stale claim is reclaimed once; a processed row is not re-applied."""
    callback = _callback(status=GePGCallback.Status.PROCESSING)
    GePGCallback.objects.filter(pk=callback.pk).update(
        updated_at=timezone.now() - timedelta(minutes=6)
    )
    calls = []

    def acknowledge(_payload):
        calls.append(True)
        return PAYMENT_ACK

    monkeypatch.setattr(
        "apps.billing.services.payment.process_payment_notification", acknowledge
    )

    assert process_gepg_callback(callback.pk)
    assert not process_gepg_callback(callback.pk)

    callback.refresh_from_db()
    assert callback.status == GePGCallback.Status.PROCESSED
    assert callback.attempts == 1
    assert calls == [True]


def test_recently_claimed_callback_cannot_be_claimed_again():
    """A second processor leaves a live PROCESSING claim to its current owner."""
    callback = _callback(status=GePGCallback.Status.PROCESSING)

    assert not process_gepg_callback(callback.pk)

    callback.refresh_from_db()
    assert callback.status == GePGCallback.Status.PROCESSING
    assert callback.attempts == 0


def test_stale_outbound_request_returns_to_retry():
    """An interrupted send is due again after stale request recovery."""
    request = GePGRequest.objects.create(
        operation=GePGRequest.Operation.BILL,
        req_id="OUTBOUND-STALE-1",
        endpoint="https://local.test/gepg",
        gepg_com="registered.com",
        gepg_code="SP",
        gepg_alg="",
        payload="<Gepg />",
        status=GePGRequest.Status.SENDING,
    )
    GePGRequest.objects.filter(pk=request.pk).update(
        updated_at=timezone.now() - timedelta(minutes=6)
    )

    assert _recover_stale_outbound_requests(timezone.now()) == 1

    request.refresh_from_db()
    assert request.status == GePGRequest.Status.RETRY
    assert request.next_attempt_at is not None
    assert "Recovered" in request.last_error


def test_command_retries_exact_persisted_outbound_request(monkeypatch):
    """The timer retries stored XML and headers, then persists backoff state."""
    payload = "<Gepg><billSubReq><ReqId>OUTBOUND-RETRY-1</ReqId></billSubReq></Gepg>"
    request = GePGRequest.objects.create(
        operation=GePGRequest.Operation.BILL,
        req_id="OUTBOUND-RETRY-1",
        endpoint="https://local.test/gepg",
        gepg_com="registered.com",
        gepg_code="SP-1",
        gepg_alg="RSA-SHA256",
        payload=payload,
        status=GePGRequest.Status.RETRY,
        attempts=1,
        first_attempt_at=timezone.now() - timedelta(minutes=2),
        next_attempt_at=timezone.now() - timedelta(seconds=1),
    )
    captured = {}

    def fail(url, **kwargs):
        captured.update(kwargs)
        raise requests.ConnectionError("temporary network failure")

    monkeypatch.setattr("apps.billing.gepg_transport.requests.post", fail)

    call_command("process_gepg_queue")

    request.refresh_from_db()
    assert request.status == GePGRequest.Status.RETRY
    assert request.attempts == 2
    assert request.next_attempt_at >= timezone.now() + timedelta(seconds=119)
    assert request.next_attempt_at <= timezone.now() + timedelta(seconds=121)
    assert "temporary network failure" in request.last_error
    assert captured["data"] == payload.encode("utf-8")
    assert captured["headers"] == {
        "Content-Type": "application/xml",
        "Gepg-Com": "registered.com",
        "Gepg-Code": "SP-1",
        "Gepg-Alg": "RSA-SHA256",
    }


def test_command_does_not_retry_gateway_business_rejection(monkeypatch):
    """A GePG application rejection is terminal even when its request was retried."""
    bill = Bill.objects.create(order=OrderFactory(), bill_number="GB-RETRY-REJECT")
    request = GePGRequest.objects.create(
        operation=GePGRequest.Operation.BILL,
        req_id="OUTBOUND-REJECT-1",
        endpoint="https://local.test/gepg",
        gepg_com="registered.com",
        gepg_code="SP-1",
        gepg_alg="",
        payload="<Gepg><billSubReq><ReqId>OUTBOUND-REJECT-1</ReqId></billSubReq></Gepg>",
        bill=bill,
        status=GePGRequest.Status.RETRY,
        attempts=1,
        first_attempt_at=timezone.now() - timedelta(minutes=2),
        next_attempt_at=timezone.now() - timedelta(seconds=1),
    )

    class Response:
        text = (
            "<Gepg><billSubReqAck><AckStsCode>7242</AckStsCode>"
            "<AckStsDesc>Invalid request</AckStsDesc></billSubReqAck></Gepg>"
        )

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr(
        "apps.billing.gepg_transport.requests.post", lambda *_args, **_kwargs: Response()
    )

    call_command("process_gepg_queue")

    request.refresh_from_db()
    bill.refresh_from_db()
    assert request.status == GePGRequest.Status.REJECTED
    assert request.status_code == "7242"
    assert request.next_attempt_at is None
    assert request.attempts == 2
    assert bill.status_code == "7242"
