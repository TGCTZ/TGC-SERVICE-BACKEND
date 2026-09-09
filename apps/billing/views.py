"""API views for the billing domain."""

from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import ActionPermissions, StrictModelPermissions
from apps.core.viewsets import BaseModelViewSet
from apps.orders.models import Order
from apps.orders.serializers import OrderSerializer

from .models import Bill, BillItem, Payment, ServiceProvider
from .selectors import billing_worklist
from .serializers import (
    BillItemSerializer,
    BillSerializer,
    GenerateBillSerializer,
    PaymentSerializer,
    ServiceProviderSerializer,
)
from .services import generate_bill_for_order


class ServiceProviderViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    """CRUD over GePG service providers."""

    queryset = ServiceProvider.objects.all()
    serializer_class = ServiceProviderSerializer
    search_fields = ("name", "sp_code", "group_code", "sys_code")
    filter_fields = ("is_active",)
    ordering_fields = ("id", "name", "sp_code", "is_active", "created_at")


class BillViewSet(viewsets.ReadOnlyModelViewSet):
    """Bills, plus the action that creates one.

    Read-only for CRUD purposes: a bill is created by ``POST /bills/generate/``
    so the service can price every stone and transition it, and thereafter only
    the gateway callbacks change it.

    Generation hangs off this ViewSet rather than off the order it bills because
    ``apps.orders`` sits a layer below ``apps.billing`` and must not import it.
    """

    queryset = Bill.objects.select_related(
        "order", "order__customer", "service_provider", "created_by", "updated_by"
    ).prefetch_related("items", "items__stone", "payments")
    serializer_class = BillSerializer
    permission_classes = [ActionPermissions]

    search_fields = (
        "bill_number",
        "control_number",
        "order__reference_number",
        "order__customer__first_name",
        "order__customer__last_name",
    )
    filter_fields = ("status", "order", "service_provider", "currency")
    ordering_fields = ("id", "bill_number", "total_amount", "status", "created_at")
    date_filter_fields = ("created_at", "updated_at", "issued_at", "expiry_at")

    action_permissions = {
        "generate": ["billing.generate_bill"],
        "worklist": ["billing.generate_bill"],
    }

    @extend_schema(request=GenerateBillSerializer, responses=BillSerializer)
    @action(detail=False, methods=["post"])
    def generate(self, request):
        """Bill an order: price every stone, then submit to GePG."""
        payload = GenerateBillSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        order = Order.objects.filter(pk=request.data.get("order")).first()
        if order is None:
            return Response(
                {"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        bill = generate_bill_for_order(
            order,
            service_provider=payload.validated_data.get("service_provider"),
            user=request.user,
        )
        return Response(self.get_serializer(bill).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=OrderSerializer)
    @action(detail=False, methods=["get"])
    def worklist(self, request):
        """Orders with every stone registered and no bill yet."""
        queryset = billing_worklist()
        page = self.paginate_queryset(queryset)
        serializer = OrderSerializer(
            page, many=True, context=self.get_serializer_context()
        )
        return self.get_paginated_response(serializer.data)


class BillItemViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only view of bill lines.

    Snapshots taken at billing time; editing one would rewrite what a customer
    was charged.
    """

    queryset = BillItem.objects.select_related(
        "bill", "stone", "created_by", "updated_by"
    )
    serializer_class = BillItemSerializer
    permission_classes = [StrictModelPermissions]

    filter_fields = ("bill", "stone")
    ordering_fields = ("id", "amount", "created_at")


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only view of payments.

    The only legitimate writer is the GePG notification webhook.
    """

    queryset = Payment.objects.select_related(
        "bill", "bill__order", "created_by", "updated_by"
    )
    serializer_class = PaymentSerializer
    permission_classes = [StrictModelPermissions]

    search_fields = ("trx_id", "gepg_bill_id", "bill_ctr_num", "pyr_name", "psp_name")
    filter_fields = ("bill", "is_processed", "currency", "psp_code")
    ordering_fields = ("id", "trx_dt_tm", "paid_amount", "created_at")
    date_filter_fields = ("trx_dt_tm", "created_at")
