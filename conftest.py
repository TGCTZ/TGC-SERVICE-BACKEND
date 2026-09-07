"""Fixtures available to the whole suite.

Imports are deferred into the fixture bodies: this module is imported before
Django's app registry is populated, so a module-level model import would fail.
"""

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    """An unauthenticated DRF test client."""
    return APIClient()


@pytest.fixture
def roles(db):
    """Create the project's groups and permissions exactly as production does."""
    from django.core.management import call_command

    call_command("setup_roles", verbosity=0)


@pytest.fixture
def user(db):
    """A plain user with no roles."""
    from apps.users.tests.factories import UserFactory

    return UserFactory()


@pytest.fixture
def admin_user(db, roles):
    """A user holding the admin role."""
    from django.contrib.auth.models import Group

    from apps.users.tests.factories import UserFactory

    account = UserFactory()
    account.groups.add(Group.objects.get(name="admin"))
    return account


@pytest.fixture
def viewer_user(db, roles):
    """A user holding the read-only viewer role."""
    from django.contrib.auth.models import Group

    from apps.users.tests.factories import UserFactory

    account = UserFactory()
    account.groups.add(Group.objects.get(name="viewer"))
    return account


@pytest.fixture
def auth_client(api_client):
    """Factory fixture returning a client authenticated as a given user."""
    from rest_framework_simplejwt.tokens import RefreshToken

    def _authenticate(account):
        token = RefreshToken.for_user(account)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        return api_client

    return _authenticate
