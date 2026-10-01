"""URL routes for the identification domain."""

from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import IdentificationReportViewSet, InstrumentUsedViewSet

router = DefaultRouter()
router.register(
    "identification-reports", IdentificationReportViewSet, basename="identificationreport"
)
router.register("instruments-used", InstrumentUsedViewSet, basename="instrumentused")

urlpatterns = [path("", include(router.urls))]
