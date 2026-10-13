"""Background processing and recovery for durable GePG callback events."""

import logging
from datetime import timedelta

from celery import shared_task
from defusedxml.ElementTree import fromstring

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from .gepg_transport import (
    finish_gepg_request,
    mark_request_exhausted,
)
from .gepg_transport import (
    retry_gepg_request as retry_request,
)
from .models import GePGCallback, GePGRequest

logger = logging.getLogger(__name__)


class GePGCallbackRejectedError(Exception):
    """A callback was validly received but its business data was rejected."""


@shared_task(bind=True, name="apps.billing.tasks.process_gepg_callback")
def process_gepg_callback(self, callback_id: int) -> None:
    """Process a stored callback; retry transient errors for up to 24 hours."""
    with transaction.atomic():
        callback = GePGCallback.objects.select_for_update().get(pk=callback_id)
        if callback.status == GePGCallback.Status.PROCESSED:
            return
        if (
            callback.status == GePGCallback.Status.PROCESSING
            and callback.updated_at > timezone.now() - timedelta(minutes=5)
        ):
            return
        callback.status = GePGCallback.Status.PROCESSING
        callback.attempts += 1
        callback.next_attempt_at = None
        callback.last_error = ""
        callback.save(
            update_fields=[
                "status",
                "attempts",
                "next_attempt_at",
                "last_error",
                "updated_at",
            ]
        )

    try:
        if callback.kind == GePGCallback.Kind.PAYMENT:
            from .services.payment import process_payment_notification

            acknowledgement = process_payment_notification(callback.payload)
            root = fromstring(acknowledgement)
            code = root.findtext(".//AckStsCode", "")
            if code != "7101":
                raise GePGCallbackRejectedError(
                    f"Payment callback returned GePG code {code}."
                )
        elif callback.kind == GePGCallback.Kind.BILL:
            from .services.bill import handle_bill_response_callback

            root = fromstring(handle_bill_response_callback(callback.payload))
            code = root.findtext(".//AckStsCode", "")
            if code != "7101":
                raise GePGCallbackRejectedError(
                    f"Bill callback returned GePG code {code}."
                )
        elif callback.kind == GePGCallback.Kind.RECONCILIATION:
            from .services.gepg_operations import handle_reconciliation_response

            root = fromstring(handle_reconciliation_response(callback.payload))
            code = root.findtext(".//AckStsCode", "")
            if code != "7101":
                raise GePGCallbackRejectedError(
                    f"Reconciliation callback returned GePG code {code}."
                )
        else:
            raise ValueError(f"Unsupported callback type: {callback.kind}")
    except GePGCallbackRejectedError as exc:
        callback.refresh_from_db()
        callback.status = GePGCallback.Status.FAILED
        callback.next_attempt_at = None
        callback.last_error = str(exc)[:2000]
        callback.save(
            update_fields=["status", "next_attempt_at", "last_error", "updated_at"]
        )
        logger.error("GePG callback %s was rejected: %s", callback.pk, exc)
        return
    except Exception as exc:
        callback.refresh_from_db()
        callback.last_error = str(exc)[:2000]
        elapsed = timezone.now() - callback.created_at
        if elapsed >= timedelta(seconds=settings.GEPG_RETRY_MAX_AGE_SECONDS):
            callback.status = GePGCallback.Status.FAILED
            callback.next_attempt_at = None
            callback.save(
                update_fields=["status", "next_attempt_at", "last_error", "updated_at"]
            )
            logger.error("GePG callback %s exhausted retries: %s", callback.pk, exc)
            return
        callback.status = GePGCallback.Status.PENDING
        countdown = min(60 * 2 ** min(callback.attempts - 1, 10), 1800)
        callback.next_attempt_at = timezone.now() + timedelta(seconds=countdown)
        callback.save(
            update_fields=["status", "next_attempt_at", "last_error", "updated_at"]
        )
        raise self.retry(exc=exc, countdown=countdown, max_retries=None) from exc

    with transaction.atomic():
        callback = GePGCallback.objects.select_for_update().get(pk=callback_id)
        callback.status = GePGCallback.Status.PROCESSED
        callback.processed_at = timezone.now()
        callback.next_attempt_at = None
        callback.last_error = ""
        callback.save(
            update_fields=[
                "status",
                "processed_at",
                "next_attempt_at",
                "last_error",
                "updated_at",
            ]
        )


