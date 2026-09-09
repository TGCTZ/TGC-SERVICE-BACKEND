"""URL routes for the certificates domain."""

from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import CertificateAccessLogViewSet, CertificateViewSet

router = DefaultRouter()
router.register("certificates", CertificateViewSet, basename="certificate")
router.register(
    "certificate-access-logs",
    CertificateAccessLogViewSet,
    basename="certificateaccesslog",
)

urlpatterns = [path("", include(router.urls))]
