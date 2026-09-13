"""Preliminary identification of stones, and status transitions."""

from django.db import transaction

from apps.core.exceptions import ServiceError
from apps.gems.enums import StoneStatus, WeightUnit

from ..models import Order, StatusHistory, Stone


def transition_stone(stone: Stone, to_status: str, *, user=None, note: str = "") -> Stone:
    """Move a stone to a new status and record it in the audit trail.

    No-ops if the stone is already in ``to_status``, so a redelivered payment
    notification does not write a duplicate history row.

    There is deliberately no table of allowed transitions: any status may follow
    any other. What actually orders the pipeline is which service calls this -
    billing sets ``billed``, a settled payment sets ``paid``, issuing a
    certificate sets ``certified``. See the follow-ups in the port plan.

    Args:
        stone: The stone to move.
        to_status: A ``StoneStatus`` value.
        user: The acting user, or None when the gateway is the actor.
        note: Free text explaining the move, shown in the history.
    """
    if stone.status == to_status:
        return stone

    from_status = stone.status
    stone.status = to_status
    if user is not None:
        stone.updated_by = user
    stone.save(update_fields=["status", "updated_at", "updated_by"])

    StatusHistory.objects.create(
        stone=stone,
        from_status=from_status,
        to_status=to_status,
        changed_by=user,
        note=note,
    )
    return stone


@transaction.atomic
def add_stone(
    order: Order, *, stone_type, weight=None, weight_unit=WeightUnit.CARAT, user=None
) -> Stone:
    """Record the preliminary identification of a stone: its type.

    Only the type is required here, because it is what the bill is priced from.
    The full identification - weight and the gemmological findings - comes later,
    after payment.

    The label is the next letter of the alphabet, and the order cannot hold more
    stones than the customer said they brought.

    Args:
        order: The order the stone belongs to.
        stone_type: The ``gems.StoneType`` that prices this stone.
        weight: Optional here; usually recorded during full identification.
        weight_unit: Carats unless stated otherwise.
        user: The acting user.

    Raises:
        ServiceError: If every submitted stone has already been identified.
    """
    identified = order.stones.count()
    if identified >= order.stone_count:
        raise ServiceError(
            f"All {order.stone_count} stone(s) for {order.reference_number} have "
            f"already been identified."
        )

    # A, B, C... Breaks above 26 stones, which no order has yet reached.
    label = chr(65 + identified)

    stone = Stone(
        order=order,
        label=label,
        stone_type=stone_type,
        weight=weight,
        weight_unit=weight_unit,
        status=StoneStatus.RECEIVED,
    )
    if user is not None:
        stone.created_by = user
    stone.save()

    StatusHistory.objects.create(
        stone=stone,
        to_status=StoneStatus.RECEIVED,
        changed_by=user,
        note="Preliminarily identified",
    )
    return stone


def update_stone(
    stone: Stone, *, stone_type=None, weight=None, weight_unit=None, user=None
) -> Stone:
    """Update a stone's recorded properties during full identification."""
    if stone_type is not None:
        stone.stone_type = stone_type
    if weight is not None:
        stone.weight = weight
    if weight_unit:
        stone.weight_unit = weight_unit
    if user is not None:
        stone.updated_by = user

    stone.save(
        update_fields=[
            "stone_type",
            "weight",
            "weight_unit",
            "updated_at",
            "updated_by",
        ]
    )
    return stone
