"""Tanzania's regions, and reading hand-typed text as one of them."""

import importlib

import pytest

from django.apps import apps as installed_apps

from apps.gems.enums import Region
from apps.gems.regions import normalize_region
from apps.orders.models import Customer
from apps.orders.tests.factories import CustomerFactory


def test_there_are_thirty_one_regions():
    """26 on the mainland and 5 in Zanzibar, as of Songwe in 2016."""
    assert len(Region.choices) == 31
    assert Region.SONGWE.label == "Songwe"


@pytest.mark.parametrize(
    ("typed", "region"),
    [
        ("Arusha", Region.ARUSHA),
        ("  arusha region ", Region.ARUSHA),
        ("Mkoa wa Dodoma", Region.DODOMA),
        ("Dar-es-Salaam", Region.DAR_ES_SALAAM),
        ("DSM", Region.DAR_ES_SALAAM),
        ("Coast", Region.PWANI),
        ("Pemba North", Region.KASKAZINI_PEMBA),
        ("Zanzibar Urban West", Region.MJINI_MAGHARIBI),
        ("mjini_magharibi", Region.MJINI_MAGHARIBI),
    ],
)
def test_hand_typed_regions_are_read_as_the_region_meant(typed, region):
    """Case, spacing, punctuation, "region"/"mkoa wa" and English names all match."""
    assert normalize_region(typed) == region


@pytest.mark.parametrize("typed", ["", None, "Zanzibar", "Hoffmanview", "Arushaa"])
def test_text_naming_no_region_clearly_is_not_guessed(typed):
    """Plain "Zanzibar" could be five regions; a town or typo is none."""
    assert normalize_region(typed) is None


@pytest.mark.django_db
def test_the_migration_converts_what_it_can_read_and_keeps_the_rest():
    """Readable text becomes a region value; the rest is left for a person."""
    migration = importlib.import_module(
        "apps.orders.migrations.0004_customer_region_choices"
    )
    readable = CustomerFactory(region="arusha region")
    unclear = CustomerFactory(region="Hoffmanview")
    deleted = CustomerFactory(region="Coast")
    deleted.delete()

    migration.normalize_regions(installed_apps, None)

    assert Customer.all_objects.get(pk=readable.pk).region == Region.ARUSHA
    assert Customer.all_objects.get(pk=unclear.pk).region == "Hoffmanview"
    assert Customer.all_objects.get(pk=deleted.pk).region == Region.PWANI


@pytest.mark.django_db
def test_the_api_takes_region_values_only(auth_client, admin_user):
    """The dropdown sends values; a typed label is refused, so none creep back in."""
    client = auth_client(admin_user)
    payload = {"first_name": "Asha", "last_name": "Juma", "phone": "255700000001"}

    assert (
        client.post("/api/v1/customers/", {**payload, "region": "Arusha"}).status_code
        == 400
    )
    created = client.post("/api/v1/customers/", {**payload, "region": "arusha"})
    assert created.status_code == 201, created.data
    assert created.data["region"] == "arusha"
