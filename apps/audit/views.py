"""Read-only audit APIs."""

from pathlib import Path

from auditlog.models import LogEntry
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings

from apps.core.permissions import StrictModelPermissions

from .serializers import ActivityLogSerializer, SystemLogEntrySerializer
from .services import read_log

LOG_PATH = Path(settings.BASE_DIR) / "logs" / "app.log"


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Browse the change history recorded by django-auditlog.

    Read-only by design: an audit trail that can be edited is not an audit trail.
    """

    queryset = LogEntry.objects.select_related("actor", "content_type").order_by(
        "-timestamp"
    )
    serializer_class = ActivityLogSerializer
    permission_classes = [StrictModelPermissions]

    search_fields = ("object_repr",)
    # ``content_type__model`` is whitelisted alongside the raw id so a client can
    # scope history to a model by name, which is what the API already reports as
    # ``subject_type``; requiring the ContentType id would mean a lookup call
    # before every history request.
    filter_fields = (
        "action",
        "actor",
        "content_type",
        "content_type__model",
        "object_pk",
    )
    ordering_fields = ("id", "timestamp", "action")
    ordering = ["-timestamp"]
    date_filter_fields = ("timestamp",)


class CanReadSystemLog(BasePermission):
    """Allows access only to users holding ``audit.view_systemlog``."""

    def has_permission(self, request, view):
        """True when the requester may read the application log."""
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_perm("audit.view_systemlog")
        )


class SystemLogView(APIView):
    """Read the tail of the application log file, with secrets redacted."""

    permission_classes = [CanReadSystemLog]
    serializer_class = SystemLogEntrySerializer

    @extend_schema(responses=SystemLogEntrySerializer(many=True))
    def get(self, request):
        """Return recent log entries, newest first."""
        entries = read_log(
            LOG_PATH,
            level=request.query_params.get("level"),
            search=request.query_params.get("search"),
        )
        return Response(SystemLogEntrySerializer(entries, many=True).data)


class SystemLogLevelsView(APIView):
    """List the log levels available for filtering."""

    permission_classes = [CanReadSystemLog]

    @extend_schema(responses={200: dict})
    def get(self, request):
        """Return the supported level names."""
        return Response({"levels": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]})
