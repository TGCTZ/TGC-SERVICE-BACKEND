"""Role-based access control."""

import pytest

from apps.catalog.tests.factories import ProductFactory

pytestmark = pytest.mark.django_db


def test_setup_roles_creates_every_role(roles):
    """The management command materialises the whole role matrix."""
    from django.contrib.auth.models import Group

    from apps.users.roles import ROLE_PERMISSIONS

    assert set(Group.objects.values_list("name", flat=True)) == set(ROLE_PERMISSIONS)


def test_superadmin_gets_every_permission(roles):
    """The superadmin role resolves dynamically, so new models are covered."""
    from django.contrib.auth.models import Group, Permission

    superadmin = Group.objects.get(name="superadmin")

    assert superadmin.permissions.count() == Permission.objects.count()


def test_viewer_cannot_create_a_product(viewer_user, auth_client):
    """A read-only role is refused write access."""
    response = auth_client(viewer_user).post("/api/v1/products/", {"name": "Nope"})

    assert response.status_code == 403


def test_viewer_can_read_products(viewer_user, auth_client):
    """A read-only role can still list."""
    ProductFactory()
    response = auth_client(viewer_user).get("/api/v1/products/")

    assert response.status_code == 200


def test_user_without_permissions_cannot_even_read(user, auth_client):
    """StrictModelPermissions closes DRF's default read-for-anyone hole."""
    ProductFactory()
    response = auth_client(user).get("/api/v1/products/")

    assert response.status_code == 403


def test_admin_can_create_a_product(admin_user, auth_client):
    """A role with add_product may create."""
    from apps.catalog.tests.factories import (
        ProductCategoryFactory,
        ProductStatusFactory,
    )

    response = auth_client(admin_user).post(
        "/api/v1/products/",
        {
            "name": "New Product",
            "sku": "SKU-NEW-1",
            "price": "19.99",
            "product_category": ProductCategoryFactory().pk,
            "product_status": ProductStatusFactory().pk,
        },
    )

    assert response.status_code == 201, response.data


def test_protected_role_cannot_be_deleted(admin_user, auth_client, roles):
    """The superadmin role is the recovery path and must not be removable."""
    from django.contrib.auth.models import Group

    superadmin = Group.objects.get(name="superadmin")
    response = auth_client(admin_user).delete(f"/api/v1/roles/{superadmin.pk}/")

    assert response.status_code == 400
    assert Group.objects.filter(name="superadmin").exists()
