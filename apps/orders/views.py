"""API views for the order domain."""

from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import StrictModelPermissions
from apps.core.viewsets import BaseModelViewSet

from .models import Customer, Order, StatusHistory, Stone
from .selectors import registration_worklist
from .serializers import (
    AddStoneSerializer,
    CustomerSerializer,
    OrderSerializer,
    StatusHistorySerializer,
    StoneSerializer,
    TransitionSerializer,
)
from .services import add_stone, create_order, transition_stone


class CustomerViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over customers."""

    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    search_fields = (
        "first_name",
        "middle_name",
        "last_name",
        "phone",
        "email",
        "company_name",
        "id_number",
    )
    filter_fields = ("region", "company_name")
    ordering_fields = ("id", "first_name", "last_name", "phone", "created_at")


class OrderViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over orders, plus stone registration."""

    # Every row serialises its customer, and identified_count counts the stones.
    queryset = Order.objects.select_related("customer").prefetch_related("stones")
    serializer_class = OrderSerializer

    search_fields = (
        "reference_number",
        "customer__first_name",
        "customer__last_name",
        "customer__phone",
    )
    filter_fields = ("customer", "received_date")
    ordering_fields = ("id", "reference_number", "received_date", "created_at")
    date_filter_fields = ("created_at", "updated_at", "received_date")

    action_permissions = {"add_stone": ["orders.add_stone"]}

    def perform_create(self, serializer):
        """Delegate to the service, which allocates the reference number."""
        order = create_order(
            customer=serializer.validated_data["customer"],
            stone_count=serializer.validated_data.get("stone_count", 0),
            received_date=serializer.validated_data.get("received_date"),
            user=self.request.user,
        )
        serializer.instance = order

    @extend_schema(request=AddStoneSerializer, responses=StoneSerializer)
    @action(detail=True, methods=["post"], url_path="stones")
    def add_stone(self, request, pk=None):
        """Register the next stone against this order.

        A dedicated action rather than ``POST /stones/``: the service owns the
        label sequence and the cap at ``order.stone_count``, and a bare create
        would bypass both.
        """
        order = self.get_object()
        payload = AddStoneSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        stone = add_stone(order, user=request.user, **payload.validated_data)
        return Response(
            StoneSerializer(stone, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses=OrderSerializer)
    @action(detail=False, methods=["get"], url_path="worklist-registration")
    def worklist_registration(self, request):
        """Orders with stones still to register."""
        queryset = self.filter_queryset(registration_worklist())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)


class StoneViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over stones, plus status transitions."""

    queryset = Stone.objects.select_related("order", "order__customer", "stone_type")
    serializer_class = StoneSerializer

    search_fields = ("label", "order__reference_number", "stone_type__name")
    filter_fields = ("order", "stone_type", "status", "weight_unit")
    ordering_fields = ("id", "label", "status", "weight", "created_at")

    action_permissions = {"transition": ["orders.transition_stone"]}

    @extend_schema(request=TransitionSerializer, responses=StoneSerializer)
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        """Move this stone to a new status, writing a history entry."""
        stone = self.get_object()
        payload = TransitionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        stone = transition_stone(
            stone,
            payload.validated_data["to_status"],
            user=request.user,
            note=payload.validated_data.get("note", ""),
        )
        return Response(self.get_serializer(stone).data)


class StatusHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only view of stone status transitions.

    Not a ``BaseModelViewSet``: the model is an append-only ledger, so there is
    nothing to soft-delete and nothing to restore.
    """

    queryset = StatusHistory.objects.select_related("stone", "changed_by")
    serializer_class = StatusHistorySerializer
    permission_classes = [StrictModelPermissions]

    filter_fields = ("stone", "to_status", "from_status", "changed_by")
    ordering_fields = ("id", "changed_at")
    ordering = ["-changed_at"]
    date_filter_fields = ("changed_at",)
