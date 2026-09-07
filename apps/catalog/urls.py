"""URL routes for the product domain."""

from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import (
    BrandViewSet,
    ProductCategoryViewSet,
    ProductImageViewSet,
    ProductStatusViewSet,
    ProductViewSet,
    TagViewSet,
    UnitOfMeasureViewSet,
)

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("product-images", ProductImageViewSet, basename="productimage")
router.register("product-categories", ProductCategoryViewSet, basename="productcategory")
router.register("brands", BrandViewSet, basename="brand")
router.register("product-statuses", ProductStatusViewSet, basename="productstatus")
router.register("unit-of-measures", UnitOfMeasureViewSet, basename="unitofmeasure")
router.register("tags", TagViewSet, basename="tag")

urlpatterns = [path("", include(router.urls))]
