"""API views for the gemmological reference tables."""

from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet

from .models import (
    Color,
    Instrument,
    Origin,
    ShapeCut,
    Species,
    StoneType,
    Variety,
)
from .serializers import (
    ColorSerializer,
    InstrumentSerializer,
    OriginSerializer,
    ShapeCutSerializer,
    SpeciesSerializer,
    StoneTypeSerializer,
    VarietySerializer,
)


class StoneTypeViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over stone types."""

    queryset = StoneType.objects.all()
    serializer_class = StoneTypeSerializer
    search_fields = ("name", "description")
    filter_fields = ("is_active", "category")
    ordering_fields = ("id", "name", "category", "price", "is_active", "created_at")


class SpeciesViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over species."""

    queryset = Species.objects.all()
    serializer_class = SpeciesSerializer
    search_fields = ("name", "description")
    filter_fields = ("is_active",)
    ordering_fields = ("id", "name", "is_active", "created_at")


class VarietyViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over varieties."""

    # Every row serialises its species, so join it rather than fetching one per
    # row.
    queryset = Variety.objects.select_related("species")
    serializer_class = VarietySerializer
    search_fields = ("name", "description", "species__name")
    filter_fields = ("is_active", "species")
    ordering_fields = ("id", "name", "is_active", "created_at")


class ColorViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over colors."""

    queryset = Color.objects.all()
    serializer_class = ColorSerializer
    search_fields = ("name", "description")
    filter_fields = ("is_active", "group")
    ordering_fields = ("id", "name", "group", "is_active", "created_at")


class OriginViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over origins."""

    queryset = Origin.objects.all()
    serializer_class = OriginSerializer
    search_fields = ("name", "description")
    filter_fields = ("is_active",)
    ordering_fields = ("id", "name", "is_active", "created_at")


class ShapeCutViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over shapes and cuts."""

    queryset = ShapeCut.objects.all()
    serializer_class = ShapeCutSerializer
    search_fields = ("name", "description")
    filter_fields = ("is_active",)
    ordering_fields = ("id", "name", "is_active", "created_at")


class InstrumentViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over lab instruments."""

    queryset = Instrument.objects.all()
    serializer_class = InstrumentSerializer
    search_fields = ("name", "description")
    filter_fields = ("is_active",)
    ordering_fields = ("id", "name", "is_active", "created_at")
