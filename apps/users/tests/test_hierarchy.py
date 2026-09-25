"""The role hierarchy: superadmin > admin > manager > the stations.

Everyone manages only roles, and the people holding them, ranked strictly below
their own highest role - and does not see the ranks above theirs at all. Their
own level stays visible, locked. ``admin_user`` in conftest is a *manager*; the
admin role's holder here is ``admin_role_user``.
"""

import pytest

from django.contrib.auth.models import Group

from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _holding(role: str):
    account = UserFactory()
    account.groups.add(Group.objects.get(name=role))
    return account


@pytest.fixture
def superadmin_user(roles):
    """A user holding the top role."""
    return _holding("superadmin")


@pytest.fixture
def admin_role_user(roles):
    """A user holding the admin role - not conftest's ``admin_user``."""
    return _holding("admin")


def _new_user(**overrides):
    return {
        "first_name": "New",
        "last_name": "Person",
        "username": "newperson",
        "email": "newperson@example.com",
        **overrides,
    }


def _role_names(client) -> set[str]:
    return {row["name"] for row in client.get("/api/v1/roles/").data["results"]}


def _user_ids(client) -> set[int]:
    return {row["id"] for row in client.get("/api/v1/users/").data["results"]}


# -------------------------------------------------------------- the role ---


def test_admin_holds_every_permission_superadmin_does(roles):
    """All permissions by default, resolved the same way as superadmin's."""
    admin = Group.objects.get(name="admin")
    superadmin = Group.objects.get(name="superadmin")

    assert set(admin.permissions.all()) == set(superadmin.permissions.all())


def test_only_a_superadmin_can_change_the_admin_role(
    auth_client, admin_user, admin_role_user, superadmin_user
):
    """Hidden from managers, locked to its own holders, editable from the top."""
    admin = Group.objects.get(name="admin")
    url = f"/api/v1/roles/{admin.pk}/"
    narrower = {"permissions": ["users.view_user"]}

    assert auth_client(admin_user).patch(url, narrower, format="json").status_code == 404
    admin_client = auth_client(admin_role_user)
    assert admin_client.patch(url, narrower, format="json").status_code == 403
    assert admin_client.delete(url).status_code == 403

    response = auth_client(superadmin_user).patch(url, narrower, format="json")
    assert response.status_code == 200
    assert response.data["permissions"] == ["users.view_user"]


def test_superadmin_stays_protected_even_from_a_superadmin(auth_client, superadmin_user):
    """The break-glass role is fixed by setup_roles, never by the API."""
    superadmin = Group.objects.get(name="superadmin")

    response = auth_client(superadmin_user).delete(f"/api/v1/roles/{superadmin.pk}/")

    assert response.status_code == 400


def test_admin_manages_the_manager_role_that_managers_no_longer_can(
    auth_client, admin_user, admin_role_user
):
    """A manager could otherwise widen their own role; now the rank above does it."""
    manager = Group.objects.get(name="manager")
    url = f"/api/v1/roles/{manager.pk}/"
    unchanged = {
        "permissions": sorted(
            f"{p.content_type.app_label}.{p.codename}" for p in manager.permissions.all()
        )
    }

    assert auth_client(admin_user).patch(url, unchanged, format="json").status_code == 403
    assert (
        auth_client(admin_role_user).patch(url, unchanged, format="json").status_code
        == 200
    )


def test_a_role_cannot_gain_a_permission_its_editor_lacks(auth_client, admin_user):
    """Otherwise a manager could build a role above themselves and hand it out."""
    response = auth_client(admin_user).post(
        "/api/v1/roles/",
        {"name": "helper", "permissions": ["auth.delete_permission"]},
        format="json",
    )

    assert response.status_code == 403
    assert not Group.objects.filter(name="helper").exists()


# ---------------------------------------------------------------- hidden ---


def test_an_admin_never_learns_that_superadmin_exists(
    auth_client, admin_role_user, superadmin_user
):
    """Not in the roles list, not in the users list, not even through an error."""
    client = auth_client(admin_role_user)
    superadmin = Group.objects.get(name="superadmin")

    assert "superadmin" not in _role_names(client)
    assert {"admin", "manager"} <= _role_names(client)
    assert superadmin_user.pk not in _user_ids(client)
    assert client.get(f"/api/v1/roles/{superadmin.pk}/").status_code == 404
    assert client.get(f"/api/v1/users/{superadmin_user.pk}/").status_code == 404

    # Probing by name gets the answers a name that does not exist would get.
    created = client.post("/api/v1/roles/", {"name": "superadmin"}, format="json")
    assert created.status_code == 400
    assert "already exists" not in str(created.data)
    assigned = client.post(
        "/api/v1/users/", _new_user(roles=["superadmin"]), format="json"
    )
    assert assigned.status_code == 400
    assert "does not exist" in str(assigned.data)


