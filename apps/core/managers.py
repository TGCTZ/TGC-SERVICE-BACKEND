"""Soft-delete queryset and manager.

Rows are never physically removed by ordinary code paths. ``delete()`` stamps
``deleted_at`` instead. The default manager hides soft-deleted rows;
``all_objects`` exposes them.
"""

from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet whose bulk ``delete`` is soft; ``hard_delete`` removes for real."""

    def delete(self):
        """Soft-delete every matched row in a single UPDATE.

        ``deleted_by`` is left alone: a bulk update has no single acting user,
        so the service layer sets it where that attribution is needed.
        """
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        """Permanently remove matched rows. Admin and maintenance only."""
        return super().delete()

    def alive(self):
        """Rows that are not soft-deleted."""
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        """Rows that are soft-deleted."""
        return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager):
    """Default manager: returns live (non-deleted) rows only."""

    def get_queryset(self):
        """Base queryset filtered to live rows."""
        return SoftDeleteQuerySet(self.model, using=self._db).alive()
