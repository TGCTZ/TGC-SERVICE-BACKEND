"""GePG service provider configuration."""

from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class ServiceProvider(BaseModel):
    """A GePG service provider the system bills through."""

    sp_code = models.CharField(max_length=20)
    name = models.CharField(max_length=255)
    group_code = models.CharField(max_length=20, blank=True, default="")
    sys_code = models.CharField(max_length=20, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["sp_code"],
                condition=Q(deleted_at__isnull=True),
                name="%(app_label)s_%(class)s_unique_sp_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.sp_code})"
