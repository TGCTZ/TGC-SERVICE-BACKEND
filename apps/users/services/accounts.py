"""Accounts created by staff, and the first login that finishes them.

There is no self-registration. A superadmin, admin or manager creates an
account from an email and a role; the system fills in the rest - Tanzania,
Active, a temporary password - and emails the credentials. The user then has to
set their own password and complete their profile before the app opens up to
them; ``apps/users/authentication.py`` holds them to that.

The temporary password is random per account rather than one shared default: a
default everyone knows lets anyone who knows a new colleague's email sign in
first and take the account. It is shown once to whoever created or reset it,
and emailed - never stored in a form that can be read back.
"""

import logging
import re
import secrets

from rest_framework_simplejwt.tokens import RefreshToken

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string

from apps.core.exceptions import ServiceError
from apps.users.models import UserStatus
from apps.users.services.auth import revoke_all_tokens
from apps.users.services.roles import assert_can_assign

logger = logging.getLogger(__name__)
User = get_user_model()

COUNTRY = "Tanzania"
ACTIVE_STATUS = "Active"

#: Letters and digits a reader cannot confuse when copying from a screen or
#: reading over the phone: no 0/O, 1/l/I.
_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TEMPORARY_PASSWORD_LENGTH = 10


def generate_temporary_password() -> str:
    """A random password for a first sign-in, from an unambiguous alphabet."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(TEMPORARY_PASSWORD_LENGTH))


def _username_for(email: str) -> str:
    """A unique username from the email's local part: ``asha``, ``asha2``...

    Soft-deleted accounts count, since the column is unique across them too.
    """
    base = re.sub(r"[^a-z0-9._-]+", "", email.split("@")[0].lower())[:140] or "user"
    candidate, suffix = base, 1
    while User.all_objects.filter(username=candidate).exists():
        suffix += 1
        candidate = f"{base}{suffix}"
    return candidate


@transaction.atomic
def create_user_account(*, email: str, role, actor) -> tuple:
    """Create an account from an email and a role, and email its credentials.

    Args:
        email: The new user's email, also what they sign in with.
        role: The ``Group`` to give them.
        actor: Who is creating it; must outrank ``role``.

    Returns:
        ``(user, temporary_password)`` - the password so it can be shown once.

    Raises:
        PermissionDenied: If ``actor`` does not outrank ``role``.
    """
    assert_can_assign(actor, before=set(), after={role.name})
    password = generate_temporary_password()
    user = User.objects.create_user(
        email=email,
        username=_username_for(email),
        password=password,
        first_name="",
        last_name="",
        country=COUNTRY,
        user_status=UserStatus.objects.get_or_create(name=ACTIVE_STATUS)[0],
        is_active=True,
        must_change_password=True,
        must_complete_profile=True,
    )
    user.groups.set([role])
    _email_credentials_on_commit(user, password)
    return user, password


@transaction.atomic
def reset_temporary_password(*, user) -> str:
    """Give an account a new temporary password and send it again.

    For a colleague whose credentials email never came, or who has forgotten
    their password. Every session is ended and the password must be changed
    again at the next sign-in; a profile already completed stays completed.

    Returns:
        The new temporary password, so it can be shown once.
    """
    password = generate_temporary_password()
    user.set_password(password)
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password", "updated_at"])
    revoke_all_tokens(user)
    _email_credentials_on_commit(user, password)
    return password


def _email_credentials_on_commit(user, password: str) -> None:
    """Send the credentials once the account is really saved.

    Requests run in a transaction, so sending straight away could mail someone
    an account that is then rolled back. A failed send is logged, not raised:
    the account exists, and whoever created it has the credentials on screen.
    """

    def send():
        context = {
            "user": user,
            "password": password,
            "login_url": f"{settings.FRONTEND_URL.rstrip('/')}/sign-in",
            "lab_name": settings.CERTIFICATE_LAB_NAME,
        }
        try:
            send_mail(
                subject=f"Your {settings.CERTIFICATE_LAB_NAME} account",
                message=render_to_string("users/email/credentials.txt", context),
                html_message=render_to_string("users/email/credentials.html", context),
                from_email=None,  # DEFAULT_FROM_EMAIL
                recipient_list=[user.email],
            )
        except Exception:
            logger.exception("Could not email credentials to %s", user.email)

    transaction.on_commit(send)


@transaction.atomic
def complete_first_login_password(*, user, password: str) -> dict:
    """Set the user's own password in place of the temporary one.

    Returns:
        A fresh ``{"access", "refresh"}`` pair. Every older token is revoked -
        including the one this request came in on - so without new ones the
        user would be signed out halfway through their first login.

    Raises:
        ServiceError: If no password change is due, or the new password is the
            temporary one.
    """
    if not user.must_change_password:
        raise ServiceError("Your password has already been set.")
    if user.check_password(password):
        raise ServiceError("Choose a new password, not the temporary one.")

    user.set_password(password)
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password", "updated_at"])
    revoke_all_tokens(user)
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def complete_first_login_profile(*, user, serializer) -> None:
    """Save the profile the first login asks for, and open the app.

    Raises:
        ServiceError: If the password step has not been done yet - the order is
            password first, so a stolen temporary password cannot finish setup.
    """
    if user.must_change_password:
        raise ServiceError("Set your password first.")
    serializer.save(must_complete_profile=False)
