"""Actor stamping via the current-user contextvar."""

import pytest

from apps.core.current_user import reset_current_user, set_current_user
from apps.gems.tests.factories import SpeciesFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_created_by_is_stamped_from_the_context():
    """A save inside a request context records who did it."""
    actor = UserFactory()
    token = set_current_user(actor)
    try:
        species = SpeciesFactory()
    finally:
        reset_current_user(token)

    assert species.created_by == actor
    assert species.updated_by == actor


def test_partial_save_still_stamps_the_actor():
    """update_fields is widened so a partial save does not drop the stamp.

    A naive implementation computes updated_by and then hands Django an
    update_fields list that excludes it, silently discarding the write.
    """
    species = SpeciesFactory()
    actor = UserFactory()

    token = set_current_user(actor)
    try:
        species.name = "Renamed"
        species.save(update_fields=["name"])
    finally:
        reset_current_user(token)

    species.refresh_from_db()
    assert species.name == "Renamed"
    assert species.updated_by == actor


def test_no_actor_outside_a_request():
    """Saving with no current user leaves the actor columns null."""
    species = SpeciesFactory()

    assert species.created_by is None
    assert species.updated_by is None


def test_soft_delete_stamps_deleted_by():
    """delete() records who removed the row."""
    species = SpeciesFactory()
    actor = UserFactory()

    token = set_current_user(actor)
    try:
        species.delete()
    finally:
        reset_current_user(token)

    species.refresh_from_db()
    assert species.deleted_by == actor
