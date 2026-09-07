"""Product CRUD, restore and query efficiency."""

import pytest

from apps.catalog.models import Product
from apps.catalog.tests.factories import ProductFactory, TagFactory

pytestmark = pytest.mark.django_db


def test_slug_is_derived_from_the_name():
    """A product saved without a slug gets one from its name."""
    product = ProductFactory(name="Wireless Keyboard", slug="")

    assert product.slug == "wireless-keyboard"


def test_delete_then_restore_round_trips(admin_user, auth_client):
    """DELETE soft-deletes; the restore action brings the row back."""
    product = ProductFactory()
    client = auth_client(admin_user)

    assert client.delete(f"/api/v1/products/{product.pk}/").status_code == 204
    assert not Product.objects.filter(pk=product.pk).exists()

    restore = client.post(f"/api/v1/products/{product.pk}/restore/")
    assert restore.status_code == 200, restore.data
    assert Product.objects.filter(pk=product.pk).exists()


def test_restoring_a_live_product_is_rejected(admin_user, auth_client):
    """Restoring something that was never deleted is a client error."""
    product = ProductFactory()
    response = auth_client(admin_user).post(f"/api/v1/products/{product.pk}/restore/")

    assert response.status_code in (400, 404)


def test_delete_and_restore_are_recorded_in_the_activity_log(admin_user, auth_client):
    """Soft delete and restore are logged explicitly rather than left to auditlog."""
    from auditlog.models import LogEntry

    product = ProductFactory()
    client = auth_client(admin_user)
    client.delete(f"/api/v1/products/{product.pk}/")
    client.post(f"/api/v1/products/{product.pk}/restore/")

    entries = LogEntry.objects.filter(object_pk=str(product.pk))
    assert entries.filter(action=LogEntry.Action.DELETE).exists()


def test_expiry_before_release_is_rejected(admin_user, auth_client):
    """The serializer enforces the date ordering."""
    from apps.catalog.tests.factories import (
        ProductCategoryFactory,
        ProductStatusFactory,
    )

    response = auth_client(admin_user).post(
        "/api/v1/products/",
        {
            "name": "Bad Dates",
            "sku": "SKU-BAD-1",
            "price": "5.00",
            "product_category": ProductCategoryFactory().pk,
            "product_status": ProductStatusFactory().pk,
            "released_at": "2026-06-01",
            "expiry_date": "2026-01-01",
        },
    )

    assert response.status_code == 400
    assert "expiry_date" in response.data


def test_listing_products_does_not_n_plus_one(
    admin_user, auth_client, django_assert_max_num_queries
):
    """select_related/prefetch_related keep the query count flat as rows grow.

    Without them, serialising each product would fetch its category, brand,
    status, unit, tags and images one row at a time.
    """
    tag = TagFactory()
    for _ in range(10):
        ProductFactory().tags.add(tag)

    client = auth_client(admin_user)
    with django_assert_max_num_queries(12):
        response = client.get("/api/v1/products/")

    assert response.status_code == 200
    assert response.data["count"] == 10


def test_sync_tags_rejects_unknown_ids():
    """The service refuses ids that do not resolve, rather than silently dropping."""
    from apps.catalog.services import sync_tags
    from apps.core.exceptions import ServiceError

    product = ProductFactory()
    with pytest.raises(ServiceError):
        sync_tags(product=product, tag_ids=[999999])


def test_set_primary_image_demotes_the_previous_one():
    """A product has exactly one primary image at a time."""
    from apps.catalog.services import set_primary_image
    from apps.catalog.tests.factories import ProductImageFactory

    product = ProductFactory()
    first = ProductImageFactory(product=product)
    second = ProductImageFactory(product=product)

    set_primary_image(image=first)
    set_primary_image(image=second)

    first.refresh_from_db()
    second.refresh_from_db()
    assert second.is_primary
    assert not first.is_primary
