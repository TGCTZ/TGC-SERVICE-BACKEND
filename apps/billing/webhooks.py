"""GePG callback endpoints with optional signature validation and durable inboxing."""

import logging

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .gateways.gepg import (
    build_bill_response_ack,
    build_payment_ack,
    build_reconciliation_ack,
)
from .gateways.signing import verify_payload
from .models import GePGCallback
from .services import handle_cancel_response
from .tasks import process_gepg_callback

logger = logging.getLogger(__name__)
XML_CONTENT_TYPE = "text/xml; charset=utf-8"


def _ack(kind: str, event_id: str, code: str) -> str:
    """Build the acknowledgement envelope expected by a callback type."""
    if kind == GePGCallback.Kind.PAYMENT:
        return build_payment_ack(event_id, code)
    if kind == GePGCallback.Kind.BILL:
        return build_bill_response_ack(event_id, code)
    return build_reconciliation_ack(event_id, code)


def _event_id(kind: str, payload: str) -> str:
    """Read the protocol correlation ID used to deduplicate gateway retries."""
    root = fromstring(payload)
    if kind == GePGCallback.Kind.PAYMENT:
        return root.findtext(".//pmtSpNtfReq/PmtHdr/ReqId", "")
    if kind == GePGCallback.Kind.BILL:
        return root.findtext(".//billSubRes/BillHdr/ResId", "")
    if kind == GePGCallback.Kind.RECONCILIATION:
        return root.findtext(".//sucSpPmtRes/BatchHdr/ResId", "")
    raise ValueError(f"Unsupported callback type: {kind}")


def _queue_callback(request, kind: str) -> HttpResponse:
    """Optionally verify, persist, enqueue, and acknowledge one callback."""
    try:
        payload = request.body.decode("utf-8")
        event_id = _event_id(kind, payload)
        if not event_id:
            raise ValueError("Missing callback correlation ID")
    except (UnicodeDecodeError, ValueError, ParseError, DefusedXmlException):
        return HttpResponse(_ack(kind, "ERROR", "7242"), content_type=XML_CONTENT_TYPE)

    if settings.GEPG_VERIFY_CALLBACK_SIGNATURE:
        try:
            is_valid = verify_payload(payload)
        except (OSError, ValueError):
            logger.exception("GePG callback verification is unavailable")
            return HttpResponse(
                "GePG callback verification temporarily unavailable", status=503
            )
        if not is_valid:
            logger.warning("Rejected GePG callback with invalid signature (%s)", kind)
            return HttpResponse(
                _ack(kind, event_id, "7303"), content_type=XML_CONTENT_TYPE
            )

    try:
        try:
            callback, _created = GePGCallback.objects.get_or_create(
                kind=kind,
                event_id=event_id,
                defaults={"payload": payload},
            )
        except IntegrityError:
            callback = GePGCallback.objects.get(kind=kind, event_id=event_id)

        if callback.status != GePGCallback.Status.PROCESSED and (
            callback.next_attempt_at is None or callback.next_attempt_at <= timezone.now()
        ):
            process_gepg_callback.delay(callback.pk)
    except Exception:
        # The persisted inbox row will be redispatched by Celery Beat if the
        # broker is unavailable. Ask GePG to retry rather than false-acknowledge.
        logger.exception("Could not persist or queue GePG callback %s", event_id)
        return HttpResponse("GePG callback temporarily unavailable", status=503)

    return HttpResponse(_ack(kind, event_id, "7101"), content_type=XML_CONTENT_TYPE)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(transaction.non_atomic_requests, name="dispatch")
class PaymentNotificationView(View):
    """Receive and durably queue a ``pmtSpNtfReq`` payment notification."""

    def post(self, request, *args, **kwargs):
        """Enqueue one payment event."""
        return _queue_callback(request, GePGCallback.Kind.PAYMENT)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(transaction.non_atomic_requests, name="dispatch")
class BillResponseView(View):
    """Receive and durably queue an asynchronous ``billSubRes`` callback."""

    def post(self, request, *args, **kwargs):
        """Enqueue one bill response event."""
        return _queue_callback(request, GePGCallback.Kind.BILL)


@method_decorator(csrf_exempt, name="dispatch")
class BillCancelResponseView(View):
    """Handle the legacy cancellation response endpoint."""

    def post(self, request, *args, **kwargs):
        """Process one cancellation response."""
        try:
            payload = request.body.decode("utf-8")
        except UnicodeDecodeError:
            return HttpResponse(status=400)
        if settings.GEPG_VERIFY_CALLBACK_SIGNATURE:
            try:
                if not verify_payload(payload):
                    return HttpResponse(status=400)
            except (OSError, ValueError):
                logger.exception("GePG cancellation signature verification unavailable")
                return HttpResponse(status=503)
        return HttpResponse(
            handle_cancel_response(payload), content_type=XML_CONTENT_TYPE
        )


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(transaction.non_atomic_requests, name="dispatch")
class ReconciliationResponseView(View):
    """Receive and durably queue a ``sucSpPmtRes`` callback."""

    def post(self, request, *args, **kwargs):
        """Enqueue one reconciliation response event."""
        return _queue_callback(request, GePGCallback.Kind.RECONCILIATION)
