"""Role assignment and protection rules."""

from django.contrib.auth.models import Group
from django.db import transaction

from apps.core.exceptions import ServiceError
from apps.users.roles import PROTECTED_ROLES


@transaction.atomic
def sync_user_roles(*, user, role_names: list[str]):
    """Replace a user's group membership with ``role_names``.

    Raises:
        ServiceError: If any name does not correspond to an existing group.
    """
    groups = list(Group.objects.filter(name__in=role_names))
    missing = set(role_names) - {group.name for group in groups}
    if missing:
        raise ServiceError(f"Unknown role(s): {', '.join(sorted(missing))}")
    user.groups.set(groups)
    return user


def assert_role_mutable(group: Group) -> None:
    """Reject changes to a protected role.

    ``superadmin`` is the escape hatch that fixes a broken permission setup, so
    allowing it to be renamed, deleted or narrowed would let an administrator
    lock every user out of the system irrecoverably.

    Raises:
        ServiceError: If the group is protected.
    """
    if group.name in PROTECTED_ROLES:
        raise ServiceError(f"The '{group.name}' role is protected and cannot be changed.")
