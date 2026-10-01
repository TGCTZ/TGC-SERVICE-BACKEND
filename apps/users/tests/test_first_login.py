"""First login: set your password, then your profile, then the system."""

import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from django.contrib.auth.models import Group

from apps.users.services.accounts import create_user_account
from apps.users.tests.factories import GenderFactory, UserFactory

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "Str0ng!Passphrase"


@pytest.fixture
def new_account(roles):
    """A receptionist account as the Users screen creates it: ``(user, password)``."""
    creator = UserFactory(is_superuser=True)
    return create_user_account(
        email="new@example.com",
        role=Group.objects.get(name="receptionist"),
        actor=creator,
    )


def _signed_in(api_client, user):
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client, refresh


def _profile(**overrides):
    return {
        "first_name": "Neema",
        "last_name": "Mushi",
        "phone_number": "255700000009",
        "gender": GenderFactory().pk,
        **overrides,
    }


def test_the_emailed_credentials_sign_in(api_client, new_account):
    """Signing in works, and says a first login is due."""
    user, password = new_account

    response = api_client.post(
        "/api/v1/auth/login/", {"email": user.email, "password": password}
    )

    assert response.status_code == 200, response.data
    assert response.data["user"]["must_change_password"] is True
    assert response.data["user"]["must_complete_profile"] is True


def test_until_first_login_is_done_only_its_steps_are_open(api_client, new_account):
    """Enforced by the API, so a token and curl cannot skip the UI's redirect."""
    client, _ = _signed_in(api_client, new_account[0])

    blocked = client.get("/api/v1/orders/")
    assert blocked.status_code == 403
    assert blocked.data["code"] == "first_login_required"
    assert client.patch("/api/v1/auth/me/", {"first_name": "X"}).status_code == 403

    assert client.get("/api/v1/auth/me/").status_code == 200
    assert client.get("/api/v1/genders/").status_code == 200


def test_the_password_step_replaces_the_temporary_one(api_client, new_account):
    """Not the temporary password again; old sessions end, the new pair works."""
    user, temporary = new_account
    client, old_refresh = _signed_in(api_client, user)
    url = "/api/v1/auth/first-login/password/"

    reused = client.post(url, {"password": temporary, "password_confirm": temporary})
    mismatch = client.post(url, {"password": NEW_PASSWORD, "password_confirm": "nope"})
    assert (reused.status_code, mismatch.status_code) == (400, 400)

    done = client.post(url, {"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD})
    assert done.status_code == 200, done.data
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD) and not user.must_change_password

    # The old session is over; the pair the step returned carries on.
    stale = api_client.post("/api/v1/auth/refresh/", {"refresh": str(old_refresh)})
    assert stale.status_code == 401
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {done.data['access']}")
    assert api_client.get("/api/v1/auth/me/").status_code == 200
    # Still one step to go.
    assert api_client.get("/api/v1/orders/").status_code == 403


def test_the_profile_step_comes_second_and_needs_gender(api_client, new_account):
    """Password first, so a leaked temporary password cannot finish the setup."""
    user, _ = new_account
    client, _ = _signed_in(api_client, user)
    url = "/api/v1/auth/first-login/profile/"

    early = client.post(url, _profile())
    assert early.status_code == 400

    step_one = client.post(
        "/api/v1/auth/first-login/password/",
        {"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD},
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {step_one.data['access']}")

    no_gender = client.post(url, {k: v for k, v in _profile().items() if k != "gender"})
    assert no_gender.status_code == 400
    assert "gender" in no_gender.data

    done = client.post(url, _profile())
    assert done.status_code == 200, done.data
    assert done.data["full_name"] == "Neema Mushi"
    assert done.data["must_complete_profile"] is False

    # The system is theirs now, within their role.
    assert client.get("/api/v1/orders/").status_code == 200


def test_existing_accounts_are_left_alone(user, auth_client):
    """Accounts from before the flow have no first login to do."""
    response = auth_client(user).get("/api/v1/auth/me/")

    assert response.status_code == 200
    assert response.data["must_change_password"] is False
    assert response.data["must_complete_profile"] is False
