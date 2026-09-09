"""Factories for the gemmological reference tables.

Reused by ``manage.py seed``, so the shapes here are the shapes a developer
sees on a freshly seeded database.
"""

import factory
from factory.django import DjangoModelFactory

from apps.gems.enums import ColorGroup, StoneCategory
from apps.gems.models import (
    Color,
    Instrument,
    Origin,
    ShapeCut,
    Species,
    StoneType,
    Variety,
)


class StoneTypeFactory(DjangoModelFactory):
    """A priced stone type."""

    class Meta:
        model = StoneType
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Stone type {n}")
    category = StoneCategory.PRECIOUS
    price = factory.Faker("pydecimal", left_digits=5, right_digits=2, positive=True)


class SpeciesFactory(DjangoModelFactory):
    """Gemmological species."""

    class Meta:
        model = Species
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Species {n}")


class VarietyFactory(DjangoModelFactory):
    """A variety under a species."""

    class Meta:
        model = Variety
        django_get_or_create = ("name", "species")

    name = factory.Sequence(lambda n: f"Variety {n}")
    species = factory.SubFactory(SpeciesFactory)


class ColorFactory(DjangoModelFactory):
    """A color in a broad family."""

    class Meta:
        model = Color
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Color {n}")
    group = ColorGroup.RED_PINK


class OriginFactory(DjangoModelFactory):
    """Geographic origin."""

    class Meta:
        model = Origin
        django_get_or_create = ("name",)

    name = factory.Faker("country")


class ShapeCutFactory(DjangoModelFactory):
    """Shape or cut."""

    class Meta:
        model = ShapeCut
        django_get_or_create = ("name",)

    name = factory.Iterator(["Round brilliant", "Oval", "Cushion", "Emerald", "Cabochon"])


class InstrumentFactory(DjangoModelFactory):
    """Lab instrument."""

    class Meta:
        model = Instrument
        django_get_or_create = ("name",)

    name = factory.Iterator(
        ["Refractometer", "Polariscope", "Dichroscope", "Spectroscope", "UV lamp"]
    )
