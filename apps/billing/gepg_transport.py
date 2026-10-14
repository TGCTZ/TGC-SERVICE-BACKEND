"""Persistent GePG HTTP transport with bounded retry scheduling."""

from datetime import timedelta

import requests
from defusedxml.ElementTree import fromstring

from django.conf import settings
from django.utils import timezone

from .models import GePGRequest


def send_gepg_request(
    operation: str,
    endpoint: str,
    payload: str,
    *,
    bill=None,
    cancellation=None,
    reconciliation=None,
) -> tuple[GePGRequest, str | None]:
    """Persist and send the exact signed payload once; retry failures in Celery."""
    try:
        root = fromstring(payload)
        req_id = root.findtext(".//ReqId", "")
    except Exception as exc:
        raise ValueError("GePG request XML must include a valid ReqId.") from exc
    if not req_id:
        raise ValueError("GePG request XML must include a ReqId.")
    request_record = GePGRequest.objects.create(
        operation=operation,
        req_id=req_id,
        endpoint=endpoint,
        gepg_com=settings.GEPG_COM,
        gepg_code=settings.GEPG_SP_CODE,
        gepg_alg=settings.GEPG_ALG,
        payload=payload,
        bill=bill,
        cancellation=cancellation,
        reconciliation=reconciliation,
    )
    return request_record, _attempt(request_record)


def retry_gepg_request(request_record: GePGRequest) -> str | None:
    """Retry a due request using its original ID, headers, and signed bytes."""
    return _attempt(request_record)


def _attempt(request_record: GePGRequest) -> str | None:
    now = timezone.now()
    request_record.attempts += 1
    if request_record.first_attempt_at is None:
        request_record.first_attempt_at = now
    request_record.status = GePGRequest.Status.SENDING
    request_record.next_attempt_at = None
    request_record.save(
        update_fields=[
            "attempts",
            "first_attempt_at",
            "status",
            "next_attempt_at",
            "updated_at",
        ]
    )
    try:
        headers = {
            "Content-Type": "application/xml",
            "Gepg-Com": request_record.gepg_com,
            "Gepg-Code": request_record.gepg_code,
        }
        if request_record.gepg_alg:
            headers["Gepg-Alg"] = request_record.gepg_alg

        response = requests.post(
            request_record.endpoint,
            data=request_record.payload.encode("utf-8"),
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        request_record.last_error = str(exc)[:2000]
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        retryable = status_code is None or status_code >= 500
        age = now - request_record.first_attempt_at
        if not retryable:
            request_record.status = GePGRequest.Status.REJECTED
        elif age >= timedelta(seconds=settings.GEPG_RETRY_MAX_AGE_SECONDS):
            request_record.status = GePGRequest.Status.EXHAUSTED
        else:
            request_record.status = GePGRequest.Status.RETRY
            delay = min(
                settings.GEPG_RETRY_INITIAL_SECONDS
                * 2 ** min(request_record.attempts - 1, 10),
                settings.GEPG_RETRY_MAX_SECONDS,
            )
            request_record.next_attempt_at = now + timedelta(seconds=delay)
        request_record.save(
            update_fields=["status", "last_error", "next_attempt_at", "updated_at"]
        )
        if request_record.status == GePGRequest.Status.EXHAUSTED:
            mark_request_exhausted(request_record)
        return None

    request_record.response_xml = response.text
    request_record.last_error = ""
    request_record.save(update_fields=["response_xml", "last_error", "updated_at"])
    return response.text


def finish_gepg_request(
    request_record: GePGRequest,
    *,
    accepted: bool,
    status_code: str = "",
    status_desc: str = "",
    response_xml: str = "",
) -> None:
    """Record the gateway's application-level outcome without retrying rejects."""
    request_record.status = (
        GePGRequest.Status.ACCEPTED if accepted else GePGRequest.Status.REJECTED
    )
    request_record.status_code = status_code[:30]
    request_record.status_desc = status_desc[:255]
    if response_xml:
        request_record.response_xml = response_xml
    request_record.next_attempt_at = None
    request_record.save(
        update_fields=[
            "status",
            "status_code",
            "status_desc",
            "response_xml",
            "next_attempt_at",
            "updated_at",
        ]
    )


def mark_request_exhausted(request_record: GePGRequest) -> None:
    """Expose exhausted delivery state on its owning workflow record."""
    message = "GePG transport retries exhausted after 24 hours."
    if request_record.bill_id:
        request_record.bill.status_code = "CONNECTION_ERROR"
        request_record.bill.status_desc = message
        request_record.bill.save(
            update_fields=["status_code", "status_desc", "updated_at"]
        )
    if request_record.cancellation_id:
        request_record.cancellation.status_code = "CONNECTION_ERROR"
        request_record.cancellation.status_desc = message
        request_record.cancellation.save(
            update_fields=["status_code", "status_desc", "updated_at"]
        )
    if request_record.reconciliation_id:
        request_record.reconciliation.status = "failed"
        request_record.reconciliation.error_message = message
        request_record.reconciliation.save(
            update_fields=["status", "error_message", "updated_at"]
        )
