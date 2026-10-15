"""Process due GePG callbacks and outbound retries from PostgreSQL."""

from django.core.management.base import BaseCommand

from apps.billing.processing import process_due_gepg_work


class Command(BaseCommand):
    """Run one bounded pass over the GePG inbox and outbox."""

    help = "Process due GePG callbacks and retryable outbound requests."

    def handle(self, *args, **options):
        """Process due records and report the work completed."""
        result = process_due_gepg_work()
        self.stdout.write(
            "Processed {callbacks} callbacks and {outbound_requests} outbound "
            "requests; recovered {recovered_requests} stale outbound requests.".format(
                **result
            )
        )
