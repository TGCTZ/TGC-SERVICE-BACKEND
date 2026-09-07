"""Abstract base for admin-managed lookup tables."""

from django.db import models
from django.db.models import Q

from .base import BaseModel


class ReferenceModel(BaseModel):
    """Shared shape for simple name-based lookups."""

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ["name"]
        constraints = [
            # Unique among live rows only. A plain unique=True would let a
            # soft-deleted row block its own name from ever being reused.
            models.UniqueConstraint(
                fields=["name"],
                condition=Q(deleted_at__isnull=True),
                name="%(app_label)s_%(class)s_unique_name",
            ),
        ]

    def __str__(self) -> str:
        return self.name
