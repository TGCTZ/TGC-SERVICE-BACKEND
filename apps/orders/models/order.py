"""Order grouping the stones a customer submits in one visit."""

from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

from .customer import Customer


class Order(BaseModel):
    """A batch of stones received from a customer.

    The order itself carries no status: progress is per-stone, because two
    stones from the same visit can sit at different stages - one certified while
    another is still on the bench.
    """

    reference_number = models.CharField(max_length=30)
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="orders"
    )
    received_date = models.DateField()
    stone_count = models.PositiveIntegerField(
        default=0, help_text="Number of stones the customer submitted."
    )

    class Meta:
        ordering = ["-received_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["reference_number"],
                condition=Q(deleted_at__isnull=True),
                name="%(app_label)s_%(class)s_unique_reference_number",
            ),
        ]

    @property
    def identified_count(self) -> int:
        """How many of the submitted stones have been registered so far."""
        return self.stones.count()

    def __str__(self) -> str:
        return self.reference_number
