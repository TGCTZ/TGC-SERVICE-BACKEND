"""URL routes for the notification inbox."""

from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import NotificationViewSet

router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = [
    path("", include(router.urls)),
]
