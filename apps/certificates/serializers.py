"""Serializers for the certificates domain."""

from rest_framework import serializers

from apps.core.serializers import AuditFieldsMixin

from .models import Certificate
from .selectors import instrument_checklist


class CertificateSerializer(AuditFieldsMixin):
    """A certificate as the lab sees it."""

    stone_label = serializers.CharField(source="stone.label", read_only=True)
    order_reference = serializers.CharField(
        source="stone.order.reference_number", read_only=True
    )
    customer_name = serializers.CharField(
        source="stone.order.customer.full_name", read_only=True
    )
    customer_phone = serializers.CharField(
        source="stone.order.customer.phone", read_only=True
    )
    report_number = serializers.CharField(source="report.report_number", read_only=True)
    issued_by_label = serializers.SerializerMethodField()
    # The lab's full instrument list with this certificate's ticks - the same
    # list the PDF prints, so the view dialog and the document agree.
    instrument_checklist = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = (
            "id",
            "stone",
            "stone_label",
            "order_reference",
            "customer_name",
            "customer_phone",
            "report",
            "report_number",
            "certificate_number",
            "stone_type_snapshot",
            "weight_snapshot",
            "weight_unit_snapshot",
            "color_snapshot",
            "origin_snapshot",
            "species_snapshot",
            "variety_snapshot",
            "shape_cut_snapshot",
            "transparency_snapshot",
            "optic_character_snapshot",
            "treatment_snapshot",
            "nature_type_snapshot",
            "refractive_index_snapshot",
            "specific_gravity_snapshot",
            "comments_snapshot",
            "instruments_snapshot",
            "instrument_checklist",
            "report_number_snapshot",
            "photo_snapshot",
            "gemmologist",
            "gemmologist_two",
            "status",
            "issued_by",
            "issued_by_label",
            "issued_at",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        # Everything but the stone is written by the issuing service: the number,
        # the snapshots and the status all have to be minted together or the
        # document does not mean anything.
        read_only_fields = tuple(f for f in fields if f != "stone")

    def get_instrument_checklist(self, obj) -> list[dict]:
        """Every active instrument, ticked where this certificate used it."""
        return instrument_checklist(obj)

    def get_issued_by_label(self, obj) -> str | None:
        """Who issued it, or None if unattributed."""
        return str(obj.issued_by) if obj.issued_by_id else None


class IssueCertificateSerializer(serializers.Serializer):
    """Payload for issuing a certificate."""

    stone = serializers.IntegerField()
