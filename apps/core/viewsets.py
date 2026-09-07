"""Base ViewSet supplying soft delete, restore and trashed-row access."""

from auditlog.models import LogEntry
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from django.utils import timezone

from apps.core.filters import TRUE_VALUES
from apps.core.permissions import StrictModelPermissions


class SoftDeleteViewSetMixin:
    """Soft-delete semantics for a ViewSet over a ``BaseModel`` subclass.

    Adds two query parameters to list and detail routes - ``with_trashed=1`` and
    ``only_trashed=1`` - and a ``POST {id}/restore/`` action.

    Trashed handling lives here rather than in the filter backend because
    switching managers has to happen before the view applies its own
    ``select_related``/``prefetch_related``, which the backend never sees.
    """

    def get_queryset(self):
        """Return the view's queryset, widened to trashed rows when asked."""
        queryset = super().get_queryset()
        params = getattr(self.request, "query_params", {})
        only_trashed = str(params.get("only_trashed", "")).lower() in TRUE_VALUES
        with_trashed = str(params.get("with_trashed", "")).lower() in TRUE_VALUES

        # The restore action must be able to find a row that list views hide.
        if self.action == "restore":
            only_trashed = True

        if only_trashed:
            return queryset.model.all_objects.filter(
                deleted_at__isnull=False,
                pk__in=queryset.model.all_objects.values("pk"),
            )
        if with_trashed:
            return queryset.model.all_objects.all()
        return queryset

    def perform_destroy(self, instance):
        """Soft-delete the instance and record it explicitly in the audit log."""
        instance.delete()
        self._log(instance, LogEntry.Action.DELETE)

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        """Undo a soft delete and return the restored representation."""
        instance = self.get_object()
        if not instance.is_deleted:
            return Response(
                {"detail": "This record is not deleted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.restore()
        self._log(instance, LogEntry.Action.UPDATE, restored=True)
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def _log(self, instance, action_type, *, restored: bool = False):
        """Write an explicit audit entry for a soft delete or restore.

        django-auditlog sees a soft delete as an ordinary UPDATE, since no row
        is removed, so delete and restore would otherwise be indistinguishable
        from any other field change in the history.
        """
        changes = (
            {"deleted_at": [str(timezone.now()), None]}
            if restored
            else {"deleted_at": [None, str(instance.deleted_at)]}
        )
        LogEntry.objects.log_create(
            instance,
            action=action_type,
            changes=changes,
        )


class BaseModelViewSet(SoftDeleteViewSetMixin):
    """Shared defaults for every CRUD ViewSet in the project.

    Concrete ViewSets combine this with ``ModelViewSet`` and declare the four
    whitelists read by ``WhitelistFilterBackend``: ``search_fields``,
    ``filter_fields``, ``ordering_fields`` and ``date_filter_fields``.
    """

    permission_classes = [StrictModelPermissions]
    ordering = ["-id"]

    search_fields: tuple = ()
    filter_fields: tuple = ()
    ordering_fields: tuple = ()
    date_filter_fields: tuple = ("created_at", "updated_at")