@shared_task(name="apps.billing.tasks.recover_pending_gepg_messages")
def recover_pending_gepg_messages() -> int:
    """Requeue pending callbacks and due outbound requests after interruptions."""
    stale_sending = GePGRequest.objects.filter(
        status=GePGRequest.Status.SENDING,
        updated_at__lt=timezone.now() - timedelta(minutes=5),
    )
    stale_sending.update(
        status=GePGRequest.Status.RETRY,
        next_attempt_at=timezone.now(),
        last_error="Recovered an outbound request interrupted while sending.",
    )
    callback_ids = list(
        GePGCallback.objects.filter(
            (
                models.Q(status=GePGCallback.Status.PENDING)
                & (
                    models.Q(next_attempt_at__isnull=True)
                    | models.Q(next_attempt_at__lte=timezone.now())
                )
            )
            | models.Q(
                status=GePGCallback.Status.PROCESSING,
                updated_at__lt=timezone.now() - timedelta(minutes=5),
            )
        )
        .order_by("created_at")
        .values_list("pk", flat=True)[:500]
    )
    for callback_id in callback_ids:
        process_gepg_callback.delay(callback_id)
    request_ids = list(
        GePGRequest.objects.filter(
            status=GePGRequest.Status.RETRY,
            next_attempt_at__lte=timezone.now(),
        )
        .order_by("next_attempt_at")
        .values_list("pk", flat=True)[:500]
    )
    for request_id in request_ids:
        retry_gepg_outbound_request.delay(request_id)
    return len(callback_ids) + len(request_ids)


@shared_task(name="apps.billing.tasks.retry_gepg_outbound_request")
def retry_gepg_outbound_request(request_id: int) -> None:
    """Retry one due request and apply a valid response to its domain record."""
    outbound = GePGRequest.objects.select_related(
        "bill", "cancellation__bill", "reconciliation"
    ).get(pk=request_id)
    if outbound.status != GePGRequest.Status.RETRY:
        return
    if outbound.next_attempt_at and outbound.next_attempt_at > timezone.now():
        return

    response_xml = retry_request(outbound)
    outbound.refresh_from_db()
    if response_xml is None:
        if outbound.status == GePGRequest.Status.EXHAUSTED:
            mark_request_exhausted(outbound)
            logger.error("GePG outbound request %s exhausted retries", outbound.req_id)
        return

    try:
        if outbound.operation == GePGRequest.Operation.BILL:
            from .gateways.gepg import _parse_bill_response
            from .services.bill import record_bill_submission_result

            result = _parse_bill_response(response_xml)
            finish_gepg_request(
                outbound,
                accepted=result["success"],
                status_code=result["status_code"],
                status_desc=result["status_desc"],
                response_xml=response_xml,
            )
            record_bill_submission_result(outbound.bill, result)
        elif outbound.operation == GePGRequest.Operation.CANCELLATION:
            from .services.gepg_operations import _apply_cancellation_response

            _apply_cancellation_response(outbound, response_xml)
        elif outbound.operation == GePGRequest.Operation.RECONCILIATION:
            from .services.gepg_operations import _apply_reconciliation_ack

            _apply_reconciliation_ack(outbound, response_xml)
    except Exception as exc:
        finish_gepg_request(
            outbound,
            accepted=False,
            status_code="7242",
            status_desc=str(exc),
            response_xml=response_xml,
        )
        logger.exception(
            "GePG returned an unprocessable response for %s", outbound.req_id
        )
