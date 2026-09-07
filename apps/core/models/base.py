"""Abstract base model: audit columns plus soft delete.

Every CRUD model in the project inherits this. Actor columns are stamped
automatically from the contextvar set by ``CurrentUserMiddleware``, so callers
do not have to pass the request user down into the model layer.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.current_user import get_current_user
from apps.core.managers import SoftDeleteManager


class BaseModel(models.Model):
    """Abstract base with audit columns and soft delete."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",  # actor links are never queried backwards
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = SoftDeleteManager()  # live rows only (default manager)
    all_objects = models.Manager()  # includes soft-deleted, for admin and audit

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        """True if the row is soft-deleted."""
        return self.deleted_at is not None

    def save(self, *args, **kwargs):
        """Stamp ``created_by``/``updated_by`` from the current request user.

        When the caller passes ``update_fields``, the stamped columns are added
        to it. Without that, a partial save would compute the new actor and then
        silently decline to write it.
        """
        user = get_current_user()
        if user is not None:
            is_new = self._state.adding
            if is_new and self.created_by_id is None:
                self.created_by = user
            self.updated_by = user
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("updated_by")
                if is_new:
                    update_fields.add("created_by")
                kwargs["update_fields"] = update_fields
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        """Soft delete: stamp ``deleted_at`` and ``deleted_by`` instead of removing."""
        self.deleted_at = timezone.now()
        user = get_current_user()
        if user is not None:
            self.deleted_by = user
        self.save(using=using, update_fields=["deleted_at", "deleted_by", "updated_at"])

    def hard_delete(self, using=None, keep_parents=False):
        """Permanently remove the row. Admin and maintenance only."""
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        """Undo a soft delete."""
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["deleted_at", "deleted_by", "updated_at"])
