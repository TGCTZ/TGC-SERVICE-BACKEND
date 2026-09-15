"""Identification of stones, and status transitions."""

from django.db import transaction

from apps.core.exceptions import ServiceError
from apps.gems.enums import StoneStatus

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


def next_stone_label(order) -> str:
    """The label the next stone identified against this order will carry.

    A, B, C... Breaks above 26 stones, which no order has yet reached.

    Extracted so the screen can *show* the label before it is allocated rather
    than reimplementing the rule - a dialog that says "this will be stone C" and
    a service that writes "D" is the kind of disagreement nobody notices until a
    customer is holding the paperwork.

    Args:
        order: The order the stone would belong to.
    """
    return chr(65 + order.stones.count())


@transaction.atomic
def add_stone(order: Order, *, stone_type, user=None) -> Stone:
    """Record the identification of a stone: its type.

    Only the type is required here, because it is what the bill is priced from.
    The findings - weight and the gemmological findings - comes later,
    after payment.

    The label is the next letter of the alphabet, and the order cannot hold more
    stones than the customer said they brought.

    Args:
        order: The order the stone belongs to.
        stone_type: The ``gems.StoneType`` whose tier prices this stone.
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

    label = next_stone_label(order)

    stone = Stone(
        order=order,
        label=label,
        stone_type=stone_type,
        status=StoneStatus.RECEIVED,
    )
    if user is not None:
        stone.created_by = user
    stone.save()

    StatusHistory.objects.create(
        stone=stone,
        to_status=StoneStatus.RECEIVED,
        changed_by=user,
        note="Identified",
    )
    return stone


# The statuses in which a stone's *type* may still be corrected.
#
# ``received`` is the working state. ``on_hold`` and ``cancelled`` are the two a
# human parks a stone in precisely *to* fix something, so they stay open. Every
# other status means a bill has been priced from this stone's type - and the
# type is the price, so changing it afterwards would silently make an issued
# bill wrong.
#
# **This covers the type, not the whole record.** Weight arrives later than
# billing by design: the bench weighs the stone during the findings, when it is
# already ``paid``. Locking the row outright would make that impossible.
RETYPEABLE_STATUSES = frozenset(
    {StoneStatus.RECEIVED, StoneStatus.ON_HOLD, StoneStatus.CANCELLED}
)


def assert_stone_retypeable(stone: Stone) -> None:
    """Refuse a type change once a bill has been priced from the current one.

    Raises:
        ServiceError: If the stone's status is not in ``RETYPEABLE_STATUSES``.
    """
    if stone.status not in RETYPEABLE_STATUSES:
        raise ServiceError(
            f"{stone.label} is {stone.get_status_display().lower()}, so its type "
            f"can no longer change - that type is what priced the bill."
        )


# ``None`` is a meaningful weight - it is what a stone has before the bench
# weighs it, and what a gemmologist sets after realising they typed a reading
# against the wrong stone. A ``None`` default could not tell "clear this" from
# "leave this alone", so an omitted weight gets its own sentinel.
_UNSET = object()


def update_stone(
    stone: Stone,
    *,
    stone_type=None,
    weight=_UNSET,
    weight_unit=None,
    photo=_UNSET,
    user=None,
) -> Stone:
    """Update a stone's recorded properties during the findings stage.

    ``photo`` uses the same ``_UNSET`` sentinel as ``weight`` so that passing
    ``None`` clears the image, while omitting it leaves the existing one alone -
    a plain default of ``None`` would silently wipe the photograph on every
    partial update that did not mention it.

    Raises:
        ServiceError: If the stone has been billed and the caller is trying to
            change its type. Weight and the photograph stay writable at every
            status - the bench records both after payment.
    """
    if stone_type is not None:
        assert_stone_retypeable(stone)
        stone.stone_type = stone_type
    if weight is not _UNSET:
        stone.weight = weight
    if weight_unit:
        stone.weight_unit = weight_unit
    if photo is not _UNSET:
        stone.photo = photo
    if user is not None:
        stone.updated_by = user

    stone.save(
        update_fields=[
            "stone_type",
            "weight",
            "weight_unit",
            "photo",
            "updated_at",
            "updated_by",
        ]
    )
    return stone
