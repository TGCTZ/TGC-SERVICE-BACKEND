"""Serializers for the certificates domain."""

from rest_framework import serializers

from apps.core.serializers import AuditFieldsMixin

from .models import Certificate, CertificateAccessLog


class CertificateSerializer(AuditFieldsMixin):
    """A certificate as the lab sees it."""

    stone_label = serializers.CharField(source="stone.label", read_only=True)
    order_reference = serializers.CharField(
        source="stone.order.reference_number", read_only=True
    )
    customer_name = serializers.CharField(
        source="stone.order.customer.full_name", read_only=True
    )
    report_number = serializers.CharField(source="report.report_number", read_only=True)
    issued_by_label = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = (
            "id",
            "stone",
            "stone_label",
            "order_reference",
            "customer_name",
            "report",
            "report_number",
            "certificate_number",
            "verification_token",
            "stone_type_snapshot",
            "weight_snapshot",
            "color_snapshot",
            "origin_snapshot",
            "gemmologist",
            "qr_code",
            "pdf_file",
            "status",
            "issued_by",
            "issued_by_label",
            "issued_at",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        # Everything but the stone is written by the issuing service: the number,
        # the token, the snapshots and the status all have to be minted together
        # or the document does not mean anything.
        read_only_fields = tuple(f for f in fields if f != "stone")

    def get_issued_by_label(self, obj) -> str | None:
        """Who issued it, or None if unattributed."""
        return str(obj.issued_by) if obj.issued_by_id else None


class PublicCertificateSerializer(serializers.ModelSerializer):
    """What an anonymous verifier is allowed to see.

    Deliberately narrow. The point of the public endpoint is to answer "is this
    document genuine, and does it still stand" - not to expose the customer, the
    order, or the audit trail to anyone holding a token.
    """

    is_valid = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = (
            "certificate_number",
            "status",
            "is_valid",
            "issued_at",
            "stone_type_snapshot",
            "weight_snapshot",
            "color_snapshot",
            "origin_snapshot",
            "gemmologist",
        )
        read_only_fields = fields

    def get_is_valid(self, obj) -> bool:
        """A revoked certificate resolves, but does not stand."""
        from apps.gems.enums import CertificateStatus

        return obj.status != CertificateStatus.REVOKED


class CertificateAccessLogSerializer(serializers.ModelSerializer):
    """One public verification hit."""

    class Meta:
        model = CertificateAccessLog
        fields = ("id", "certificate", "accessed_at", "ip_address", "user_agent")
        read_only_fields = fields


class IssueCertificateSerializer(serializers.Serializer):
    """Payload for issuing a certificate."""

    stone = serializers.IntegerField()
