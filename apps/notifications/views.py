"""The signed-in user's notification inbox."""

from collections import defaultdict

from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.db.models import Count, Q
from django.utils import timezone

from apps.core.filters import TRUE_VALUES

from .models import Notification
from .serializers import NotificationSerializer


def _path(link: str) -> str:
    """A link without its query string - the route a sidebar entry points at."""
    return link.split("?", 1)[0]


@extend_schema(
    parameters=[
        OpenApiParameter("unread", bool, description="Only unread notifications.")
    ]
)
class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """List and mark the current user's notifications.

    No model permission gates this: every user may read their own inbox, and
    the queryset is scoped to ``request.user``, so there is no one else's to
    reach. A foreign id is a 404, not a 403 - it does not confirm the row exists.
    """

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    filter_fields = ("kind",)
    ordering_fields = ("created_at",)
    ordering = ["-created_at"]

    def get_queryset(self):
        """The requesting user's notifications, optionally only unread ones."""
        queryset = Notification.objects.filter(recipient=self.request.user)
        unread = str(self.request.query_params.get("unread", "")).lower()
        if unread in TRUE_VALUES:
            queryset = queryset.filter(read_at__isnull=True)
        return queryset

    def _unread(self):
        return Notification.objects.filter(
            recipient=self.request.user, read_at__isnull=True
        )

    @extend_schema(
        responses=inline_serializer(
            "UnreadSummary",
            fields={
                "count": serializers.IntegerField(),
                "by_link": serializers.DictField(child=serializers.IntegerField()),
                "latest": NotificationSerializer(allow_null=True),
            },
        )
    )
    @action(detail=False, methods=["get"], url_path="unread-summary")
    def unread_summary(self, request):
        """Everything the client polls for, in one request.

        ``by_link`` counts unread notifications per route, query string
        dropped, so the sidebar can badge the entry each one points at.
        ``latest`` rides along so the arrival toast needs no second request -
        a follow-up fetch could race a mark-read and toast the wrong row.
        """
        unread = self._unread()
        by_link: dict[str, int] = defaultdict(int)
        count = 0
        for row in unread.values("link").annotate(n=Count("id")):
            count += row["n"]
            if path := _path(row["link"]):
                by_link[path] += row["n"]

        latest = unread.order_by("-created_at", "-id").first()
        return Response(
            {
                "count": count,
                "by_link": by_link,
                "latest": NotificationSerializer(latest).data if latest else None,
            }
        )

    @extend_schema(request=None, responses=NotificationSerializer)
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        """Mark one notification read. Idempotent: the first read time is kept."""
        notification = self.get_object()
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(self.get_serializer(notification).data)

    @extend_schema(
        request=inline_serializer(
            "ReadAllRequest", fields={"link": serializers.CharField(required=False)}
        ),
        responses=inline_serializer(
            "ReadAllResult", fields={"updated": serializers.IntegerField()}
        ),
    )
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        """Mark unread notifications read - all of them, or one route's.

        With ``link``, only notifications pointing at that route are marked,
        whatever their query string: opening a page is how its sidebar badge
        clears, and the page is the same page whichever order it was opened for.
        """
        unread = self._unread()
        if path := _path(str(request.data.get("link", ""))):
            unread = unread.filter(Q(link=path) | Q(link__startswith=f"{path}?"))
        updated = unread.update(read_at=timezone.now())
        return Response({"updated": updated})
