"""API views for the certificates domain."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from django.http import HttpResponse

from apps.core.filters import search_queryset
from apps.core.viewsets import BaseModelViewSet
from apps.gems.enums import CertificateStatus
from apps.orders.models import Stone
from apps.orders.search import STONE_SEARCH_FIELDS
from apps.orders.serializers import StoneSerializer

from .models import Certificate
from .selectors import certification_worklist
from .serializers import CertificateSerializer, IssueCertificateSerializer
from .services import issue_certificate, render_certificate_pdf, revoke_certificate


class CertificateViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """Certificates, plus issuance, revocation and PDF download."""

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
        # `pdf` is deliberately absent: ActionPermissions falls back to the HTTP
        # method map, so a GET resolves to certificates.view_certificate. A
        # download is a read of data the detail endpoint already returns, and
        # the project reserves bespoke permissions for verbs that change state.
    }

    @extend_schema(request=IssueCertificateSerializer, responses=CertificateSerializer)
    def create(self, request, *args, **kwargs):
        """Issue a certificate for a stone.

        Delegates wholly to the service: the number and the snapshots are
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
        # Searched explicitly rather than via `filter_queryset`: this action
        # returns Stones, so the ViewSet's Certificate `search_fields` do not
        # apply.
        queryset = search_queryset(
            certification_worklist(),
            request.query_params.get("search"),
            STONE_SEARCH_FIELDS,
        )
        page = self.paginate_queryset(queryset)
        serializer = StoneSerializer(
            page, many=True, context=self.get_serializer_context()
        )
        return self.get_paginated_response(serializer.data)

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        """Download this certificate as a PDF.

        Rendered on demand rather than stored. The body is frozen snapshot
        columns, so re-rendering is deterministic; the one mutable input is
        ``status``, and a revoked certificate has to pick up its watermark at
        download time - which a stored file could not do without an
        invalidation step.
        """
        certificate = self.get_object()
        suffix = "-revoked" if certificate.status == CertificateStatus.REVOKED else ""
        filename = f"{certificate.certificate_number}{suffix}.pdf"

        # HttpResponse rather than FileResponse: the bytes are already in memory,
        # and ATOMIC_REQUESTS makes a streaming response the more awkward of the
        # two. Returning a bare HttpResponse also bypasses DRF content
        # negotiation, so the client's `Accept: application/json` is harmless.
        response = HttpResponse(
            render_certificate_pdf(certificate), content_type="application/pdf"
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
