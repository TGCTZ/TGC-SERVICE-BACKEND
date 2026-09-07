"""Authentication operations that involve more than serialising a payload."""

from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceError

User = get_user_model()


@transaction.atomic
def register_user(*, password: str, roles: list[str] | None = None, **fields):
    """Create an account, hash its password and attach its initial roles.

    Args:
        password: Raw password; hashed before it reaches the database.
        roles: Group names to assign. Unknown names are rejected outright
            rather than silently ignored, since a typo would otherwise create
            an account with fewer permissions than intended.
        **fields: Remaining user fields.

    Returns:
        The newly created user.

    Raises:
        ServiceError: If any requested role does not exist.
    """
    user = User.objects.create_user(password=password, **fields)
    if roles:
        _attach_roles(user, roles)
    return user


@transaction.atomic
def change_password(*, user, current_password: str, new_password: str) -> None:
    """Replace a user's password and invalidate their other sessions.

    Blacklisting every outstanding refresh token except the current one means a
    stolen session cannot outlive the password change that was meant to end it.

    Raises:
        ServiceError: If the current password is wrong or the new one matches it.
    """
    if not user.check_password(current_password):
        raise ServiceError("The current password is incorrect.")
    if current_password == new_password:
        raise ServiceError("The new password must differ from the current one.")

    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    revoke_all_tokens(user)


def revoke_all_tokens(user) -> int:
    """Blacklist every outstanding refresh token for ``user``.

    Returns:
        The number of tokens newly blacklisted.
    """
    count = 0
    for token in OutstandingToken.objects.filter(user=user):
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        count += int(created)
    return count


def record_login(user) -> None:
    """Stamp the successful-login timestamp.

    Kept separate from ``last_login`` (which simplejwt can manage) so the API
    exposes a field the project controls.
    """
    user.last_login_at = timezone.now()
    user.save(update_fields=["last_login_at", "updated_at"])


def _attach_roles(user, roles: list[str]) -> None:
    """Set a user's groups from a list of role names."""
    groups = list(Group.objects.filter(name__in=roles))
    missing = set(roles) - {group.name for group in groups}
    if missing:
        raise ServiceError(f"Unknown role(s): {', '.join(sorted(missing))}")
    user.groups.set(groups)
