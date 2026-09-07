"""Middleware that resolves the API user before the view runs.

DRF authenticates lazily, inside the view, which is too late for anything that
runs as middleware. ``CurrentUserMiddleware`` and django-auditlog's middleware
both read ``request.user``, so on a token-authenticated request they would see
``AnonymousUser`` and silently record no actor at all - leaving ``created_by``,
``updated_by`` and every audit-log entry unattributed.

Resolving the token here, once, fixes both without either of them knowing.
"""

import logging

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

logger = logging.getLogger(__name__)


class APIAuthenticationMiddleware:
    """Populate ``request.user`` from a Bearer token during the middleware phase.

    Must be listed after ``AuthenticationMiddleware`` (which sets up the session
    user it may override) and before ``CurrentUserMiddleware`` and
    ``AuditlogMiddleware``, which are the two consumers that need it.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.authenticator = JWTAuthentication()

    def __call__(self, request):
        """Resolve the bearer token, leaving session auth untouched otherwise."""
        if "HTTP_AUTHORIZATION" in request.META:
            try:
                result = self.authenticator.authenticate(request)
            except (InvalidToken, TokenError) as exc:
                # Swallowed deliberately: DRF authenticates again inside the view
                # and is responsible for turning a bad token into a 401. Raising
                # here would bypass DRF's error shaping and content negotiation.
                logger.debug("Ignoring unusable token in middleware: %s", exc)
            else:
                if result is not None:
                    request.user = result[0]
        return self.get_response(request)
