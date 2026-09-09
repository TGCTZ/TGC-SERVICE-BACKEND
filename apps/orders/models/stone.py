"""Stone (order line item) and its status audit trail."""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.gems.enums import StoneStatus, WeightUnit

from .order import Order


class Stone(BaseModel):
    """An individual stone in an order, progressing through the pipeline."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="stones")
    label = models.CharField(max_length=20)
    stone_type = models.ForeignKey(
        "gems.StoneType", on_delete=models.PROTECT, related_name="stones"
    )
    weight = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    weight_unit = models.CharField(
        max_length=10, choices=WeightUnit.choices, default=WeightUnit.CARAT
    )
    status = models.CharField(
        max_length=20, choices=StoneStatus.choices, default=StoneStatus.RECEIVED
    )

    class Meta:
        ordering = ["order", "label"]
        indexes = [models.Index(fields=["status"])]
        permissions = [("transition_stone", "Can change a stone's status")]

    def __str__(self) -> str:
        return f"{self.order.reference_number} / {self.label}"


class StatusHistory(models.Model):
    """Append-only record of a stone's status transitions.

    Deliberately a plain ``models.Model`` rather than a ``BaseModel``: this is
    the ledger, so it is never edited and never deleted, and a soft-deletable
    audit trail would be a contradiction. It follows that it carries no audit
    columns of its own and is not registered with django-auditlog - logging the
    log would be circular.
    """

    stone = models.ForeignKey(
        Stone, on_delete=models.CASCADE, related_name="status_history"
    )
    # Blank on the first entry, where the stone came from nowhere.
    from_status = models.CharField(
        max_length=20, choices=StoneStatus.choices, blank=True, default=""
    )
    to_status = models.CharField(max_length=20, choices=StoneStatus.choices)
    # Null when the gateway made the change: a payment callback has no user.
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["stone", "changed_at"]
        indexes = [models.Index(fields=["stone", "changed_at"])]
        verbose_name_plural = "status history"

    def __str__(self) -> str:
        return f"{self.stone}: {self.from_status or '-'} -> {self.to_status}"
