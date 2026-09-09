"""Permission classes and helpers."""

from rest_framework.permissions import DjangoModelPermissions

from django.core.exceptions import PermissionDenied


class StrictModelPermissions(DjangoModelPermissions):
    """``DjangoModelPermissions`` that also gates read access.

    DRF's stock class leaves GET, HEAD and OPTIONS wide open, which means an
    authenticated user with no permissions at all can still read every record.
    Requiring ``view_<model>`` closes that hole.

    There is deliberately no bespoke ``restore_<model>`` permission: it would
    have to be declared on every single model. ``restore`` is a POST, so it
    resolves to ``add_<model>`` through the map below - the frontend's
    ``restorePerm()`` mirrors that.
    """

    perms_map = {
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": [],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
        "POST": ["%(app_label)s.add_%(model_name)s"],
        "PUT": ["%(app_label)s.change_%(model_name)s"],
        "PATCH": ["%(app_label)s.change_%(model_name)s"],
        "DELETE": ["%(app_label)s.delete_%(model_name)s"],
    }


class ActionPermissions(StrictModelPermissions):
    """Gate a custom ``@action`` on a permission of its own.

    The parent maps by HTTP method, so every POST asks for ``add_<model>``.
    Workflow verbs are POSTs that mean something else entirely: transitioning a
    stone, finalizing a report or issuing a certificate are not creations, and
    each has its own permission declared on the model. Without this class those
    permissions would be decorative - anyone holding ``add_<model>`` would pass.

    Declare the mapping on the ViewSet, keyed by action name::

        class StoneViewSet(BaseModelViewSet, viewsets.ModelViewSet):
            action_permissions = {"transition": ["orders.transition_stone"]}

    An action that is not listed falls back to the method-based map, so the
    standard CRUD routes and ``restore`` are unaffected.
    """

    action_permissions: dict[str, list[str]] = {}

    def has_permission(self, request, view):
        """Check the action's own permissions, or defer to the method map."""
        required = getattr(view, "action_permissions", {}).get(
            getattr(view, "action", None)
        )
        if required is None:
            return super().has_permission(request, view)

        if not request.user or (
            not request.user.is_authenticated and self.authenticated_users_only
        ):
            return False
        return request.user.has_perms(required)


def require_permission(user, perm: str) -> None:
    """Assert that ``user`` holds ``perm``, raising ``PermissionDenied`` if not.

    Callable from any layer, including management commands and webhooks.

    Args:
        user: The acting user, or None for a trusted system call.
        perm: A permission label such as ``"gems.change_stonetype"``.

    Raises:
        PermissionDenied: If the user is present and lacks the permission.
    """
    if user is None:
        return
    if not user.has_perm(perm):
        raise PermissionDenied(f"Missing permission: {perm}")
