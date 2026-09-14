"""Serializers for the order domain."""

from rest_framework import serializers

from apps.core.serializers import AuditFieldsMixin
from apps.gems.enums import OrderHold, OrderStage, StoneStatus
from apps.gems.models import StoneType
from apps.gems.serializers import StoneTypeSerializer

from .models import Customer, Order, StatusHistory, Stone
from .selectors import order_stage


class CustomerSerializer(AuditFieldsMixin):
    """A submitting customer."""

    full_name = serializers.CharField(read_only=True)

    def validate_phone(self, value):
        """Refuse a phone already on file, naming who holds it.

        The model has a partial unique index on ``phone``, but an IntegrityError
        reaches the client as an opaque "conflicts with existing data" - which
        tells reception nothing and offers no way out. Checking here turns it
        into a field error naming the existing customer, so the UI can offer to
        use that record instead of asking for the same details again.
        """
        existing = Customer.objects.filter(phone=value)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)

        match = existing.first()
        if match is not None:
            raise serializers.ValidationError(
                f"Already registered to {match.full_name}. Pick that customer instead."
            )
        return value

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
        # Drop the UniqueValidator DRF infers from the model's partial unique
        # index: it fires before validate_phone and reports a message that names
        # nobody. The check below replaces it, and the index still backstops.
        extra_kwargs = {"phone": {"validators": []}}


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
            "photo",
            "status",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        read_only_fields = (*AuditFieldsMixin.AUDIT_FIELDS, "label", "status", "order")


class OrderSerializer(AuditFieldsMixin):
    """An order, with its customer and progress counters.

    The project's one nested write. Every other nested serializer here is
    read-only, and this is the exception because reception meets most customers
    for the first time while receiving their order: send ``customer`` for
    somebody on file, or ``customer_data`` to register them alongside the order.
    """

    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False
    )
    customer_detail = CustomerSerializer(source="customer", read_only=True)
    # The bill raised against this order, if any.
    #
    # Exposed so a screen can tell "ready to bill" from "already billed"
    # without a second request. `apps.orders` sits below `apps.billing`, so
    # this reads the reverse relation rather than importing it.
    bill_number = serializers.SerializerMethodField()
    control_number = serializers.SerializerMethodField()
    # Where the order has got to, derived from its stones and its bill.
    stage = serializers.SerializerMethodField()
    stage_label = serializers.SerializerMethodField()
    held_by_label = serializers.SerializerMethodField()
    customer_data = CustomerSerializer(required=False, write_only=True)
    identified_count = serializers.IntegerField(read_only=True)

    def validate(self, attrs):
        """Require exactly one of ``customer`` and ``customer_data``.

        Both together is an error rather than a precedence rule: it means the
        client is confused about which customer this order belongs to, and
        silently picking one would attach the order to the wrong person.
        """
        # On PATCH, an untouched customer is not a missing one.
        if self.instance is not None and "customer_data" not in attrs:
            return attrs

        has_ref = attrs.get("customer") is not None
        has_data = bool(attrs.get("customer_data"))

        if has_ref and has_data:
            raise serializers.ValidationError(
                "Send either an existing customer or new customer details, not both."
            )
        if not has_ref and not has_data and self.instance is None:
            raise serializers.ValidationError(
                {"customer": "Select a customer or enter their details."}
            )
        return attrs

    class Meta:
        model = Order
        fields = (
            "id",
            "reference_number",
            "customer",
            "customer_detail",
            "customer_data",
            "received_date",
            "stone_count",
            "identified_count",
            "bill_number",
            "control_number",
            "stage",
            "stage_label",
            "hold_status",
            "hold_reason",
            "held_by",
            "held_by_label",
            "held_at",
            *AuditFieldsMixin.AUDIT_FIELDS,
        )
        # The reference number is allocated by the service, never supplied.
        read_only_fields = (
            *AuditFieldsMixin.AUDIT_FIELDS,
            "reference_number",
            "bill_number",
            "control_number",
            "stage",
            "stage_label",
            "hold_status",
            "hold_reason",
            "held_by",
            "held_by_label",
            "held_at",
        )

    def get_bill_number(self, obj) -> str | None:
        """This order's bill number, or None if it has not been billed."""
        bill = getattr(obj, "bill", None)
        return bill.bill_number if bill is not None else None

    def get_control_number(self, obj) -> str | None:
        """The number the customer quotes when paying, once GePG has issued one.

        Allocated by the gateway in response to the bill submission, not minted
        here - so it stays null on a bill whose submission failed, which is
        exactly the case worth seeing from the orders list.
        """
        bill = getattr(obj, "bill", None)
        return (bill.control_number or None) if bill is not None else None

    def get_stage(self, obj) -> str:
        """The stage code, for a client to style and filter on."""
        return order_stage(obj)

    def get_stage_label(self, obj) -> str:
        """The stage in words, so a client need not mirror the enum."""
        return OrderStage(order_stage(obj)).label

    def get_held_by_label(self, obj) -> str | None:
        """Who paused or withdrew the order, or None if it is active."""
        return str(obj.held_by) if obj.held_by_id else None


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
    """Payload for identifying one stone.

    Type only: it is what the bill is priced from. Weight is a bench
    measurement and arrives later, with the findings.
    """

    stone_type = serializers.PrimaryKeyRelatedField(queryset=StoneType.objects.all())


class TransitionSerializer(serializers.Serializer):
    """Payload for moving a stone to a new status."""

    to_status = serializers.ChoiceField(choices=StoneStatus.choices)
    note = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class HoldOrderSerializer(serializers.Serializer):
    """Payload for pausing or withdrawing an order.

    ``reason`` is required rather than optional: a held order that says nothing
    about why is a question for whoever finds it next, and the person who knows
    the answer is the one filling this in.
    """

    hold_status = serializers.ChoiceField(
        choices=[OrderHold.ON_HOLD, OrderHold.CANCELLED]
    )
    reason = serializers.CharField(max_length=500)
