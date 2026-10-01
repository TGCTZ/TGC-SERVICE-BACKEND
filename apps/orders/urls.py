"""URL routes for the order domain."""

from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import (
    CustomerViewSet,
    OrderViewSet,
    StatusHistoryViewSet,
    StoneViewSet,
)

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("orders", OrderViewSet, basename="order")
router.register("stones", StoneViewSet, basename="stone")
router.register("status-history", StatusHistoryViewSet, basename="statushistory")

urlpatterns = [path("", include(router.urls))]
