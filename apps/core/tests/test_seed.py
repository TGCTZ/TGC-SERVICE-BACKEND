"""The demo data command: one sign-in per role, so every screen can be tried."""

import pytest

from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.core.management.commands.seed import DEMO_PASSWORD
from apps.users.roles import ROLE_PERMISSIONS

pytestmark = pytest.mark.django_db


def test_every_role_gets_a_demo_account():
    """``<role>@example.com`` for each declared role - admin included.

    The accounts are made by looping over the groups setup_roles creates, so a
    new role gets one without touching the seed; this keeps it that way.
    """
    call_command("seed", users=0, orders=0, verbosity=0)

    for role in ROLE_PERMISSIONS:
        account = get_user_model().objects.get(email=f"{role}@example.com")
        assert account.check_password(DEMO_PASSWORD), role
        assert set(account.groups.values_list("name", flat=True)) == {role}

    # Only the break-glass account is a Django superuser; admin works through
    # its role, so the hierarchy applies to it.
    admin = get_user_model().objects.get(email="admin@example.com")
    assert not admin.is_superuser
