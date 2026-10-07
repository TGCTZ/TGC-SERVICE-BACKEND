"""Synchronize the active lab instrument checklist."""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.gems.instrument_list import INSTRUMENTS
from apps.gems.models import Instrument


class Command(BaseCommand):
    """Keep exactly the canonical instruments active without deleting history."""

    help = "Synchronize the canonical active lab instrument list."

    @transaction.atomic
    def handle(self, *args, **options):
        """Create/reactivate canonical rows and deactivate every other live row."""
        for name in INSTRUMENTS:
            instrument, _ = Instrument.objects.get_or_create(
                name=name, defaults={"is_active": True}
            )
            if not instrument.is_active:
                instrument.is_active = True
                instrument.save(update_fields=["is_active", "updated_at"])

        retired = Instrument.objects.filter(is_active=True).exclude(name__in=INSTRUMENTS)
        for instrument in retired.iterator():
            instrument.is_active = False
            instrument.save(update_fields=["is_active", "updated_at"])

        self.stdout.write(self.style.SUCCESS("Lab instruments synchronized."))
