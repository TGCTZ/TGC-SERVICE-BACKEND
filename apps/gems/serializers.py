"""Serializers for the gemmological reference tables."""

from apps.core.serializers import AuditFieldsMixin

from .models import (
    Color,
    Instrument,
    Origin,
    ShapeCut,
    Species,
    StoneType,
    Variety,
)


class ReferenceSerializer(AuditFieldsMixin):
    """Shared shape for the stone lookup tables."""

    class Meta:
        fields = (
            "id",
            "name",
            "description",
            "is_active",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        read_only_fields = AuditFieldsMixin.AUDIT_FIELDS


class StoneTypeSerializer(ReferenceSerializer):
    """Stone types, with the category and the flat identification fee."""

    class Meta(ReferenceSerializer.Meta):
        model = StoneType
        fields = (*ReferenceSerializer.Meta.fields, "category", "price")


class SpeciesSerializer(ReferenceSerializer):
    """Gemmological species."""

    class Meta(ReferenceSerializer.Meta):
        model = Species


class VarietySerializer(ReferenceSerializer):
    """Varieties, including the species they belong to."""

    species_detail = SpeciesSerializer(source="species", read_only=True)

    class Meta(ReferenceSerializer.Meta):
        model = Variety
        fields = (*ReferenceSerializer.Meta.fields, "species", "species_detail")


class ColorSerializer(ReferenceSerializer):
    """Colors, filed under a broad color family."""

    class Meta(ReferenceSerializer.Meta):
        model = Color
        fields = (*ReferenceSerializer.Meta.fields, "group")


class OriginSerializer(ReferenceSerializer):
    """Geographic origins."""

    class Meta(ReferenceSerializer.Meta):
        model = Origin


class ShapeCutSerializer(ReferenceSerializer):
    """Shapes and cuts."""

    class Meta(ReferenceSerializer.Meta):
        model = ShapeCut


class InstrumentSerializer(ReferenceSerializer):
    """Lab instruments."""

    class Meta(ReferenceSerializer.Meta):
        model = Instrument
