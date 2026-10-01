"""Report access follows the existing model-view permissions."""

from rest_framework.permissions import BasePermission

from .definitions import allowed_sections


class CanReadReport(BasePermission):
    """A page is accessible when at least one of its sections is readable."""

    def has_permission(self, request, view):
        """Keep direct API requests subject to the same gates as navigation."""
        return bool(
            request.user
            and request.user.is_authenticated
            and allowed_sections(request.user, view.kind)
        )
