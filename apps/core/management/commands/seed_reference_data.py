"""Create the shared reference data and code-defined roles for an environment."""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.gems.color_palette import sync_color_palette
from apps.gems.models import (
    StoneCategory,
    StoneType,
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

        sync_color_palette()

        call_command("sync_instruments", verbosity=0)

        for name in USER_STATUSES:
            UserStatus.objects.get_or_create(name=name)

        for name in GENDERS:
            Gender.objects.get_or_create(name=name)

        self.stdout.write(self.style.SUCCESS("Shared reference data is ready."))
