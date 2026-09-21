"""Reads that encode a findings workflow gate."""

from django.contrib.auth import get_user_model

from apps.gems.enums import BillStatus
from apps.orders.models import Stone
from apps.users.roles import GEMMOLOGIST_ROLE


def findings_worklist():
    """Stones waiting for findings.

    The bill must be settled before a gemmologist starts work, and a stone
    leaves the queue once its report is finalized. Reached through the bill on
    the stone's order, which is why the enum lives in ``apps.gems`` rather than
    in ``apps.billing`` - the join itself needs no import.
    """
    return (
        Stone.objects.select_related(
            "order",
            "order__customer",
            "stone_type",
            # The row serialises the stone type, which renders its
            # category - one query per row without this join.
            "stone_type__category",
        )
        # `reports` is a reverse FK, so it is prefetched rather than joined; the
        # rows read it back through `Stone.report`.
        .prefetch_related("reports")
        .filter(order__bill__status=BillStatus.PAID)
        # A soft-deleted report does not count as findings, so the join is
        # narrowed to live rows - a database join sees every row, including the
        # ones the model's default manager hides.
        .exclude(reports__is_finalized=True, reports__deleted_at__isnull=True)
        # Grouped by the parcel they came in on, which is how they sit on the
        # bench; `pk` breaks the tie so a paginated page is stable.
        .order_by("order__received_date", "order_id", "label", "pk")
    )


def gemmologist_candidates(*, exclude_user=None):
    """Active gemmologists who may be named as the second signatory.

    A certificate states that the stone was "examined by at least two qualified
    Gemmologists", so the countersignature has to come from the bench - not from
    everyone who happens to hold ``finalize_report``, which a manager does too.
    Encoded here rather than in the dialog because it is the sentence on the
    printed document that has to stay true, including for a caller that never
    opens the UI.

    Args:
        exclude_user: The first gemmologist, left out of their own candidate
            list. ``finalize_report`` refuses a report signed twice by the same
            person, so offering the choice would only earn a rejection.

    Returns:
        A ``User`` queryset ordered by display name.
    """
    queryset = get_user_model().objects.filter(
        is_active=True, groups__name=GEMMOLOGIST_ROLE
    )
    if exclude_user is not None:
        queryset = queryset.exclude(pk=exclude_user.pk)
    # `pk` breaks the tie, so two people sharing a name keep a stable order.
    return queryset.order_by("first_name", "last_name", "pk")
