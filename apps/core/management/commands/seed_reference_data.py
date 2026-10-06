"""Create the shared reference data and code-defined roles for an environment."""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

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
from apps.users.models import Gender, UserStatus

# The lab's pricing tiers and flat identification fees, in TZS.
STONE_CATEGORIES = (
    ("Precious", 30_000),
    ("Semi-precious", 10_000),
    ("Diamond", 40_000),
)

STONE_TYPES = (
    ("Ruby", "Precious"),
    ("Sapphire", "Precious"),
    ("Emerald", "Precious"),
    ("Diamond", "Diamond"),
    ("Tanzanite", "Semi-precious"),
    ("Garnet", "Semi-precious"),
    ("Tourmaline", "Semi-precious"),
    ("Spinel", "Semi-precious"),
)

SPECIES_VARIETIES = {
    "Corundum": ("Ruby", "Blue sapphire", "Padparadscha"),
    "Beryl": ("Emerald", "Aquamarine", "Morganite"),
    "Zoisite": ("Tanzanite",),
    "Quartz": ("Amethyst", "Citrine"),
}

COLORS = (
    ("Red", ColorGroup.RED_PINK),
    ("Pink", ColorGroup.RED_PINK),
    ("Blue", ColorGroup.BLUE),
    ("Green", ColorGroup.GREEN),
    ("Yellow", ColorGroup.ORANGE_YELLOW),
    ("Colourless", ColorGroup.WHITE_GREY_BLACK),
    ("Violet", ColorGroup.PURPLE_VIOLET),
)

ORIGINS = ("Tanzania", "Madagascar", "Sri Lanka", "Myanmar", "Mozambique")
SHAPE_CUTS = ("Round brilliant", "Oval", "Cushion", "Emerald", "Cabochon")
INSTRUMENTS = ("Refractometer", "Polariscope", "Dichroscope", "Spectroscope", "UV lamp")
USER_STATUSES = ("Active", "Suspended", "Pending", "Archived")
GENDERS = ("Female", "Male", "Non-binary", "Prefer not to say")


class Command(BaseCommand):
    """Ensure shared lookups exist without overwriting environment edits."""

    help = "Create shared reference data and synchronize code-defined roles."

    @transaction.atomic
    def handle(self, *args, **options):
        """Run reference and role setup as one transaction."""
        call_command("setup_roles", verbosity=0)

        categories = {}
        for name, price in STONE_CATEGORIES:
            category, _ = StoneCategory.objects.get_or_create(
                name=name, defaults={"price": price}
            )
            categories[name] = category

        for name, category_name in STONE_TYPES:
            StoneType.objects.get_or_create(
                name=name, defaults={"category": categories[category_name]}
            )

        for species_name, variety_names in SPECIES_VARIETIES.items():
            species, _ = Species.objects.get_or_create(name=species_name)
            for variety_name in variety_names:
                Variety.objects.get_or_create(
                    name=variety_name, species=species
                )

        for name, group in COLORS:
            Color.objects.get_or_create(name=name, defaults={"group": group})

        for name in ORIGINS:
            Origin.objects.get_or_create(name=name)

        for name in SHAPE_CUTS:
            ShapeCut.objects.get_or_create(name=name)

        for name in INSTRUMENTS:
            Instrument.objects.get_or_create(name=name)

        for name in USER_STATUSES:
            UserStatus.objects.get_or_create(name=name)

        for name in GENDERS:
            Gender.objects.get_or_create(name=name)

        self.stdout.write(self.style.SUCCESS("Shared reference data is ready."))
