"""Synchronize the active identification color palette."""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.gems.color_palette import sync_color_palette


class Command(BaseCommand):
    """Make the database color lookup match the canonical palette."""

    help = "Synchronize the canonical identification color palette."

    @transaction.atomic
    def handle(self, *args, **options):
        """Synchronize the palette in one transaction."""
        sync_color_palette()
        self.stdout.write(self.style.SUCCESS("Identification colors synchronized."))
