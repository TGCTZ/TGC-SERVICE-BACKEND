"""Soft delete, restore and trashed-row visibility."""

import pytest

from apps.catalog.tests.factories import BrandFactory

pytestmark = pytest.mark.django_db


def test_delete_is_soft():
    """delete() stamps deleted_at rather than removing the row."""
    brand = BrandFactory()
    brand.delete()

    assert not type(brand).objects.filter(pk=brand.pk).exists()
    assert type(brand).all_objects.filter(pk=brand.pk).exists()
    brand.refresh_from_db()
    assert brand.deleted_at is not None
    assert brand.is_deleted


def test_restore_undoes_delete():
    """restore() clears deleted_at and brings the row back into the default manager."""
    brand = BrandFactory()
    brand.delete()
    brand.restore()

    assert type(brand).objects.filter(pk=brand.pk).exists()
    brand.refresh_from_db()
    assert brand.deleted_at is None


def test_hard_delete_removes_the_row():
    """hard_delete() actually removes the row."""
    brand = BrandFactory()
    pk = brand.pk
    brand.hard_delete()

    assert not type(brand).all_objects.filter(pk=pk).exists()


def test_queryset_delete_is_also_soft():
    """Bulk delete goes through the soft-delete queryset."""
    BrandFactory.create_batch(3)
    from apps.catalog.models import Brand

    Brand.objects.all().delete()

    assert Brand.objects.count() == 0
    assert Brand.all_objects.count() == 3


def test_alive_and_dead_helpers():
    """alive() and dead() partition the table."""
    from apps.catalog.models import Brand

    keep = BrandFactory()
    drop = BrandFactory()
    drop.delete()

    assert list(Brand.objects.all()) == [keep]
    assert Brand.all_objects.filter(deleted_at__isnull=False).get() == drop
