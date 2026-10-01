"""Order grouping the stones a customer submits in one visit."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.gems.enums import OrderHold

from .customer import Customer


class Order(BaseModel):
    """A batch of stones received from a customer.

    The order carries no *pipeline* status: progress is per-stone, because two
    stones from the same visit can sit at different stages - one certified while
    another is still on the bench. Where an order has got to is derived by
    :func:`apps.orders.selectors.order_stage`, which reports its least advanced
    stone, and so can never drift out of step with reality.

    What it does carry is ``hold_status``: whether somebody has paused or
    withdrawn the whole visit. That is the one thing no stone can tell you - a
    customer asking the lab to stop is a fact about the order, not about any
    stone in it - so it is the one thing stored rather than derived.
    """

    reference_number = models.CharField(max_length=30)
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="orders"
    )
    received_date = models.DateField()
    stone_count = models.PositiveIntegerField(
        default=0, help_text="Number of stones the customer submitted."
    )

    # A decision about the whole visit. Everything else about where an order
    # stands is derived from its stones; this cannot be.
    hold_status = models.CharField(
        max_length=20, choices=OrderHold.choices, default=OrderHold.ACTIVE
    )
    # Why, in the words of whoever decided it. Blank while active.
    hold_reason = models.TextField(blank=True, default="")
    held_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    held_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_date"]
        permissions = [("hold_order", "Can hold or cancel an order")]
        constraints = [
            models.UniqueConstraint(
                fields=["reference_number"],
                condition=Q(deleted_at__isnull=True),
                name="%(app_label)s_%(class)s_unique_reference_number",
            ),
        ]

    @property
    def identified_count(self) -> int:
        """How many of the submitted stones have been identified so far."""
        return self.stones.count()

    @property
    def is_held(self) -> bool:
        """Whether work on this order has been paused or stopped."""
        return self.hold_status != OrderHold.ACTIVE

    def __str__(self) -> str:
        return self.reference_number
