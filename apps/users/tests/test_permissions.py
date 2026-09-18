"""Role-based access control."""

import pytest

from apps.gems.tests.factories import StoneCategoryFactory, StoneTypeFactory

pytestmark = pytest.mark.django_db


def test_setup_roles_creates_every_role(roles):
    """The management command materialises the whole role matrix."""
    from django.contrib.auth.models import Group

    from apps.users.roles import ROLE_PERMISSIONS

    assert set(Group.objects.values_list("name", flat=True)) == set(ROLE_PERMISSIONS)


def test_setup_roles_reports_a_retired_role_without_removing_it(roles):
    """A group the matrix no longer declares is reported, not silently dropped.

    Pruning removes group memberships, so it has to be asked for.
    """
    from io import StringIO

    from django.contrib.auth.models import Group
    from django.core.management import call_command

    Group.objects.create(name="retired")
    out = StringIO()
    call_command("setup_roles", stdout=out)

    assert "retired" in out.getvalue()
    assert Group.objects.filter(name="retired").exists()


def test_setup_roles_prune_removes_a_retired_role(roles):
    """--prune brings the database back in line with the matrix."""
    from django.contrib.auth.models import Group
    from django.core.management import call_command

    Group.objects.create(name="retired")
    call_command("setup_roles", "--prune", verbosity=0)

    assert not Group.objects.filter(name="retired").exists()
    assert Group.objects.filter(name="administrator").exists()


def test_setup_roles_prune_removes_a_retired_module_gate(roles):
    """A gate dropped from ModuleGate.Meta stops granting access.

    Shrinking ``Meta.permissions`` leaves the old row in ``auth_permission``,
    where it keeps working for anyone who already holds it.
    """
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType
    from django.core.management import call_command

    from apps.core.models import ModuleGate

    Permission.objects.create(
        content_type=ContentType.objects.get_for_model(ModuleGate),
        codename="module_retired",
        name="Can access the retired module",
    )
    call_command("setup_roles", "--prune", verbosity=0)

    assert not Permission.objects.filter(codename="module_retired").exists()


def test_superadmin_gets_every_permission(roles):
    """The superadmin role resolves dynamically, so new models are covered."""
    from django.contrib.auth.models import Group, Permission

    superadmin = Group.objects.get(name="superadmin")

    assert superadmin.permissions.count() == Permission.objects.count()


def test_viewer_cannot_create_a_product(viewer_user, auth_client):
    """A read-only role is refused write access."""
    response = auth_client(viewer_user).post("/api/v1/stone-types/", {"name": "Nope"})

    assert response.status_code == 403


def test_viewer_can_read_products(viewer_user, auth_client):
    """A read-only role can still list."""
    StoneTypeFactory()
    response = auth_client(viewer_user).get("/api/v1/stone-types/")

    assert response.status_code == 200


def test_user_without_permissions_cannot_even_read(user, auth_client):
    """StrictModelPermissions closes DRF's default read-for-anyone hole."""
    StoneTypeFactory()
    response = auth_client(user).get("/api/v1/stone-types/")

    assert response.status_code == 403


def test_admin_can_create_a_stone_type(admin_user, auth_client):
    """A role with add_stonetype may create."""
    response = auth_client(admin_user).post(
        "/api/v1/stone-types/",
        {"name": "New Stone Type", "category": StoneCategoryFactory().pk},
    )

    assert response.status_code == 201, response.data


def test_protected_role_cannot_be_deleted(admin_user, auth_client, roles):
    """The superadmin role is the recovery path and must not be removable."""
    from django.contrib.auth.models import Group

    superadmin = Group.objects.get(name="superadmin")
    response = auth_client(admin_user).delete(f"/api/v1/roles/{superadmin.pk}/")

    assert response.status_code == 400
    assert Group.objects.filter(name="superadmin").exists()


def test_role_permissions_are_addressed_by_app_label_and_codename(
    roles, admin_user, auth_client
):
    """A role's permissions read and write as ``app_label.codename``.

    A bare codename is not unique - ``view_logentry`` exists in both ``admin``
    and ``auditlog`` - so addressing one without its app label would resolve to
    two rows and 500 the request.
    """
    from django.contrib.auth.models import Group, Permission

    duplicated = Permission.objects.filter(codename="view_logentry")
    assert duplicated.count() > 1, "expected the collision this test guards"

    role = Group.objects.create(name="auditor")
    client = auth_client(admin_user)

    response = client.patch(
        f"/api/v1/roles/{role.id}/",
        {"permissions": ["auditlog.view_logentry"]},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["permissions"] == ["auditlog.view_logentry"]

    granted = role.permissions.get()
    assert granted.content_type.app_label == "auditlog"


def test_editing_a_role_permission_set_leaves_its_name_alone(
    roles, admin_user, auth_client
):
    """The permission matrix sends only ``permissions``, and that is enough.

    It never shows the user a name, so it must not have to send one back - a
    full replace would either be rejected for the missing field or overwrite a
    name the screen never displayed.
    """
    from django.contrib.auth.models import Group

    role = Group.objects.create(name="auditor")
    client = auth_client(admin_user)

    response = client.patch(
        f"/api/v1/roles/{role.id}/",
        {"permissions": ["users.view_user"]},
        format="json",
    )

    assert response.status_code == 200
    role.refresh_from_db()
    assert role.name == "auditor"


def test_an_unknown_permission_label_is_rejected(roles, admin_user, auth_client):
    """A label that names nothing is a 400, not a crash."""
    from django.contrib.auth.models import Group

    role = Group.objects.create(name="auditor")
    client = auth_client(admin_user)

    response = client.patch(
        f"/api/v1/roles/{role.id}/",
        {"permissions": ["users.view_nothing"]},
        format="json",
    )

    assert response.status_code == 400
