"""URL routes for the billing domain."""

from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import (
    BillItemViewSet,
    BillViewSet,
    PaymentViewSet,
    ServiceProviderViewSet,
)

router = DefaultRouter()
router.register("bills", BillViewSet, basename="bill")
router.register("bill-items", BillItemViewSet, basename="billitem")
router.register("payments", PaymentViewSet, basename="payment")
router.register("service-providers", ServiceProviderViewSet, basename="serviceprovider")

urlpatterns = [path("", include(router.urls))]
