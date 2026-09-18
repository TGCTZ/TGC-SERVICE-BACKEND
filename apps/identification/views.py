"""API views for the identification domain."""

from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import ServiceError
from apps.core.filters import search_queryset
from apps.core.viewsets import BaseModelViewSet
from apps.orders.search import STONE_SEARCH_FIELDS
from apps.orders.serializers import StoneSerializer

from .models import IdentificationReport, InstrumentUsed
from .selectors import findings_worklist
from .serializers import (
    FinalizeReportSerializer,
    IdentificationReportSerializer,
    InstrumentUsedSerializer,
)
from .services import create_report, finalize_report, update_report


class IdentificationReportViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over identification reports, plus the finalize action."""

    queryset = IdentificationReport.objects.select_related(
        "stone",
        "stone__order",
        "stone__order__customer",
        "species",
        "variety",
        "origin",
        "shape_cut",
        "color",
        "identified_by",
        "verified_by",
    ).prefetch_related("instruments_used", "instruments_used__instrument")
    serializer_class = IdentificationReportSerializer

    search_fields = (
        "report_number",
        "conclusion",
        "stone__label",
        "stone__order__reference_number",
    )
    filter_fields = (
        "stone",
        "is_finalized",
        "species",
        "variety",
        "origin",
        "shape_cut",
        "color",
        "nature_type",
        "transparency",
        "treatment",
        "optic_character",
        "is_polished",
    )
    ordering_fields = (
        "id",
        "report_number",
        "is_finalized",
        "identified_at",
        "created_at",
    )
    date_filter_fields = ("created_at", "updated_at", "identified_at")

    action_permissions = {
        "finalize": ["identification.finalize_report"],
        "worklist": ["identification.add_identificationreport"],
    }

    def perform_create(self, serializer):
        """Delegate to the service, which allocates the number and checks payment."""
        fields = dict(serializer.validated_data)
        stone = fields.pop("stone")
        serializer.instance = create_report(stone=stone, user=self.request.user, **fields)

    def perform_update(self, serializer):
        """Delegate to the service, which refuses a finalized report."""
        fields = dict(serializer.validated_data)
        # The stone a report belongs to is fixed at creation.
        fields.pop("stone", None)
        serializer.instance = update_report(
            serializer.instance, user=self.request.user, **fields
        )

    @extend_schema(
        request=FinalizeReportSerializer, responses=IdentificationReportSerializer
    )
    @action(detail=True, methods=["post"])
    def finalize(self, request, pk=None):
        """Lock this report against further edits, naming the second gemmologist."""
        payload = FinalizeReportSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        report = finalize_report(
            self.get_object(),
            user=request.user,
            verified_by=payload.validated_data.get("verified_by"),
        )
        return Response(self.get_serializer(report).data)

    @extend_schema(responses=StoneSerializer)
    @action(detail=False, methods=["get"])
    def worklist(self, request):
        """Paid stones whose findings are not finalized yet."""
        # Searched explicitly rather than via `filter_queryset`: this action
        # returns Stones, so the ViewSet's report `search_fields` do not apply.
        queryset = search_queryset(
            findings_worklist(), request.query_params.get("search"), STONE_SEARCH_FIELDS
        )
        page = self.paginate_queryset(queryset)
        serializer = StoneSerializer(
            page, many=True, context=self.get_serializer_context()
        )
        return self.get_paginated_response(serializer.data)


class InstrumentUsedViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over the instruments recorded against a report."""

    queryset = InstrumentUsed.objects.select_related("report", "instrument")
    serializer_class = InstrumentUsedSerializer

    filter_fields = ("report", "instrument")
    ordering_fields = ("id", "created_at")

    def perform_create(self, serializer):
        """Refuse to add an instrument to a finalized report."""
        self._assert_report_open(serializer.validated_data["report"])
        serializer.save()

    def perform_update(self, serializer):
        """Refuse to edit an instrument on a finalized report."""
        self._assert_report_open(
            serializer.validated_data.get("report", serializer.instance.report)
        )
        serializer.save()

    def perform_destroy(self, instance):
        """Refuse to remove an instrument from a finalized report."""
        self._assert_report_open(instance.report)
        super().perform_destroy(instance)

    @staticmethod
    def _assert_report_open(report) -> None:
        """The finalize lock covers the report's instruments too.

        Without this the readings could be rewritten after the report they
        belong to was locked, which would make the lock meaningless.
        """
        if report.is_finalized:
            raise ServiceError("A finalized report cannot be edited.")
