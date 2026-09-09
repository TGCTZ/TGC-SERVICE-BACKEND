"""The whitelist filter backend."""

import pytest

from apps.gems.enums import StoneCategory
from apps.gems.models import StoneType
from apps.gems.tests.factories import (
    SpeciesFactory,
    StoneTypeFactory,
    VarietyFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def stone_types(db):
    """Three stone types with predictable names, prices and categories."""
    return [
        StoneTypeFactory(
            name="Alpha Ruby",
            price=100,
            category=StoneCategory.PRECIOUS,
            is_active=True,
        ),
        StoneTypeFactory(
            name="Beta Ruby",
            price=300,
            category=StoneCategory.SEMI_PRECIOUS,
            is_active=False,
        ),
        StoneTypeFactory(
            name="Gamma Garnet",
            price=200,
            category=StoneCategory.SEMI_PRECIOUS,
            is_active=False,
        ),
    ]


def _get(client, path="/api/v1/stone-types/", params=""):
    """Issue a list request and return the results array."""
    response = client.get(f"{path}{params}")
    assert response.status_code == 200, response.data
    return response.data["results"]


def test_search_matches_across_whitelisted_fields(stone_types, admin_user, auth_client):
    """Search matches case-insensitively across every whitelisted field."""
    client = auth_client(admin_user)
    results = _get(client, params="?search=ruby")

    assert {row["name"] for row in results} == {"Alpha Ruby", "Beta Ruby"}


def test_ordering_respects_the_whitelist(stone_types, admin_user, auth_client):
    """A whitelisted ordering is applied; an unknown one is ignored."""
    client = auth_client(admin_user)

    ascending = [row["name"] for row in _get(client, params="?ordering=price")]
    assert ascending == ["Alpha Ruby", "Gamma Garnet", "Beta Ruby"]

    descending = [row["name"] for row in _get(client, params="?ordering=-price")]
    assert descending == ["Beta Ruby", "Gamma Garnet", "Alpha Ruby"]


def test_ordering_by_a_non_whitelisted_field_is_ignored(
    stone_types, admin_user, auth_client
):
    """An un-whitelisted ordering falls back to the default rather than erroring."""
    client = auth_client(admin_user)
    results = _get(client, params="?ordering=description")

    assert len(results) == 3


def test_filter_exact_and_in(stone_types, admin_user, auth_client):
    """filter[field] does exact match; a comma-separated value does IN."""
    client = auth_client(admin_user)

    single = _get(client, params=f"?filter[category]={StoneCategory.SEMI_PRECIOUS}")
    assert len(single) == 2

    both = _get(
        client,
        params=(
            f"?filter[category]={StoneCategory.PRECIOUS},{StoneCategory.SEMI_PRECIOUS}"
        ),
    )
    assert len(both) == 3


def test_filter_on_a_foreign_key_id(admin_user, auth_client):
    """A numeric id filters as an id, not as a boolean.

    Regression test: coercing "1" by appearance rather than by field type reads
    ``filter[species]=1`` as ``species=True``, which matches nothing. Ids of 1
    and 0 are the most common ids there are, so the bug hides in exactly the
    rows most likely to be filtered.
    """
    corundum = SpeciesFactory(name="Corundum")
    beryl = SpeciesFactory(name="Beryl")
    VarietyFactory(name="Ruby", species=corundum)
    VarietyFactory(name="Sapphire", species=corundum)
    VarietyFactory(name="Emerald", species=beryl)

    client = auth_client(admin_user)

    single = _get(client, "/api/v1/varieties/", f"?filter[species]={corundum.pk}")
    assert {row["name"] for row in single} == {"Ruby", "Sapphire"}

    both = _get(
        client,
        "/api/v1/varieties/",
        f"?filter[species]={corundum.pk},{beryl.pk}",
    )
    assert len(both) == 3


def test_filter_coerces_booleans(stone_types, admin_user, auth_client):
    """A 'true'/'false' string is coerced to a real boolean."""
    client = auth_client(admin_user)

    assert len(_get(client, params="?filter[is_active]=true")) == 1
    assert len(_get(client, params="?filter[is_active]=false")) == 2


def test_pagination_caps_page_size(stone_types, admin_user, auth_client):
    """page_size is honoured, and the envelope is DRF's standard shape."""
    client = auth_client(admin_user)
    response = client.get("/api/v1/stone-types/?page_size=2")

    assert response.status_code == 200
    assert set(response.data) == {"count", "next", "previous", "results"}
    assert response.data["count"] == 3
    assert len(response.data["results"]) == 2


def test_with_trashed_and_only_trashed(stone_types, admin_user, auth_client):
    """Trashed rows are hidden by default and reachable on request."""
    client = auth_client(admin_user)
    StoneType.objects.filter(name="Alpha Ruby").first().delete()

    assert len(_get(client)) == 2
    assert len(_get(client, params="?with_trashed=1")) == 3
    assert len(_get(client, params="?only_trashed=1")) == 1
