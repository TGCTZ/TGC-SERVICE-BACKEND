"""URL routes for the audit read APIs."""

from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import ActivityLogViewSet, SystemLogLevelsView, SystemLogView

router = DefaultRouter()
router.register("activity-logs", ActivityLogViewSet, basename="activitylog")

urlpatterns = [
    path("system-logs/", SystemLogView.as_view(), name="system-logs"),
    path("system-logs/levels/", SystemLogLevelsView.as_view(), name="system-log-levels"),
    path("", include(router.urls)),
]
