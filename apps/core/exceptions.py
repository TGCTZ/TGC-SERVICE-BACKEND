"""Exceptions raised by the service layer."""


class ServiceError(Exception):
    """Base class for business-rule violations raised by services.

    Translated to HTTP 400 by ``apps.core.handlers.api_exception_handler``, so
    services never need to know they are being called from a web request.
    """
