"""Accounts created by staff: an email and a role, then a credentials email."""

import pytest
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail

from apps.users.services import accounts
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db
User = get_user_model()


def _create(client, email="asha.juma@example.com", role="receptionist"):
    return client.post("/api/v1/users/", {"email": email, "role": role}, format="json")


def test_an_email_and_a_role_are_all_it_takes(
    auth_client, admin_user, django_capture_on_commit_callbacks
):
    """The system sets the rest: Tanzania, Active, a password, first-login flags."""
    client = auth_client(admin_user)

    with django_capture_on_commit_callbacks(execute=True):
        response = _create(client)

    assert response.status_code == 201, response.data
    password = response.data["temporary_password"]
    user = User.objects.get(email="asha.juma@example.com")
    assert user.username == "asha.juma"
    assert (user.country, user.user_status.name, user.is_active) == (
        "Tanzania",
        "Active",
        True,
    )
    assert user.must_change_password and user.must_complete_profile
    assert set(user.groups.values_list("name", flat=True)) == {"receptionist"}
    assert user.check_password(password)

    # Shown once: the account's own record never carries it.
    assert "temporary_password" not in client.get(f"/api/v1/users/{user.pk}/").data


def test_the_new_user_is_emailed_their_credentials_and_where_to_sign_in(
    auth_client, admin_user, django_capture_on_commit_callbacks
):
    """Email, username, temporary password, the link, and what happens next."""
    with django_capture_on_commit_callbacks(execute=True):
        response = _create(auth_client(admin_user))

    [message] = mail.outbox
    assert message.to == ["asha.juma@example.com"]
    for expected in (
        "asha.juma@example.com",
        response.data["username"],
        response.data["temporary_password"],
        f"{settings.FRONTEND_URL}/sign-in",
        "choose your own password",
    ):
        assert expected in message.body
    assert message.alternatives, "expected an HTML version too"


def test_nothing_is_emailed_until_the_account_is_saved(auth_client, admin_user):
    """The mail waits for the transaction; a rolled-back account gets none."""
    _create(auth_client(admin_user))

    assert mail.outbox == []


def test_a_failed_email_does_not_undo_the_account(
    auth_client, admin_user, django_capture_on_commit_callbacks, monkeypatch
):
    """The creator has the credentials on screen; the account must survive."""

    def refuse(**kwargs):
        raise OSError("mail server down")

    monkeypatch.setattr(accounts, "send_mail", refuse)
    with django_capture_on_commit_callbacks(execute=True):
        response = _create(auth_client(admin_user))

    assert response.status_code == 201
    assert User.objects.filter(email="asha.juma@example.com").exists()


def test_usernames_and_emails_stay_unique(auth_client, admin_user):
    """Usernames come from the email and take a suffix; emails never repeat."""
    client = auth_client(admin_user)

    first = _create(client, email="asha@one.example")
    second = _create(client, email="asha@two.example")
    again = _create(client, email="ASHA@one.example")

    assert (first.data["username"], second.data["username"]) == ("asha", "asha2")
    assert again.status_code == 400
    assert "email" in again.data


def test_temporary_passwords_are_random_and_easy_to_read_out():
    """No two alike, and no 0/O or 1/l/I to mistake over the phone."""
    passwords = {accounts.generate_temporary_password() for _ in range(200)}

    assert len(passwords) == 200
    assert all(len(p) == accounts.TEMPORARY_PASSWORD_LENGTH for p in passwords)
    assert not set("".join(passwords)) & set("0O1lI")


# ------------------------------------------------------------ reset ---


def _holding(role: str):
    account = UserFactory()
    account.groups.add(Group.objects.get(name=role))
    return account


def test_a_reset_issues_a_new_password_and_ends_every_session(
    auth_client, admin_user, django_capture_on_commit_callbacks
):
    """For credentials that never arrived, or a forgotten password."""
    colleague = _holding("receptionist")
    old_session = RefreshToken.for_user(colleague)

    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client(admin_user).post(
            f"/api/v1/users/{colleague.pk}/reset-password/"
        )

    assert response.status_code == 200, response.data
    colleague.refresh_from_db()
    assert colleague.check_password(response.data["temporary_password"])
    assert colleague.must_change_password
    assert BlacklistedToken.objects.filter(token__jti=old_session["jti"]).exists()
    assert len(mail.outbox) == 1


def test_a_reset_follows_the_hierarchy(auth_client, admin_user, roles):
    """Not yourself (use Settings), not a peer, and superiors are out of sight."""
    client = auth_client(admin_user)

    own = client.post(f"/api/v1/users/{admin_user.pk}/reset-password/")
    peer = client.post(f"/api/v1/users/{_holding('manager').pk}/reset-password/")
    superior = client.post(f"/api/v1/users/{_holding('admin').pk}/reset-password/")

    assert (own.status_code, peer.status_code, superior.status_code) == (400, 403, 404)
