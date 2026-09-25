"""Authentication operations that involve more than serialising a payload."""

from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceError

User = get_user_model()


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
