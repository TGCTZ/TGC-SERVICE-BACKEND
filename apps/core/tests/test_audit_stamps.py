"""Actor stamping via the current-user contextvar."""

import pytest

from apps.catalog.tests.factories import BrandFactory
from apps.core.current_user import reset_current_user, set_current_user
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_created_by_is_stamped_from_the_context():
    """A save inside a request context records who did it."""
    actor = UserFactory()
    token = set_current_user(actor)
    try:
        brand = BrandFactory()
    finally:
        reset_current_user(token)

    assert brand.created_by == actor
    assert brand.updated_by == actor


def test_partial_save_still_stamps_the_actor():
    """update_fields is widened so a partial save does not drop the stamp.

    A naive implementation computes updated_by and then hands Django an
    update_fields list that excludes it, silently discarding the write.
    """
    brand = BrandFactory()
    actor = UserFactory()

    token = set_current_user(actor)
    try:
        brand.name = "Renamed"
        brand.save(update_fields=["name"])
    finally:
        reset_current_user(token)

    brand.refresh_from_db()
    assert brand.name == "Renamed"
    assert brand.updated_by == actor


def test_no_actor_outside_a_request():
    """Saving with no current user leaves the actor columns null."""
    brand = BrandFactory()

    assert brand.created_by is None
    assert brand.updated_by is None


def test_soft_delete_stamps_deleted_by():
    """delete() records who removed the row."""
    brand = BrandFactory()
    actor = UserFactory()

    token = set_current_user(actor)
    try:
        brand.delete()
    finally:
        reset_current_user(token)

    brand.refresh_from_db()
    assert brand.deleted_by == actor
