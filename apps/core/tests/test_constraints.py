"""The soft-delete-aware unique constraint on ReferenceModel."""

import pytest

from django.db import IntegrityError

from apps.gems.models import Species
from apps.gems.tests.factories import SpeciesFactory

pytestmark = pytest.mark.django_db


def test_live_names_must_be_unique():
    """Two live rows cannot share a name."""
    SpeciesFactory(name="Acme")
    with pytest.raises(IntegrityError):
        Species.objects.create(name="Acme")


def test_deleted_name_can_be_reused():
    """A soft-deleted row must not hold its name hostage.

    This is the whole reason the constraint is partial rather than a plain
    unique=True: without the condition, deleting "Acme" would permanently
    prevent anyone from creating another species by that name.
    """
    original = SpeciesFactory(name="Acme")
    original.delete()

    replacement = Species.objects.create(name="Acme")

    assert replacement.pk != original.pk
    assert Species.objects.filter(name="Acme").count() == 1
