"""Accept GePG callbacks outside the versioned, JWT-authenticated API.

These plain Django POST views keep the gateway callback URLs stable and return
XML acknowledgements for handled requests. Responses are signed only when
configured; unhandled exceptions are not guaranteed to produce an acknowledgement.
Inbound signatures are not verified, and ``GEPG_PUBLIC_CERT_PATH`` is unused.
"""

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .services import (
    handle_bill_response_callback,
    handle_cancel_response,
    handle_reconciliation_response,
    process_payment_notification,
)

XML_CONTENT_TYPE = "text/xml; charset=utf-8"


@method_decorator(csrf_exempt, name="dispatch")
class PaymentNotificationView(View):
    """Receive a ``pmtSpNtfReq`` payment notification."""

    def post(self, request, *args, **kwargs):
        """Apply the payment and answer with a signed acknowledgement."""
        body = request.body.decode("utf-8", errors="replace")
        ack = process_payment_notification(body)
        return HttpResponse(ack, content_type=XML_CONTENT_TYPE)


@method_decorator(csrf_exempt, name="dispatch")
class BillResponseView(View):
    """Receive an asynchronous ``billSubRes`` control-number callback."""

    def post(self, request, *args, **kwargs):
        """Store the control number and answer with a signed acknowledgement."""
        body = request.body.decode("utf-8", errors="replace")
        ack = handle_bill_response_callback(body)
        return HttpResponse(ack, content_type=XML_CONTENT_TYPE)


@method_decorator(csrf_exempt, name="dispatch")
class BillCancelResponseView(View):
    """Accept asynchronous bill cancellation responses from GePG."""

    def post(self, request, *args, **kwargs):
        """Persist a cancellation result and return its XML acknowledgement."""
        ack = handle_cancel_response(request.body.decode("utf-8", errors="replace"))
        return HttpResponse(ack, content_type=XML_CONTENT_TYPE)


@method_decorator(csrf_exempt, name="dispatch")
class ReconciliationResponseView(View):
    """Accept payment batch responses from GePG reconciliation."""

    def post(self, request, *args, **kwargs):
        """Persist batch details and return the legacy response acknowledgement."""
        ack = handle_reconciliation_response(
            request.body.decode("utf-8", errors="replace")
        )
        return HttpResponse(ack, content_type=XML_CONTENT_TYPE)
