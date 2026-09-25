"""Permission class for the management statistics endpoints."""

from rest_framework.permissions import BasePermission


class CanViewStatistics(BasePermission):
    """Allows access only to users holding ``analytics.view_statistics``.

    Its own permission rather than a mix of the model ones: the statistics put
    revenue beside workload beside market mix, and a role that may read bills
    has not thereby been cleared to see the lab's whole financial picture.
    """

    def has_permission(self, request, view):
        """True when the requester may read the statistics."""
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_perm("analytics.view_statistics")
        )
