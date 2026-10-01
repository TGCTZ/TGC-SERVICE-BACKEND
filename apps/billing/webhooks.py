"""Server-to-server callbacks from the GePG payment gateway.

Deliberately plain Django views rather than DRF ones, mounted outside
``/api/v1/``. Four reasons, all load-bearing:

1. The callback URL is registered with GePG out of band. ``/api/v1/`` implies a
   ``/api/v2/`` one day, and re-registering a URL with a government gateway is
   not a deploy step.
2. Signed XML in, signed XML out. DRF's content negotiation, ``JSONParser``,
   pagination and ``api_exception_handler`` are all wrong here - even the
   failure path has to be a well-formed ``7102`` acknowledgement, or GePG keeps
   redelivering.
3. They are unauthenticated. ``DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]``
   fails closed by design; reaching around it per view is exactly the drift that
   setting exists to prevent. Staying outside DRF keeps the guarantee intact.
4. ``csrf_exempt`` on a plain view is the narrowest possible carve-out.

Note what is missing: nothing verifies that a request actually came from GePG.
``GEPG_PUBLIC_CERT_PATH`` is configured but never read, so a forged
``pmtSpNtfReq`` posted to this URL will mark a bill paid. This is carried over
from the system being ported and is the first follow-up to close.
"""

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .services import handle_bill_response_callback, process_payment_notification

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
