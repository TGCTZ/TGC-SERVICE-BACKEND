"""API views for the billing domain."""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404

from apps.core.filters import search_queryset
from apps.core.permissions import ActionPermissions, StrictModelPermissions
from apps.core.viewsets import BaseModelViewSet
from apps.core.workflow_feed import feed_row, paginated_workflow_feed
from apps.orders.models import Order
from apps.orders.search import ORDER_SEARCH_FIELDS
from apps.orders.serializers import AddStoneSerializer, OrderSerializer

from .dev import simulate_payment
from .models import Bill, BillItem, Payment, ServiceProvider
from .selectors import billing_attention_worklist, billing_worklist
from .serializers import (
    BillItemSerializer,
    BillPreviewSerializer,
    BillSerializer,
    GenerateBillSerializer,
    IdentifiedStoneSerializer,
    PaymentSerializer,
    RetryBillSerializer,
    ServiceProviderSerializer,
    SimulatePaymentSerializer,
)
from .services import (
    generate_bill_for_order,
    identify_stone,
    preview_bill_for_order,
    retry_bill_for_order,
)


class IdentifyStoneView(APIView):
    """Preserve the order URL while billing owns the cross-app handoff."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=AddStoneSerializer, responses={201: IdentifiedStoneSerializer})
    def post(self, request, pk):
        """Identify one stone and bill automatically if this completes the order."""
        if not request.user.has_perm("orders.add_stone"):
            raise PermissionDenied("You may not identify stones.")
        order = get_object_or_404(Order, pk=pk)
        payload = AddStoneSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        stone, bill, attention = identify_stone(
            order, user=request.user, **payload.validated_data
        )
        response = IdentifiedStoneSerializer(
            stone,
            context={"request": request, "bill": bill, "billing_attention": attention},
        )
        return Response(response.data, status=status.HTTP_201_CREATED)


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
        "preview": ["billing.generate_bill"],
        # Simulating a settlement is the same authority as raising the bill.
        "simulate_payment": ["billing.generate_bill"],
        "worklist": ["billing.generate_bill"],
        "attention": ["billing.generate_bill"],
        "retry": ["billing.generate_bill"],
    }

    @extend_schema(request=GenerateBillSerializer, responses=BillSerializer)
    @action(detail=False, methods=["post"])
    def generate(self, request):
        """Bill an order: price every stone, then submit to GePG."""
        if settings.AUTO_BILL_AFTER_IDENTIFICATION:
            raise Http404
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

    @extend_schema(request=SimulatePaymentSerializer, responses=BillSerializer)
    @action(detail=True, methods=["post"], url_path="simulate-payment")
    def simulate_payment(self, request, pk=None):
        """Pay this bill with a fabricated GePG notification. Development only.

        Answers **404** rather than 403 when simulation is off, so the route does
        not advertise its own existence on a deployment that must never have it.
        Both flags are required: ``DEBUG`` alone is not enough, because a staging
        box pointed at the real gateway would then be able to forge settlements.

        The payload goes through the same handler the live webhook calls, so this
        exercises the real path - parse, record, settle, transition - rather than
        writing a paid bill directly.
        """
        if not (settings.DEBUG and getattr(settings, "GEPG_SIMULATE", False)):
            raise Http404

        payload = SimulatePaymentSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        bill = simulate_payment(self.get_object(), payload.validated_data.get("amount"))
        return Response(self.get_serializer(bill).data)

    @extend_schema(
        parameters=[
            OpenApiParameter("order", int, description="Order to price.", required=True)
        ],
        responses=BillPreviewSerializer,
    )
    @action(detail=False, methods=["get"])
    def preview(self, request):
        """What billing this order would charge, without creating anything.

        Its own endpoint rather than letting the client price the stones: the
        fee is per stone *category*, so a UI reading ``stone_type.price`` would
        show a total the bill then disagrees with.
        """
        order = Order.objects.filter(pk=request.query_params.get("order")).first()
        if order is None:
            return Response(
                {"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        return Response(BillPreviewSerializer(preview_bill_for_order(order)).data)

    @extend_schema(responses=OrderSerializer)
    @action(detail=False, methods=["get"])
    def worklist(self, request):
        """Orders with every stone identified and no bill yet."""
        if settings.AUTO_BILL_AFTER_IDENTIFICATION:
            raise Http404
        # Searched explicitly rather than via `filter_queryset`: this action
        # returns Orders, so the ViewSet's Bill `search_fields` do not apply.
        queryset = search_queryset(
            billing_worklist(), request.query_params.get("search"), ORDER_SEARCH_FIELDS
        )
        page = self.paginate_queryset(queryset)
        serializer = OrderSerializer(
            page, many=True, context=self.get_serializer_context()
        )
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=["get"], url_path="workflow-feed")
    def workflow_feed(self, request):
        """Existing bills and billable orders in one viewer-readable feed."""
        bills = BillSerializer(
            self.get_queryset().order_by("-created_at", "-pk"),
            many=True,
            context=self.get_serializer_context(),
        ).data
        if settings.AUTO_BILL_AFTER_IDENTIFICATION:
            pending_orders = billing_attention_worklist()
        else:
            pending_orders = billing_worklist()
        pending_ids = set(pending_orders.values_list("pk", flat=True))
        rows = [
            feed_row(
                kind="bill",
                record_id=row["id"],
                reference=row.get("bill_number"),
                customer=row.get("customer_name"),
                type_name="Bill",
                status=row.get("status"),
                date=row.get("issued_at") or row.get("created_at"),
                waiting=False,
                detail=row,
            )
            for row in bills
        ]
        order_data = OrderSerializer(
            pending_orders, many=True, context=self.get_serializer_context()
        ).data
        rows.extend(
            feed_row(
                kind="order",
                record_id=row["id"],
                reference=row.get("reference_number"),
                customer=(row.get("customer_detail") or {}).get("full_name"),
                type_name="Order",
                status="Ready to bill",
                date=row.get("received_date"),
                waiting=True,
                detail=row,
            )
            for row in order_data
            if row["id"] in pending_ids
        )
        return paginated_workflow_feed(self, rows, request)

    @extend_schema(responses=OrderSerializer)
    @action(detail=False, methods=["get"])
    def attention(self, request):
        """Failed automatic bills and identified orders missing a bill."""
        if not settings.AUTO_BILL_AFTER_IDENTIFICATION:
            raise Http404
        queryset = search_queryset(
            billing_attention_worklist(),
            request.query_params.get("search"),
            ORDER_SEARCH_FIELDS,
        )
        page = self.paginate_queryset(queryset)
        serializer = OrderSerializer(
            page, many=True, context=self.get_serializer_context()
        )
        return self.get_paginated_response(serializer.data)

    @extend_schema(request=RetryBillSerializer, responses=BillSerializer)
    @action(detail=False, methods=["post"])
    def retry(self, request):
        """Retry pricing or resubmit the existing failed bill."""
        if not settings.AUTO_BILL_AFTER_IDENTIFICATION:
            raise Http404
        payload = RetryBillSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        bill = retry_bill_for_order(payload.validated_data["order"], user=request.user)
        return Response(self.get_serializer(bill).data)


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
