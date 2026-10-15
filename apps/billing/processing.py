"""Process durable GePG inbox and outbox records from PostgreSQL."""

import logging
import time
from datetime import timedelta

from defusedxml.ElementTree import fromstring

from django.conf import settings
from django.db.models import F, Q
from django.utils import timezone

from .gepg_transport import finish_gepg_request, mark_request_exhausted
from .gepg_transport import retry_gepg_request as retry_request
from .models import GePGCallback, GePGRequest

logger = logging.getLogger(__name__)
STALE_PROCESSING_AFTER = timedelta(minutes=5)
DEFAULT_PROCESSING_BUDGET_SECONDS = 45
# Reserve the 30-second HTTP timeout plus time to persist the result.
MAX_PROCESSING_ITEM_SECONDS = 35


class GePGCallbackRejectedError(Exception):
    """A callback was validly received but its business data was rejected."""


def _callback_is_due(now):
    """Build the status condition for callbacks ready to be claimed."""
    return (
        Q(status=GePGCallback.Status.PENDING)
        & (Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
    ) | Q(
        status=GePGCallback.Status.PROCESSING,
        updated_at__lt=now - STALE_PROCESSING_AFTER,
    )


def process_gepg_callback(callback_id: int) -> bool:
    """Claim and process one due callback, recording retry state in PostgreSQL."""
    now = timezone.now()
    claimed = (
        GePGCallback.objects.filter(pk=callback_id)
        .filter(_callback_is_due(now))
        .update(
            status=GePGCallback.Status.PROCESSING,
            attempts=F("attempts") + 1,
            next_attempt_at=None,
            last_error="",
            updated_at=now,
        )
    )
    if not claimed:
        return False

    callback = GePGCallback.objects.get(pk=callback_id)
    try:
        if callback.kind == GePGCallback.Kind.PAYMENT:
            from .services.payment import process_payment_notification

            acknowledgement = process_payment_notification(callback.payload)
            root = fromstring(acknowledgement)
            code = root.findtext(".//AckStsCode", "")
        elif callback.kind == GePGCallback.Kind.BILL:
            from .services.bill import handle_bill_response_callback

            root = fromstring(handle_bill_response_callback(callback.payload))
            code = root.findtext(".//AckStsCode", "")
        elif callback.kind == GePGCallback.Kind.RECONCILIATION:
            from .services.gepg_operations import handle_reconciliation_response

            root = fromstring(handle_reconciliation_response(callback.payload))
            code = root.findtext(".//AckStsCode", "")
        else:
            raise ValueError(f"Unsupported callback type: {callback.kind}")
        if code != "7101":
            raise GePGCallbackRejectedError(f"Callback returned GePG code {code}.")
    except GePGCallbackRejectedError as exc:
        callback.status = GePGCallback.Status.FAILED
        callback.next_attempt_at = None
        callback.last_error = str(exc)[:2000]
        callback.save(
            update_fields=["status", "next_attempt_at", "last_error", "updated_at"]
        )
        logger.error("GePG callback %s was rejected: %s", callback.pk, exc)
        return True
    except Exception as exc:
        callback.last_error = str(exc)[:2000]
        elapsed = timezone.now() - callback.created_at
        if elapsed >= timedelta(seconds=settings.GEPG_RETRY_MAX_AGE_SECONDS):
            callback.status = GePGCallback.Status.FAILED
            callback.next_attempt_at = None
            callback.save(
                update_fields=["status", "next_attempt_at", "last_error", "updated_at"]
            )
            logger.exception("GePG callback %s exhausted retries", callback.pk)
            return True

        callback.status = GePGCallback.Status.PENDING
        delay = min(
            settings.GEPG_RETRY_INITIAL_SECONDS * 2 ** min(callback.attempts - 1, 10),
            settings.GEPG_RETRY_MAX_SECONDS,
        )
        callback.next_attempt_at = timezone.now() + timedelta(seconds=delay)
        callback.save(
            update_fields=["status", "next_attempt_at", "last_error", "updated_at"]
        )
        logger.exception("GePG callback %s will be retried", callback.pk)
        return True

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
    return True


def _recover_stale_outbound_requests(now):
    """Return requests abandoned during a process or server interruption to retry."""
    return GePGRequest.objects.filter(
        status=GePGRequest.Status.SENDING,
        updated_at__lt=now - STALE_PROCESSING_AFTER,
    ).update(
        status=GePGRequest.Status.RETRY,
        next_attempt_at=now,
        last_error="Recovered an outbound request interrupted while sending.",
        updated_at=now,
    )


def _next_due_callback_id(now):
    return (
        GePGCallback.objects.filter(_callback_is_due(now))
        .order_by("created_at")
        .values_list("pk", flat=True)
        .first()
    )


def _next_due_request_id(now):
    due = Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)
    return (
        GePGRequest.objects.filter(status=GePGRequest.Status.RETRY)
        .filter(due)
        .order_by("next_attempt_at", "created_at")
        .values_list("pk", flat=True)
        .first()
    )


def _process_gepg_request(request_id: int) -> bool:
    """Atomically claim and retry one due outbound request."""
    now = timezone.now()
    due = Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)
    claimed = (
        GePGRequest.objects.filter(pk=request_id, status=GePGRequest.Status.RETRY)
        .filter(due)
        .update(
            status=GePGRequest.Status.SENDING,
            next_attempt_at=None,
            updated_at=now,
        )
    )
    if not claimed:
        return False

    outbound = GePGRequest.objects.select_related(
        "bill", "cancellation__bill", "reconciliation"
    ).get(pk=request_id)
    response_xml = retry_request(outbound)
    outbound.refresh_from_db()
    if response_xml is None:
        if outbound.status == GePGRequest.Status.EXHAUSTED:
            mark_request_exhausted(outbound)
            logger.error("GePG outbound request %s exhausted retries", outbound.req_id)
        return True

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
        else:
            raise ValueError(f"Unsupported outbound operation: {outbound.operation}")
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
    return True


def process_due_gepg_work(
    *, max_runtime_seconds: int = DEFAULT_PROCESSING_BUDGET_SECONDS
) -> dict[str, int]:
    """Process due inbox/outbox rows within one bounded timer invocation."""
    started_at = time.monotonic()
    deadline = started_at + max_runtime_seconds
    recovered_requests = _recover_stale_outbound_requests(timezone.now())
    callbacks = 0
    requests = 0

    while deadline - time.monotonic() >= MAX_PROCESSING_ITEM_SECONDS:
        did_work = False
        callback_id = _next_due_callback_id(timezone.now())
        if (
            callback_id is not None
            and deadline - time.monotonic() >= MAX_PROCESSING_ITEM_SECONDS
            and process_gepg_callback(callback_id)
        ):
            callbacks += 1
            did_work = True

        if deadline - time.monotonic() >= MAX_PROCESSING_ITEM_SECONDS:
            request_id = _next_due_request_id(timezone.now())
            if (
                request_id is not None
                and deadline - time.monotonic() >= MAX_PROCESSING_ITEM_SECONDS
                and _process_gepg_request(request_id)
            ):
                requests += 1
                did_work = True

        if not did_work:
            break

    return {
        "callbacks": callbacks,
        "outbound_requests": requests,
        "recovered_requests": recovered_requests,
    }
