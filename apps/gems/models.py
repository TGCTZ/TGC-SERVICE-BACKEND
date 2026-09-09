"""Gemmological reference tables.

All seven inherit ``ReferenceModel``, so they share a name, description, active
flag, soft delete and the partial unique constraint that lets a deleted name be
reused.
"""

from django.db import models
from django.db.models import Q

from apps.core.models import ReferenceModel

from .enums import ColorGroup, StoneCategory


class StoneType(ReferenceModel):
    """A type of stone (e.g. ruby, sapphire), and what the lab charges for one.

    ``price`` is the flat fee for identifying a stone of this type, independent
    of weight. It is nullable rather than defaulted to zero: an unpriced type is
    a configuration gap that billing must refuse, and a zero default would
    silently issue a bill for nothing.
    """

    category = models.CharField(max_length=20, choices=StoneCategory.choices)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)


class Species(ReferenceModel):
    """Gemmological species."""

    class Meta(ReferenceModel.Meta):
        verbose_name_plural = "species"


class Variety(ReferenceModel):
    """A variety within a species."""

    species = models.ForeignKey(
        Species, on_delete=models.PROTECT, related_name="varieties"
    )

    class Meta(ReferenceModel.Meta):
        verbose_name_plural = "varieties"
        # Deliberately replaces the parent's unique-name constraint rather than
        # extending it: a variety name is only unique within its species, and
        # two species may legitimately share one.
        constraints = [
            models.UniqueConstraint(
                fields=["name", "species"],
                condition=Q(deleted_at__isnull=True),
                name="%(app_label)s_%(class)s_unique_name_species",
            ),
        ]


class Color(ReferenceModel):
    """Observed stone color, filed under a broad color family."""

    group = models.CharField(max_length=20, choices=ColorGroup.choices)


class Origin(ReferenceModel):
    """Geographic origin of a stone."""


class ShapeCut(ReferenceModel):
    """Shape or cut of a stone."""


class Instrument(ReferenceModel):
    """Lab instrument used during identification."""
