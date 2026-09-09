"""Customer who brings stones for identification."""

from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class Customer(BaseModel):
    """A person or company that submits orders."""

    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, default="")
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, default="")
    company_name = models.CharField(max_length=255, blank=True, default="")
    region = models.CharField(max_length=100, blank=True, default="")
    id_number = models.CharField(max_length=50, blank=True, default="")
    address = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["first_name", "last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["phone"],
                condition=Q(deleted_at__isnull=True),
                name="%(app_label)s_%(class)s_unique_phone",
            ),
        ]

    @property
    def full_name(self) -> str:
        """First, middle, and last name joined, skipping blanks."""
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(part for part in parts if part)

    def __str__(self) -> str:
        return self.full_name
