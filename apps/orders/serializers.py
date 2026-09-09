"""Serializers for the order domain."""

from rest_framework import serializers

from apps.core.serializers import AuditFieldsMixin
from apps.gems.enums import StoneStatus, WeightUnit
from apps.gems.models import StoneType
from apps.gems.serializers import StoneTypeSerializer

from .models import Customer, Order, StatusHistory, Stone


class CustomerSerializer(AuditFieldsMixin):
    """A submitting customer."""

    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Customer
        fields = (
            "id",
            "first_name",
            "middle_name",
            "last_name",
            "full_name",
            "phone",
            "email",
            "company_name",
            "region",
            "id_number",
            "address",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        read_only_fields = AuditFieldsMixin.AUDIT_FIELDS


class StoneSerializer(AuditFieldsMixin):
    """One stone in an order.

    ``status`` is read-only: it moves through ``POST {id}/transition/`` so that
    every change writes a history row. A writable field here would let a client
    change the status without leaving a trace.
    """

    stone_type_detail = StoneTypeSerializer(source="stone_type", read_only=True)
    order_reference = serializers.CharField(
        source="order.reference_number", read_only=True
    )

    class Meta:
        model = Stone
        fields = (
            "id",
            "order",
            "order_reference",
            "label",
            "stone_type",
            "stone_type_detail",
            "weight",
            "weight_unit",
            "status",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        read_only_fields = (*AuditFieldsMixin.AUDIT_FIELDS, "label", "status", "order")


class OrderSerializer(AuditFieldsMixin):
    """An order, with its customer and progress counters."""

    customer_detail = CustomerSerializer(source="customer", read_only=True)
    identified_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "reference_number",
            "customer",
            "customer_detail",
            "received_date",
            "stone_count",
            "identified_count",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        # The reference number is allocated by the service, never supplied.
        read_only_fields = (*AuditFieldsMixin.AUDIT_FIELDS, "reference_number")


class StatusHistorySerializer(serializers.ModelSerializer):
    """One entry in a stone's status trail.

    Plain ``ModelSerializer`` rather than ``AuditFieldsMixin``: the model is an
    append-only ledger with no audit columns of its own.
    """

    changed_by_label = serializers.SerializerMethodField()

    class Meta:
        model = StatusHistory
        fields = (
            "id",
            "stone",
            "from_status",
            "to_status",
            "changed_by",
            "changed_by_label",
            "changed_at",
            "note",
        )
        read_only_fields = fields

    def get_changed_by_label(self, obj) -> str:
        """Who made the change, or 'System' when the gateway did."""
        return str(obj.changed_by) if obj.changed_by_id else "System"


class AddStoneSerializer(serializers.Serializer):
    """Payload for registering one stone against an order."""

    stone_type = serializers.PrimaryKeyRelatedField(queryset=StoneType.objects.all())
    weight = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, allow_null=True
    )
    weight_unit = serializers.ChoiceField(
        choices=WeightUnit.choices, default=WeightUnit.CARAT
    )


class TransitionSerializer(serializers.Serializer):
    """Payload for moving a stone to a new status."""

    to_status = serializers.ChoiceField(choices=StoneStatus.choices)
    note = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
