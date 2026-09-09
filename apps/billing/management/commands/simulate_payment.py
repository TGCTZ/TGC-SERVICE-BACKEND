"""Dev-only: simulate a GePG payment so a bill settles."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.billing.dev import simulate_payment
from apps.billing.models import Bill


class Command(BaseCommand):
    """Settle a bill by feeding a fake notification through the real handler.

    Exercises the whole payment path - parse, record, settle, transition - so a
    developer can walk an order through to certification without the gateway.
    """

    help = "Simulate a GePG payment for a bill (development only)."

    def add_arguments(self, parser):
        """Take the bill to settle, by its human-readable number."""
        parser.add_argument("bill_number", help="e.g. BILL-2026-0004")

    def handle(self, *args, **options):
        """Refuse outside DEBUG, then run the real notification handler."""
        if not settings.DEBUG:
            raise CommandError("simulate_payment is only allowed when DEBUG is on.")
        number = options["bill_number"]
        try:
            bill = Bill.objects.get(bill_number=number)
        except Bill.DoesNotExist:
            raise CommandError(f"No bill {number!r}.") from None
        simulate_payment(bill)
        self.stdout.write(
            self.style.SUCCESS(
                f"Settled {bill.bill_number} · status={bill.status} "
                f"· control={bill.control_number}"
            )
        )