def test_a_manager_sees_neither_admins_nor_superadmins(
    auth_client, admin_user, admin_role_user, superadmin_user
):
    """Their own level stays in view: they hold it."""
    client = auth_client(admin_user)

    assert {"admin", "superadmin"}.isdisjoint(_role_names(client))
    assert "manager" in _role_names(client)
    assert {admin_role_user.pk, superadmin_user.pk}.isdisjoint(_user_ids(client))


def test_a_django_superuser_is_hidden_like_a_superadmin(auth_client, admin_role_user):
    """A superuser is the top rank, whatever groups it has."""
    superuser = UserFactory(is_superuser=True)

    assert superuser.pk not in _user_ids(auth_client(admin_role_user))


# -------------------------------------------------------------- assigning ---


@pytest.mark.parametrize(
    ("role", "status"),
    # Roles above are unknown to a manager (400); their own is refused (403).
    [("superadmin", 400), ("admin", 400), ("manager", 403), ("receptionist", 201)],
)
def test_a_manager_hands_out_only_roles_below_manager(
    auth_client, admin_user, role, status
):
    """Strictly below: not even the manager role itself."""
    response = auth_client(admin_user).post(
        "/api/v1/users/", _new_user(roles=[role]), format="json"
    )

    assert response.status_code == status, response.data


def test_only_a_superadmin_makes_admins(auth_client, admin_role_user, superadmin_user):
    """An admin cannot create peers; the level above decides who joins it."""
    target = _holding("receptionist")
    url = f"/api/v1/users/{target.pk}/roles/"

    assert (
        auth_client(admin_role_user)
        .put(url, {"roles": ["admin"]}, format="json")
        .status_code
        == 403
    )
    assert (
        auth_client(superadmin_user)
        .put(url, {"roles": ["admin"]}, format="json")
        .status_code
        == 200
    )
    assert target.groups.filter(name="admin").exists()


def test_no_one_can_promote_themselves(auth_client, admin_user):
    """Editing your own account is allowed; raising it is not."""
    client = auth_client(admin_user)
    url = f"/api/v1/users/{admin_user.pk}/"

    assert client.patch(url, {"first_name": "Renamed"}, format="json").status_code == 200
    # "admin" is not a role a manager can see, so it is simply unknown.
    assert (
        client.patch(url, {"roles": ["manager", "admin"]}, format="json").status_code
        == 400
    )
    assert (
        client.put(f"{url}roles/", {"roles": ["admin"]}, format="json").status_code == 400
    )
    assert set(admin_user.groups.values_list("name", flat=True)) == {"manager"}


# ------------------------------------------------------------------ people ---


def test_no_one_can_edit_or_delete_a_superior_or_a_peer(
    auth_client, admin_user, admin_role_user, superadmin_user
):
    """Superiors are out of sight (404); peers are in sight but locked (403)."""
    manager_client = auth_client(admin_user)
    admin_url = f"/api/v1/users/{admin_role_user.pk}/"
    assert (
        manager_client.patch(admin_url, {"first_name": "X"}, format="json").status_code
        == 404
    )
    assert manager_client.delete(admin_url).status_code == 404

    peer = _holding("manager")
    peer_url = f"/api/v1/users/{peer.pk}/"
    assert (
        manager_client.patch(peer_url, {"first_name": "X"}, format="json").status_code
        == 403
    )

    admin_client = auth_client(admin_role_user)
    assert (
        admin_client.patch(
            f"/api/v1/users/{superadmin_user.pk}/", {"first_name": "X"}, format="json"
        ).status_code
        == 404
    )
    assert (
        admin_client.patch(peer_url, {"first_name": "X"}, format="json").status_code
        == 200
    )


def test_the_api_tells_the_screens_what_the_requester_may_do(auth_client, admin_user):
    """The roles and users screens lock what the API would refuse."""
    client = auth_client(admin_user)

    roles = {row["name"]: row for row in client.get("/api/v1/roles/").data["results"]}
    assert (roles["manager"]["can_manage"], roles["manager"]["can_assign"]) == (
        False,
        False,
    )
    assert (roles["receptionist"]["can_manage"], roles["receptionist"]["can_assign"]) == (
        True,
        True,
    )

    peer = _holding("manager")
    peer_row = client.get(f"/api/v1/users/{peer.pk}/").data
    own_row = client.get(f"/api/v1/users/{admin_user.pk}/").data
    assert (peer_row["can_manage"], own_row["can_manage"]) == (False, True)
