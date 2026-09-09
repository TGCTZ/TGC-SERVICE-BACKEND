"""URL routes for the gemmological reference tables."""

from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import (
    ColorViewSet,
    InstrumentViewSet,
    OriginViewSet,
    ShapeCutViewSet,
    SpeciesViewSet,
    StoneTypeViewSet,
    VarietyViewSet,
)

router = DefaultRouter()
router.register("stone-types", StoneTypeViewSet, basename="stonetype")
router.register("species", SpeciesViewSet, basename="species")
router.register("varieties", VarietyViewSet, basename="variety")
router.register("colors", ColorViewSet, basename="color")
router.register("origins", OriginViewSet, basename="origin")
router.register("shape-cuts", ShapeCutViewSet, basename="shapecut")
router.register("instruments", InstrumentViewSet, basename="instrument")

urlpatterns = [path("", include(router.urls))]
