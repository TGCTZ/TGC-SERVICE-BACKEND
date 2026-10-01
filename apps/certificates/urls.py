"""URL routes for the certificates domain."""

from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import CertificateViewSet

router = DefaultRouter()
router.register("certificates", CertificateViewSet, basename="certificate")

urlpatterns = [path("", include(router.urls))]
