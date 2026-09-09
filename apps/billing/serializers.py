"""Serializers for the billing domain."""

from rest_framework import serializers

from apps.core.serializers import AuditFieldsMixin

from .models import Bill, BillItem, Payment, ServiceProvider


class ServiceProviderSerializer(AuditFieldsMixin):
    """A GePG service provider."""

    class Meta:
        model = ServiceProvider
        fields = (
            "id",
            "sp_code",
            "name",
            "group_code",
            "sys_code",
            "is_active",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        read_only_fields = AuditFieldsMixin.AUDIT_FIELDS


class BillItemSerializer(AuditFieldsMixin):
    """One charge line on a bill."""

    stone_label = serializers.CharField(source="stone.label", read_only=True)

    class Meta:
        model = BillItem
        fields = (
            "id",
            "bill",
            "stone",
            "stone_label",
            "description",
            "unit_price",
            "weight",
            "amount",
            "gfs_code",
            "item_ref",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        # Items are snapshots written by the billing service, never edited.
        read_only_fields = fields


class PaymentSerializer(AuditFieldsMixin):
    """A payment notification as the gateway sent it."""

    class Meta:
        model = Payment
        fields = (
            "id",
            "bill",
            "req_id",
            "grp_bill_id",
            "sp_grp_code",
            "cust_cntr_num",
            "entry_count",
            "sp_code",
            "gepg_bill_id",
            "bill_ctr_num",
            "psp_code",
            "psp_name",
            "trx_id",
            "pay_ref_id",
            "bill_amount",
            "paid_amount",
            "bill_pay_opt",
            "currency",
            "coll_acc_num",
            "trx_dt_tm",
            "usd_pay_chnl",
            "pyr_cell_num",
            "pyr_email",
            "pyr_name",
            "ack_id",
            "ack_sts_code",
            "is_processed",
            "raw_request",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        read_only_fields = fields


class BillSerializer(AuditFieldsMixin):
    """A bill, with its line items and the gateway's last word on it."""

    order_reference = serializers.CharField(
        source="order.reference_number", read_only=True
    )
    customer_name = serializers.CharField(
        source="order.customer.full_name", read_only=True
    )
    service_provider_detail = ServiceProviderSerializer(
        source="service_provider", read_only=True
    )
    items = BillItemSerializer(many=True, read_only=True)
    amount_paid = serializers.SerializerMethodField()

    class Meta:
        model = Bill
        fields = (
            "id",
            "order",
            "order_reference",
            "customer_name",
            "bill_number",
            "control_number",
            "service_provider",
            "service_provider_detail",
            "items",
            "total_amount",
            "amount_paid",
            "currency",
            "status",
            "issued_at",
            "expiry_at",
            "due_date",
            "bill_type",
            "pay_type",
            "status_code",
            "status_desc",
            "is_gepg_submitted",
            "gepg_submitted_at",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        # A bill is created by the billing service and thereafter written only by
        # the gateway callbacks, so nothing here is client-writable.
        read_only_fields = fields

    def get_amount_paid(self, obj) -> str:
        """Sum of the payments received, as a string to preserve the decimal."""
        total = sum((payment.paid_amount or 0) for payment in obj.payments.all())
        return str(total)


class GenerateBillSerializer(serializers.Serializer):
    """Payload for generating an order's bill."""

    service_provider = serializers.PrimaryKeyRelatedField(
        queryset=ServiceProvider.objects.all(), required=False, allow_null=True
    )
