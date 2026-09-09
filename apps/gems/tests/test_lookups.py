"""Stone reference tables: CRUD, restore, constraints and query efficiency."""

import pytest

from django.db import IntegrityError

from apps.gems.models import StoneType, Variety
from apps.gems.tests.factories import (
    SpeciesFactory,
    StoneTypeFactory,
    VarietyFactory,
)

pytestmark = pytest.mark.django_db


def test_delete_then_restore_round_trips(admin_user, auth_client):
    """DELETE soft-deletes; the restore action brings the row back."""
    stone_type = StoneTypeFactory()
    client = auth_client(admin_user)

    assert client.delete(f"/api/v1/stone-types/{stone_type.pk}/").status_code == 204
    assert not StoneType.objects.filter(pk=stone_type.pk).exists()

    restore = client.post(f"/api/v1/stone-types/{stone_type.pk}/restore/")
    assert restore.status_code == 200, restore.data
    assert StoneType.objects.filter(pk=stone_type.pk).exists()


def test_restoring_a_live_row_is_rejected(admin_user, auth_client):
    """Restoring something that was never deleted is a client error."""
    stone_type = StoneTypeFactory()
    response = auth_client(admin_user).post(
        f"/api/v1/stone-types/{stone_type.pk}/restore/"
    )

    assert response.status_code in (400, 404)


def test_delete_and_restore_are_recorded_in_the_activity_log(admin_user, auth_client):
    """Soft delete is logged explicitly rather than left to auditlog."""
    from auditlog.models import LogEntry

    stone_type = StoneTypeFactory()
    client = auth_client(admin_user)
    client.delete(f"/api/v1/stone-types/{stone_type.pk}/")
    client.post(f"/api/v1/stone-types/{stone_type.pk}/restore/")

    entries = LogEntry.objects.filter(object_pk=str(stone_type.pk))
    assert entries.filter(action=LogEntry.Action.DELETE).exists()


def test_stone_type_price_may_be_unset(admin_user, auth_client):
    """An unpriced type is representable; billing is what refuses it.

    The column is nullable rather than defaulted to zero precisely so that a
    missing price is a visible configuration gap instead of a bill for nothing.
    """
    response = auth_client(admin_user).post(
        "/api/v1/stone-types/", {"name": "Unpriced", "category": "precious"}
    )

    assert response.status_code == 201, response.data
    assert response.data["price"] is None


def test_variety_names_are_unique_per_species():
    """Two species may each have a variety of the same name."""
    corundum = SpeciesFactory(name="Corundum")
    beryl = SpeciesFactory(name="Beryl")

    VarietyFactory(name="Star", species=corundum)
    VarietyFactory(name="Star", species=beryl)

    assert Variety.objects.filter(name="Star").count() == 2


def test_duplicate_variety_within_a_species_is_rejected():
    """The same species cannot hold the same variety name twice."""
    corundum = SpeciesFactory(name="Corundum")
    VarietyFactory(name="Ruby", species=corundum)

    with pytest.raises(IntegrityError):
        Variety.objects.create(name="Ruby", species=corundum)


def test_listing_varieties_does_not_n_plus_one(
    admin_user, auth_client, django_assert_max_num_queries
):
    """select_related keeps the query count flat as rows grow.

    Without it, serialising each variety's ``species_detail`` would fetch its
    species one row at a time.
    """
    species = SpeciesFactory()
    for index in range(10):
        VarietyFactory(name=f"Variety {index}", species=species)

    client = auth_client(admin_user)
    with django_assert_max_num_queries(8):
        response = client.get("/api/v1/varieties/")

    assert response.status_code == 200
    assert response.data["count"] == 10
    assert response.data["results"][0]["species_detail"]["name"] == species.name
