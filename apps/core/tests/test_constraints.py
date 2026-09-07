"""The soft-delete-aware unique constraint on ReferenceModel."""

import pytest

from django.db import IntegrityError

from apps.catalog.models import Brand
from apps.catalog.tests.factories import BrandFactory

pytestmark = pytest.mark.django_db


def test_live_names_must_be_unique():
    """Two live rows cannot share a name."""
    BrandFactory(name="Acme")
    with pytest.raises(IntegrityError):
        Brand.objects.create(name="Acme")


def test_deleted_name_can_be_reused():
    """A soft-deleted row must not hold its name hostage.

    This is the whole reason the constraint is partial rather than a plain
    unique=True: without the condition, deleting "Acme" would permanently
    prevent anyone from creating another brand by that name.
    """
    original = BrandFactory(name="Acme")
    original.delete()

    replacement = Brand.objects.create(name="Acme")

    assert replacement.pk != original.pk
    assert Brand.objects.filter(name="Acme").count() == 1
