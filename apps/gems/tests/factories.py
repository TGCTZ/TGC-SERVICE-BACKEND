"""Factories for the gemmological reference tables.

Reused by ``manage.py seed``, so the shapes here are the shapes a developer
sees on a freshly seeded database.
"""

import factory
from factory.django import DjangoModelFactory

from apps.gems.enums import ColorGroup
from apps.gems.models import (
    Color,
    Instrument,
    Origin,
    ShapeCut,
    Species,
    StoneCategory,
    StoneType,
    Variety,
)


class StoneCategoryFactory(DjangoModelFactory):
    """A pricing tier.

    Unpriced by default, which is the state billing must refuse. A test that
    bills something says so by passing a price.
    """

    class Meta:
        model = StoneCategory
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Tier {n}")
    price = None


class StoneTypeFactory(DjangoModelFactory):
    """A stone type, priced through its tier.

    ``price=`` is accepted here and pushed down onto the category, because the
    fee lives on the tier now but a test reads far better saying what a stone
    costs than assembling a category first. Each type gets its own tier, so one
    test's price cannot leak into another's.
    """

    class Meta:
        model = StoneType
        django_get_or_create = ("name",)
        # The price hook saves the category, never the type itself.
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"Stone type {n}")
    category = factory.SubFactory(StoneCategoryFactory)

    @factory.post_generation
    def price(self, create, extracted, **kwargs):
        """Apply a ``price=`` kwarg to the tier, where the fee actually lives.

        Only when one was given: an omitted price must leave a tier passed in by
        the caller alone, and a fresh ``StoneCategoryFactory`` is unpriced
        already.
        """
        if create and extracted is not None:
            self.category.price = extracted
            self.category.save(update_fields=["price"])


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
