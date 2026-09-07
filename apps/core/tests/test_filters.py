"""The whitelist filter backend."""

import pytest

from apps.catalog.models import Product
from apps.catalog.tests.factories import BrandFactory, ProductFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def products(db):
    """Three products with predictable names, prices and brands."""
    cheap_brand = BrandFactory(name="Cheap")
    lux_brand = BrandFactory(name="Lux")
    return [
        ProductFactory(
            name="Alpha Laptop", price=100, brand=cheap_brand, is_featured=True
        ),
        ProductFactory(name="Beta Laptop", price=300, brand=lux_brand, is_featured=False),
        ProductFactory(name="Gamma Phone", price=200, brand=lux_brand, is_featured=False),
    ]


def _get(client, params=""):
    """Issue a list request and return the results array."""
    response = client.get(f"/api/v1/products/{params}")
    assert response.status_code == 200, response.data
    return response.data["results"]


def test_search_matches_across_whitelisted_fields(products, admin_user, auth_client):
    """Search matches case-insensitively across every whitelisted field."""
    client = auth_client(admin_user)
    results = _get(client, "?search=laptop")

    assert {row["name"] for row in results} == {"Alpha Laptop", "Beta Laptop"}


def test_ordering_respects_the_whitelist(products, admin_user, auth_client):
    """A whitelisted ordering is applied; an unknown one is ignored."""
    client = auth_client(admin_user)

    ascending = [row["name"] for row in _get(client, "?ordering=price")]
    assert ascending == ["Alpha Laptop", "Gamma Phone", "Beta Laptop"]

    descending = [row["name"] for row in _get(client, "?ordering=-price")]
    assert descending == ["Beta Laptop", "Gamma Phone", "Alpha Laptop"]


def test_ordering_by_a_non_whitelisted_field_is_ignored(
    products, admin_user, auth_client
):
    """An un-whitelisted ordering falls back to the default rather than erroring."""
    client = auth_client(admin_user)
    results = _get(client, "?ordering=cost_price")

    assert len(results) == 3


def test_filter_exact_and_in(products, admin_user, auth_client):
    """filter[field] does exact match; a comma-separated value does IN."""
    client = auth_client(admin_user)
    lux = products[1].brand

    single = _get(client, f"?filter[brand]={lux.pk}")
    assert len(single) == 2

    both = _get(client, f"?filter[brand]={products[0].brand.pk},{lux.pk}")
    assert len(both) == 3


def test_filter_coerces_booleans(products, admin_user, auth_client):
    """A 'true'/'false' string is coerced to a real boolean."""
    client = auth_client(admin_user)

    assert len(_get(client, "?filter[is_featured]=true")) == 1
    assert len(_get(client, "?filter[is_featured]=false")) == 2


def test_pagination_caps_page_size(products, admin_user, auth_client):
    """page_size is honoured, and the envelope is DRF's standard shape."""
    client = auth_client(admin_user)
    response = client.get("/api/v1/products/?page_size=2")

    assert response.status_code == 200
    assert set(response.data) == {"count", "next", "previous", "results"}
    assert response.data["count"] == 3
    assert len(response.data["results"]) == 2


def test_with_trashed_and_only_trashed(products, admin_user, auth_client):
    """Trashed rows are hidden by default and reachable on request."""
    client = auth_client(admin_user)
    Product.objects.filter(name="Alpha Laptop").first().delete()

    assert len(_get(client, "")) == 2
    assert len(_get(client, "?with_trashed=1")) == 3
    assert len(_get(client, "?only_trashed=1")) == 1
