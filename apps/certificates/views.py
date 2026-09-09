"""API views for the certificates domain."""

from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.permissions import StrictModelPermissions
from apps.core.viewsets import BaseModelViewSet
from apps.orders.models import Stone
from apps.orders.serializers import StoneSerializer

from .models import Certificate, CertificateAccessLog
from .selectors import certificate_by_token, certification_worklist
from .serializers import (
    CertificateAccessLogSerializer,
    CertificateSerializer,
    IssueCertificateSerializer,
    PublicCertificateSerializer,
)
from .services import issue_certificate, revoke_certificate


class CertificateViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """Certificates, plus issuance, revocation and public verification."""

    queryset = Certificate.objects.select_related(
        "stone",
        "stone__order",
        "stone__order__customer",
        "stone__stone_type",
        "report",
        "issued_by",
    )
    serializer_class = CertificateSerializer

    search_fields = (
        "certificate_number",
        "stone_type_snapshot",
        "gemmologist",
        "stone__order__reference_number",
        "stone__order__customer__first_name",
        "stone__order__customer__last_name",
    )
    filter_fields = ("status", "stone", "report", "issued_by")
    ordering_fields = ("id", "certificate_number", "status", "issued_at", "created_at")
    date_filter_fields = ("created_at", "updated_at", "issued_at")

    action_permissions = {
        "create": ["certificates.issue_certificate"],
        "revoke": ["certificates.revoke_certificate"],
        "worklist": ["certificates.issue_certificate"],
        # The public endpoint carries its own AllowAny, but the map still has to
        # name it or the parent would ask for view_certificate.
        "verify": [],
    }

    def get_permissions(self):
        """The verification endpoint is public; everything else is not."""
        if self.action == "verify":
            return [AllowAny()]
        return super().get_permissions()

    @extend_schema(request=IssueCertificateSerializer, responses=CertificateSerializer)
    def create(self, request, *args, **kwargs):
        """Issue a certificate for a stone.

        Delegates wholly to the service: the number, token and snapshots are
        minted together, so there is nothing here for a client to supply beyond
        which stone to certify.
        """
        payload = IssueCertificateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        stone = Stone.objects.filter(pk=payload.validated_data["stone"]).first()
        if stone is None:
            return Response(
                {"detail": "Stone not found."}, status=status.HTTP_404_NOT_FOUND
            )

        certificate = issue_certificate(stone, user=request.user)
        return Response(
            self.get_serializer(certificate).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(request=None, responses=CertificateSerializer)
    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        """Withdraw this certificate."""
        certificate = revoke_certificate(self.get_object(), user=request.user)
        return Response(self.get_serializer(certificate).data)

    @extend_schema(responses=StoneSerializer)
    @action(detail=False, methods=["get"])
    def worklist(self, request):
        """Stones with a finalized report and a paid bill, not yet certified."""
        queryset = certification_worklist()
        page = self.paginate_queryset(queryset)
        serializer = StoneSerializer(
            page, many=True, context=self.get_serializer_context()
        )
        return self.get_paginated_response(serializer.data)

    @extend_schema(responses=PublicCertificateSerializer)
    @action(
        detail=False,
        methods=["get"],
        url_path=r"verify/(?P<token>[0-9a-f]{64})",
        authentication_classes=[],
    )
    def verify(self, request, token=None):
        """Confirm a certificate from its token. Public, and logged.

        Anyone holding the printed certificate can check it, so there is no
        authentication. Every hit is recorded, because who checked a certificate
        and when is itself part of the audit trail.
        """
        certificate = certificate_by_token(token)
        if certificate is None:
            return Response(
                {"detail": "No certificate matches that token."},
                status=status.HTTP_404_NOT_FOUND,
            )

        CertificateAccessLog.objects.create(
            certificate=certificate,
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        )
        return Response(PublicCertificateSerializer(certificate).data)


class CertificateAccessLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only view of public verification hits.

    Not a ``BaseModelViewSet``: an append-only ledger has nothing to
    soft-delete and nothing to restore.
    """

    queryset = CertificateAccessLog.objects.select_related("certificate")
    serializer_class = CertificateAccessLogSerializer
    permission_classes = [StrictModelPermissions]

    filter_fields = ("certificate",)
    ordering_fields = ("id", "accessed_at")
    ordering = ["-accessed_at"]
    date_filter_fields = ("accessed_at",)
