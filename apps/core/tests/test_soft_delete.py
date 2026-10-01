"""Soft delete, restore and trashed-row visibility."""

import pytest

from apps.gems.tests.factories import SpeciesFactory

pytestmark = pytest.mark.django_db


def test_delete_is_soft():
    """delete() stamps deleted_at rather than removing the row."""
    species = SpeciesFactory()
    species.delete()

    assert not type(species).objects.filter(pk=species.pk).exists()
    assert type(species).all_objects.filter(pk=species.pk).exists()
    species.refresh_from_db()
    assert species.deleted_at is not None
    assert species.is_deleted


def test_restore_undoes_delete():
    """restore() clears deleted_at and brings the row back into the default manager."""
    species = SpeciesFactory()
    species.delete()
    species.restore()

    assert type(species).objects.filter(pk=species.pk).exists()
    species.refresh_from_db()
    assert species.deleted_at is None


def test_hard_delete_removes_the_row():
    """hard_delete() actually removes the row."""
    species = SpeciesFactory()
    pk = species.pk
    species.hard_delete()

    assert not type(species).all_objects.filter(pk=pk).exists()


def test_queryset_delete_is_also_soft():
    """Bulk delete goes through the soft-delete queryset."""
    SpeciesFactory.create_batch(3)
    from apps.gems.models import Species

    Species.objects.all().delete()

    assert Species.objects.count() == 0
    assert Species.all_objects.count() == 3


def test_alive_and_dead_helpers():
    """alive() and dead() partition the table."""
    from apps.gems.models import Species

    keep = SpeciesFactory()
    drop = SpeciesFactory()
    drop.delete()

    assert list(Species.objects.all()) == [keep]
    assert Species.all_objects.filter(deleted_at__isnull=False).get() == drop
