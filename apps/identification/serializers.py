"""Serializers for the identification domain."""

from rest_framework import serializers

from apps.core.serializers import AuditFieldsMixin
from apps.gems.enums import WeightUnit
from apps.gems.serializers import (
    ColorSerializer,
    InstrumentSerializer,
    OriginSerializer,
    ShapeCutSerializer,
    SpeciesSerializer,
    VarietySerializer,
)

from .models import IdentificationReport, InstrumentUsed


class InstrumentUsedSerializer(AuditFieldsMixin):
    """An instrument used during a report, with its reading."""

    instrument_detail = InstrumentSerializer(source="instrument", read_only=True)

    class Meta:
        model = InstrumentUsed
        fields = (
            "id",
            "report",
            "instrument",
            "instrument_detail",
            "reading",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        read_only_fields = AuditFieldsMixin.AUDIT_FIELDS


class IdentificationReportSerializer(AuditFieldsMixin):
    """A gemmologist's findings for one stone."""

    species_detail = SpeciesSerializer(source="species", read_only=True)
    variety_detail = VarietySerializer(source="variety", read_only=True)
    origin_detail = OriginSerializer(source="origin", read_only=True)
    shape_cut_detail = ShapeCutSerializer(source="shape_cut", read_only=True)
    color_detail = ColorSerializer(source="color", read_only=True)
    instruments_used = InstrumentUsedSerializer(many=True, read_only=True)

    stone_label = serializers.CharField(source="stone.label", read_only=True)
    order_reference = serializers.CharField(
        source="stone.order.reference_number", read_only=True
    )
    identified_by_label = serializers.SerializerMethodField()

    # Weight is measured at the bench alongside the dimensions, so it belongs on
    # this form - but it lives on the Stone, which is what the certificate
    # snapshots. It travels through here and the service hands it on. Read back
    # under stone_* so the form seeds itself in one request.
    stone_weight = serializers.DecimalField(
        source="stone.weight", max_digits=10, decimal_places=3, read_only=True
    )
    stone_weight_unit = serializers.CharField(source="stone.weight_unit", read_only=True)
    weight = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        allow_null=True,
        write_only=True,
    )
    # No default, deliberately: a default lands in validated_data on every
    # request, so a PATCH of the conclusion alone would write to the stone.
    weight_unit = serializers.ChoiceField(
        choices=WeightUnit.choices, required=False, write_only=True
    )

    class Meta:
        model = IdentificationReport
        fields = (
            "id",
            "stone",
            "stone_label",
            "order_reference",
            "report_number",
            "species",
            "species_detail",
            "variety",
            "variety_detail",
            "origin",
            "origin_detail",
            "shape_cut",
            "shape_cut_detail",
            "color",
            "color_detail",
            "nature_type",
            "transparency",
            "treatment",
            "optic_character",
            "dimensions",
            "refractive_index",
            "specific_gravity",
            "weight",
            "weight_unit",
            "stone_weight",
            "stone_weight_unit",
            "is_polished",
            "conclusion",
            "instruments_used",
            "is_finalized",
            "identified_by",
            "identified_by_label",
            "identified_at",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        # The workflow fields move only through the finalize action, and the
        # report number is allocated by the service.
        read_only_fields = (
            *AuditFieldsMixin.AUDIT_FIELDS,
            "report_number",
            "is_finalized",
            "identified_by",
            "identified_at",
        )

    def get_identified_by_label(self, obj) -> str | None:
        """The gemmologist's display name, or None if unattributed."""
        return str(obj.identified_by) if obj.identified_by_id else None
