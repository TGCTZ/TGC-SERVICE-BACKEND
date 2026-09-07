"""Project-wide DRF exception handling."""

import logging

from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404

from apps.core.exceptions import ServiceError

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    """Translate service and database errors into DRF responses.

    Services raise ``ServiceError`` for business-rule violations without knowing
    anything about HTTP; this is the single place that maps them onto a status
    code. Anything unrecognised falls through to DRF, and a genuinely unhandled
    exception is logged with its traceback and reported as a bare 500 so
    internals never reach the client.
    """
    if isinstance(exc, ServiceError):
        exc = DRFValidationError({"detail": str(exc)})
    elif isinstance(exc, DjangoValidationError):
        exc = DRFValidationError(
            exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        )
    elif isinstance(exc, Http404):
        exc = NotFound()
    elif isinstance(exc, IntegrityError):
        logger.warning("Integrity error: %s", exc)
        exc = DRFValidationError(
            {"detail": "This operation conflicts with existing data."}
        )

    response = drf_exception_handler(exc, context)

    if response is None:
        logger.exception("Unhandled exception in %s", context.get("view"))
        return Response(
            {"detail": "A server error occurred."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return response
