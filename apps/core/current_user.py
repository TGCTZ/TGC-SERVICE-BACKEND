"""Request-user tracking for audit columns.

Stores the current request's user in a contextvar so models can stamp
``created_by``/``updated_by``/``deleted_by`` without the user being threaded
through every call. Contextvars are safe under both sync and async request
handling, unlike thread-locals.
"""

from contextvars import ContextVar

_current_user: ContextVar = ContextVar("current_user", default=None)


def get_current_user():
    """Return the user for the active request, or None outside one."""
    return _current_user.get()


def set_current_user(user):
    """Set the active user; returns a token for ``reset_current_user``."""
    return _current_user.set(user)


def reset_current_user(token):
    """Restore the previous value using a token from ``set_current_user``."""
    _current_user.reset(token)


class CurrentUserMiddleware:
    """Bind the authenticated request user to the current context.

    Must be listed after ``AuthenticationMiddleware``, which is what populates
    ``request.user``. The reset in ``finally`` matters: without it a worker
    thread would leak the previous request's user into the next one.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Set the user for the duration of the request, then restore."""
        user = getattr(request, "user", None)
        token = set_current_user(user if user and user.is_authenticated else None)
        try:
            return self.get_response(request)
        finally:
            reset_current_user(token)
