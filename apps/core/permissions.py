"""Permission classes and helpers."""

from rest_framework.permissions import DjangoModelPermissions

from django.core.exceptions import PermissionDenied


class StrictModelPermissions(DjangoModelPermissions):
    """``DjangoModelPermissions`` that also gates read access.

    DRF's stock class leaves GET, HEAD and OPTIONS wide open, which means an
    authenticated user with no permissions at all can still read every record.
    Requiring ``view_<model>`` closes that hole.

    The ``restore`` action is mapped to ``change_<model>`` rather than a bespoke
    ``restore_<model>`` permission: bringing a row back is a state change, and a
    dedicated permission would have to be declared on every single model.
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


def require_permission(user, perm: str) -> None:
    """Assert that ``user`` holds ``perm``, raising ``PermissionDenied`` if not.

    Callable from any layer, including management commands and webhooks.

    Args:
        user: The acting user, or None for a trusted system call.
        perm: A permission label such as ``"catalog.change_product"``.

    Raises:
        PermissionDenied: If the user is present and lacks the permission.
    """
    if user is None:
        return
    if not user.has_perm(perm):
        raise PermissionDenied(f"Missing permission: {perm}")
