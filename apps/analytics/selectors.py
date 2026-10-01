"""Aggregate reads behind the management statistics.

Each public function answers one section of the dashboard's Management tab for
a :class:`~apps.analytics.periods.Period` and returns JSON-ready data. The
docstrings are the contract with the management team: they say exactly what is
counted, because a number nobody can trace back to the records is a number
nobody should decide on.

Conventions every section keeps:

- **Money is never added across currencies.** Every amount is reported per
  currency. The lab bills in TZS today, but ``Bill.currency`` allows others,
  and a total of shillings plus dollars is not a number.
- **"Received" means handed in at reception**: an order's ``received_date``
  and its ``stone_count``. A ``Stone`` row only exists once the bench has
  identified the stone, so counting stone rows would count identifications.
- **Default managers only**, so soft-deleted rows are in no statistic.
- **Grouped queries call ``.order_by()`` first.** Most of these models carry a
  default ordering, and Django adds ordering columns to ``GROUP BY`` - which
  would silently split every aggregate into one group per row.
"""

import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import (
    Avg,
    Count,
    DecimalField,
    F,
    Min,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, NullIf
from django.utils import timezone

from apps.billing.models import Bill, BillItem, Payment
from apps.certificates.models import Certificate
from apps.gems.enums import (
    BillStatus,
    CertificateStatus,
    NatureType,
    OrderHold,
    Region,
    StoneStatus,
    Treatment,
)
from apps.identification.models import IdentificationReport
from apps.orders.models import Order, StatusHistory, Stone

from .periods import Period, lab_day, local_date

NOT_RECORDED = "Not recorded"
TOP_N = 10

OPEN_BILLS = (BillStatus.PENDING, BillStatus.PARTIALLY_PAID)

#: Statuses a stone is still being worked on in. Certified stones are finished
#: as far as the lab's work goes; collection is not tracked yet, so counting
#: them would make every certified stone look a day older each day.
LIVE_STATUSES = (
    StoneStatus.RECEIVED,
    StoneStatus.UNDER_IDENTIFICATION,
    StoneStatus.BILLED,
    StoneStatus.PAID,
    StoneStatus.ON_HOLD,
)

#: The stage before a stone has a row of its own: reception has registered the
#: order, the bench has not identified the stone yet.
AWAITING_IDENTIFICATION = "identification"

#: What the lab is waiting for while a stone sits in each status. The bottleneck
#: chart speaks in these words, since "time in 'billed'" means little to a board.
STAGE_LABELS = {
    AWAITING_IDENTIFICATION: "Awaiting identification",
    StoneStatus.RECEIVED: "Awaiting billing",
    StoneStatus.UNDER_IDENTIFICATION: "Under identification",
    StoneStatus.BILLED: "Awaiting payment",
    StoneStatus.PAID: "Findings & certification",
    StoneStatus.ON_HOLD: "On hold",
}
STAGE_ORDER = (AWAITING_IDENTIFICATION, *StoneStatus.values)

#: Whole days since an open bill was issued: (lowest, highest or None, label).
RECEIVABLE_AGES = (
    (0, 7, "0-7 days"),
    (8, 30, "8-30 days"),
    (31, 90, "31-90 days"),
    (91, None, "Over 90 days"),
)

#: Whole days a stone has waited in its current stage: (lowest, highest or
#: None for open-ended, label, status). The whole pipeline normally takes one
#: to three days when the customer pays promptly, so a stage should clear
#: within a day. The bands are cut to catch drift early - "watch" once one
#: stage alone has used up the usual three days' budget, "late" beyond it -
#: rather than to count stones that are already weeks behind.
AGE_BUCKETS = (
    (0, 0, "Under 1 day", "normal"),
    (1, 1, "1 day", "normal"),
    (2, 3, "2-3 days", "watch"),
    (4, 7, "4-7 days", "late"),
    (8, None, "Over 7 days", "late"),
)


# ---------------------------------------------------------------- helpers ---


def _in(queryset, field: str, period: Period):
    """Rows whose datetime ``field`` falls on one of the period's lab days."""
    start, end = period.bounds()
    return queryset.filter(**{f"{field}__gte": start, f"{field}__lt": end})


def _money(value) -> float:
    """A Decimal amount as a JSON number, to the cent."""
    return round(float(value or 0), 2)


def _days(delta: timedelta) -> float:
    """A duration in (fractional) days, never negative."""
    return max(delta.total_seconds(), 0) / 86400


def _rate(part, whole) -> float | None:
    """``part / whole``, or None when there is nothing to divide by."""
    return round(float(part) / float(whole), 4) if whole else None


def _describe(values: list[float]) -> dict:
    """Median, mean and 90th percentile of a list of day counts.

    The median leads because one stone forgotten on a shelf for a month drags
    the mean far from what a typical customer experienced. The 90th percentile
    (nearest rank) is the promise the lab can keep to nine customers in ten.
    Two decimal places, because most stage waits are under a day and 0.1 of a
    day is already 2.4 hours.
    """
    if not values:
        return {"median": None, "average": None, "p90": None}
    ordered = sorted(values)
    p90 = ordered[math.ceil(0.9 * len(ordered)) - 1]
    return {
        "median": round(statistics.median(ordered), 2),
        "average": round(statistics.fmean(ordered), 2),
        "p90": round(p90, 2),
    }


def _top(pairs: Iterable[tuple[str | None, int]], limit: int = TOP_N) -> list[dict]:
    """``(name, count)`` pairs as a ranked list, the tail folded into "Other".

    Blank names become "Not recorded" rather than disappearing: a large gap in
    the findings is itself something management should see.
    """
    counts: Counter = Counter()
    for name, count in pairs:
        counts[name or NOT_RECORDED] += count or 0
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    rows = [{"name": name, "count": count} for name, count in ranked[:limit]]
    rest = sum(count for _, count in ranked[limit:])
    if rest:
        rows.append({"name": "Other", "count": rest})
    return rows


def _labelled(pairs: Iterable[tuple[str, int]], choices) -> list[dict]:
    """Choice values as their display labels, every one listed."""
    labels = dict(choices.choices)
    return _top(
        ((labels.get(value, value) if value else None, count) for value, count in pairs),
        limit=len(labels) + 1,
    )


def _counted(queryset, field: str):
    """``(value, row count)`` for each distinct value of ``field``."""
    return (
        queryset.order_by().values(field).annotate(n=Count("id")).values_list(field, "n")
    )


def _region_name(value: str) -> str | None:
    """A region's label; free text kept from before the list, tidied."""
    if not value:
        return None
    return dict(Region.choices).get(value) or value.strip().title()


def _stage_label(key: str) -> str:
    return STAGE_LABELS.get(key) or dict(StoneStatus.choices).get(key, key)


# --------------------------------------------------------------- building ---


def _payments():
    """Payments with the moment they were made and their currency.

    ``trx_dt_tm`` is the gateway's own timestamp; a row without one falls back
    to when it was recorded. A payment naming no currency is in its bill's.
    """
    default = Bill._meta.get_field("currency").default
    return Payment.objects.annotate(
        paid_on=Coalesce("trx_dt_tm", "created_at"),
        pay_currency=Coalesce(
            NullIf("currency", Value("")), "bill__currency", Value(default)
        ),
    )


def _bills():
    """Bills that stand - a cancelled bill never asked anyone for money."""
    return Bill.objects.exclude(status=BillStatus.CANCELLED).annotate(
        billed_on=Coalesce("issued_at", "created_at")
    )


def _orders_received(period: Period):
    return Order.objects.filter(received_date__range=(period.start, period.end))


def _stones_received(period: Period) -> int:
    return _orders_received(period).aggregate(n=Sum("stone_count"))["n"] or 0


def _certificates(period: Period):
    return _in(Certificate.objects.all(), "issued_at", period)


def _finalized_reports(period: Period):
    finalized = IdentificationReport.objects.filter(is_finalized=True)
    return _in(finalized, "identified_at", period)


def _collected(period: Period) -> dict[str, Decimal]:
    rows = (
        _in(_payments(), "paid_on", period)
        .order_by()
        .values("pay_currency")
        .annotate(total=Sum("paid_amount"))
    )
    return {row["pay_currency"]: row["total"] or Decimal(0) for row in rows}


def _turnarounds(period: Period) -> list[tuple[date, float]]:
    """``(day certified, days taken)`` for each stone certified in the period.

    The clock starts when reception registered the order - the moment the lab
    took the stones into its care - and stops when the stone was certified.
    """
    rows = _in(
        StatusHistory.objects.filter(
            to_status=StoneStatus.CERTIFIED, stone__deleted_at__isnull=True
        ),
        "changed_at",
        period,
    ).values_list("changed_at", "stone__order__created_at")
    return [
        (local_date(certified), _days(certified - registered))
        for certified, registered in rows
    ]


def _outstanding() -> list[dict]:
    """What open bills still ask for, per currency, as of now.

    Open means pending or partially paid; the balance is the bill's total less
    the payments recorded against it. The balance is aged by how long ago the
    bill was issued - receivables aging, the chase list. Not by due date:
    nothing sets ``Bill.due_date``, and the GePG expiry is a year out, so
    "overdue" would read zero on every real bill.

    Expired bills are counted apart - nothing collects on them any more, so
    they are a write-off question rather than a chase list.
    """
    now = timezone.now()

    def empty():
        return {
            "amount": Decimal(0),
            "bills": 0,
            "aging": [[Decimal(0), 0] for _ in RECEIVABLE_AGES],
            "expired_amount": Decimal(0),
            "expired_bills": 0,
        }

    totals: dict[str, dict] = defaultdict(empty)

    open_bills = (
        Bill.objects.filter(status__in=OPEN_BILLS)
        .order_by()
        .annotate(billed_on=Coalesce("issued_at", "created_at"))
        .values("id", "currency", "total_amount", "billed_on")
        .annotate(
            paid=Coalesce(
                Sum("payments__paid_amount", filter=Q(payments__deleted_at__isnull=True)),
                Value(Decimal(0)),
                output_field=DecimalField(),
            )
        )
    )
    for bill in open_bills:
        balance = max((bill["total_amount"] or Decimal(0)) - bill["paid"], Decimal(0))
        row = totals[bill["currency"]]
        row["amount"] += balance
        row["bills"] += 1
        age = int(_days(now - bill["billed_on"]))
        for index, (low, high, _) in enumerate(RECEIVABLE_AGES):
            if age >= low and (high is None or age <= high):
                row["aging"][index][0] += balance
                row["aging"][index][1] += 1

    expired = (
        Bill.objects.filter(status=BillStatus.EXPIRED)
        .order_by()
        .values("currency")
        .annotate(n=Count("id"), total=Sum("total_amount"))
    )
    for bill in expired:
        row = totals[bill["currency"]]
        row["expired_amount"] += bill["total"] or Decimal(0)
        row["expired_bills"] += bill["n"]

    return [
        {
            "currency": currency,
            "amount": _money(row["amount"]),
            "bills": row["bills"],
            "aging": [
                {"label": label, "amount": _money(amount), "bills": bills}
                for (_, _, label), (amount, bills) in zip(
                    RECEIVABLE_AGES, row["aging"], strict=True
                )
            ],
            "expired_amount": _money(row["expired_amount"]),
            "expired_bills": row["expired_bills"],
        }
        for currency, row in sorted(totals.items())
    ]


# ---------------------------------------------------------------- sections ---


def summary(period: Period) -> dict:
    """The KPI row: this period against the equally long one before it.

    - **Stones received** - stones handed in at reception.
    - **Certificates issued** - by ``issued_at``, revoked ones included: they
      were issued, and revocations are reported under volume.
    - **Revenue collected** - payments by the day they were made, per currency.
    - **Outstanding** - open bills' unpaid balance *as of now*, not bound to
      the period, so it has no "previous" to compare with.
    """
    previous = period.previous()
    collected, collected_before = _collected(period), _collected(previous)
    return {
        "range": period.as_dict(),
        "previous_range": previous.as_dict(),
        "stones_received": {
            "current": _stones_received(period),
            "previous": _stones_received(previous),
        },
        "certificates_issued": {
            "current": _certificates(period).count(),
            "previous": _certificates(previous).count(),
        },
        "revenue_collected": [
            {
                "currency": currency,
                "current": _money(collected.get(currency)),
                "previous": _money(collected_before.get(currency)),
            }
            for currency in sorted(collected.keys() | collected_before.keys())
        ],
        "outstanding": _outstanding(),
    }


def volume(period: Period) -> dict:
    """How much work came in and went out, per bucket.

    - **Orders / stones** - orders by ``received_date`` and the stones they
      brought.
    - **Certificates** - by ``issued_at``.
    - **New vs returning customers** - customers who handed something in during
      the bucket; *new* when that was their first order ever.
    - **Hold / cancel rate** - share of the period's orders now on hold or
      cancelled.
    - **Revoked** - certificates issued in the period that have since been
      revoked (a certificate records no revocation date).
    """
    orders = _orders_received(period)
    per_day = list(
        orders.order_by()
        .values("received_date")
        .annotate(n=Count("id"), stones=Sum("stone_count"))
    )
    order_counts = period.rollup((row["received_date"], row["n"]) for row in per_day)
    stone_counts = period.rollup((row["received_date"], row["stones"]) for row in per_day)
    certificate_counts = period.rollup(
        _certificates(period)
        .order_by()
        .annotate(day=lab_day("issued_at"))
        .values("day")
        .annotate(n=Count("id"))
        .values_list("day", "n")
    )

    visits = list(orders.values_list("customer_id", "received_date"))
    first_order = dict(
        Order.objects.filter(customer_id__in={customer for customer, _ in visits})
        .order_by()
        .values("customer_id")
        .annotate(first=Min("received_date"))
        .values_list("customer_id", "first")
    )
    customers_per_bucket: dict[date, set] = defaultdict(set)
    for customer, received in visits:
        customers_per_bucket[period.bucket(received)].add(customer)

    series = []
    for bucket in period.buckets():
        customers = customers_per_bucket.get(bucket, set())
        # A bucket can open before the period does; only a first order inside
        # both the bucket and the period makes a customer new here.
        since = max(bucket, period.start)
        new = sum(1 for customer in customers if first_order[customer] >= since)
        series.append(
            {
                "period": bucket.isoformat(),
                "orders": order_counts[bucket],
                "stones": stone_counts[bucket],
                "certificates": certificate_counts[bucket],
                "new_customers": new,
                "returning_customers": len(customers) - new,
            }
        )

    everyone = {customer for customer, _ in visits}
    new_total = sum(1 for customer in everyone if first_order[customer] >= period.start)
    total_orders = sum(order_counts.values())
    on_hold = orders.filter(hold_status=OrderHold.ON_HOLD).count()
    cancelled = orders.filter(hold_status=OrderHold.CANCELLED).count()
    return {
        "range": period.as_dict(),
        "series": series,
        "totals": {
            "orders": total_orders,
            "stones": sum(stone_counts.values()),
            "certificates": sum(certificate_counts.values()),
            "new_customers": new_total,
            "returning_customers": len(everyone) - new_total,
        },
        "orders_on_hold": on_hold,
        "orders_cancelled": cancelled,
        "hold_rate": _rate(on_hold, total_orders),
        "cancel_rate": _rate(cancelled, total_orders),
        "certificates_revoked": _certificates(period)
        .filter(status=CertificateStatus.REVOKED)
        .count(),
    }


def revenue(period: Period) -> dict:
    """Money billed and collected, and money still owed - per currency.

    - **Collected** - payments by the day they were made.
    - **Billed** - bills by the day they were issued, cancelled ones excluded.
    - **Collection rate** - collected ÷ billed over the period. The two sets of
      money overlap only partly (a bill issued in March may be paid in April),
      so read it as a trend rather than a ratio of the same bills.
    - **Average fee per stone** - mean bill line over bills issued in the period.
    - **Outstanding (aged) / expired** - as of now; see :func:`_outstanding`.
    - **Payment lag** - days from a bill being issued to its first payment,
      for bills first paid in the period.
    - **Channels** - payments in the period by the institution that took them.
    """
    payments = _in(_payments(), "paid_on", period)
    bills = _in(_bills(), "billed_on", period)

    collected: dict[str, list] = defaultdict(list)
    for row in (
        payments.order_by()
        .annotate(day=lab_day("paid_on"))
        .values("pay_currency", "day")
        .annotate(total=Sum("paid_amount"))
    ):
        collected[row["pay_currency"]].append((row["day"], row["total"]))

    billed: dict[str, list] = defaultdict(list)
    for row in (
        bills.order_by()
        .annotate(day=lab_day("billed_on"))
        .values("currency", "day")
        .annotate(total=Sum("total_amount"))
    ):
        billed[row["currency"]].append((row["day"], row["total"]))

    fees = {
        row["bill__currency"]: row["average"]
        for row in BillItem.objects.filter(bill__in=bills.values("id"))
        .order_by()
        .values("bill__currency")
        .annotate(average=Avg("amount"))
    }
    outstanding = {row["currency"]: row for row in _outstanding()}

    by_currency = []
    for currency in sorted(collected.keys() | billed.keys() | outstanding.keys()):
        collected_series = period.rollup(collected[currency])
        billed_series = period.rollup(billed[currency])
        total_collected = sum(collected_series.values())
        total_billed = sum(billed_series.values())
        by_currency.append(
            {
                "currency": currency,
                "collected": _money(total_collected),
                "billed": _money(total_billed),
                "collection_rate": _rate(total_collected, total_billed),
                "average_fee_per_stone": (
                    _money(fees[currency]) if fees.get(currency) is not None else None
                ),
                "series": [
                    {
                        "period": bucket.isoformat(),
                        "collected": _money(collected_series[bucket]),
                        "billed": _money(billed_series[bucket]),
                    }
                    for bucket in period.buckets()
                ],
                "outstanding": outstanding.get(currency),
            }
        )

    start, end = period.bounds()
    first_payments = (
        Bill.objects.order_by()
        .annotate(
            billed_on=Coalesce("issued_at", "created_at"),
            first_paid=Min(
                Coalesce("payments__trx_dt_tm", "payments__created_at"),
                filter=Q(payments__deleted_at__isnull=True),
            ),
        )
        .filter(first_paid__gte=start, first_paid__lt=end)
        .values_list("billed_on", "first_paid")
    )

    return {
        "range": period.as_dict(),
        "by_currency": by_currency,
        "payment_lag_days": _describe(
            [_days(paid - issued) for issued, paid in first_payments]
        ),
        "channels": _top(
            payments.order_by()
            .values("psp_name")
            .annotate(n=Count("id"))
            .values_list("psp_name", "n")
        ),
        "unprocessed_payments": Payment.objects.filter(is_processed=False).count(),
    }


def turnaround(period: Period) -> dict:
    """How long the work takes, where it waits, and who does it.

    - **Turnaround** - see :func:`_turnarounds`; median, mean and 90th
      percentile, overall and per bucket.
    - **Stages** - time spent waiting in each stage; see :func:`_stages`.
    - **Aging** - what is in the lab *now*, by how long it has waited in its
      current stage; see :func:`_aging`.
    - **Workload** - findings finalized per gemmologist and certificates issued
      per officer in the period.
    """
    certified = _turnarounds(period)
    per_bucket: dict[date, list[float]] = defaultdict(list)
    for day, days in certified:
        per_bucket[period.bucket(day)].append(days)

    return {
        "range": period.as_dict(),
        "certified_stones": len(certified),
        "turnaround_days": _describe([days for _, days in certified]),
        "series": [
            {
                "period": bucket.isoformat(),
                "median_days": _describe(per_bucket.get(bucket, []))["median"],
                "stones": len(per_bucket.get(bucket, [])),
            }
            for bucket in period.buckets()
        ],
        "stages": _stages(period),
        "aging": _aging(),
        "workload": {
            "reports": _by_person(_finalized_reports(period), "identified_by"),
            "certificates": _by_person(_certificates(period), "issued_by"),
        },
    }


def _stages(period: Period) -> list[dict]:
    """Time spent in each stage, for moves out of that stage made in the period.

    Read off consecutive ``StatusHistory`` rows: a stone's stay in a status runs
    from the row that moved it in to the row that moved it out. The first stage
    has no row to start from - it runs from registering the order to the row
    that created the stone, which is when the bench identified it.
    """
    start, end = period.bounds()
    history = StatusHistory.objects.filter(stone__deleted_at__isnull=True)
    moved = history.filter(changed_at__gte=start, changed_at__lt=end).values("stone_id")
    rows = (
        history.filter(stone_id__in=moved)
        .order_by("stone_id", "changed_at", "id")
        .values_list("stone_id", "from_status", "changed_at", "stone__order__created_at")
    )

    durations: dict[str, list[float]] = defaultdict(list)
    entered: dict[int, object] = {}
    for stone_id, from_status, changed_at, registered in rows:
        # A move out of a status whose entry predates the history (legacy rows)
        # has no start; it is skipped rather than guessed.
        began = entered.get(stone_id) if from_status else registered
        if began is not None and start <= changed_at < end:
            durations[from_status or AWAITING_IDENTIFICATION].append(
                _days(changed_at - began)
            )
        entered[stone_id] = changed_at

    result = []
    for key in STAGE_ORDER:
        values = durations.get(key)
        if values:
            described = _describe(values)
            result.append(
                {
                    "key": key,
                    "label": _stage_label(key),
                    "median_days": described["median"],
                    "average_days": described["average"],
                    "stones": len(values),
                }
            )
    return result


def _aging() -> list[dict]:
    """Work in the lab now, by whole days waited in its current stage.

    A stone's wait starts at its latest status change. Stones reception has
    taken in but the bench has not identified yet have no row of their own, so
    they are the gap between an active order's ``stone_count`` and the stones
    recorded against it, waiting since the order was registered.
    """
    now = timezone.now()
    last_move = (
        StatusHistory.objects.filter(stone=OuterRef("pk"))
        .order_by("-changed_at")
        .values("changed_at")[:1]
    )
    waits: dict[str, list[int]] = defaultdict(list)
    for status, since in (
        Stone.objects.filter(status__in=LIVE_STATUSES)
        .exclude(order__hold_status=OrderHold.CANCELLED)
        .annotate(since=Coalesce(Subquery(last_move), "created_at"))
        .values_list("status", "since")
    ):
        waits[status].append(int(_days(now - since)))

    unidentified = (
        Order.objects.filter(hold_status=OrderHold.ACTIVE)
        .annotate(identified=Count("stones", filter=Q(stones__deleted_at__isnull=True)))
        .filter(stone_count__gt=F("identified"))
        .values_list("stone_count", "identified", "created_at")
    )
    for count, identified, registered in unidentified:
        waits[AWAITING_IDENTIFICATION].extend(
            [int(_days(now - registered))] * (count - identified)
        )

    result = []
    for key in STAGE_ORDER:
        values = waits.get(key)
        if values:
            result.append(
                {
                    "key": key,
                    "label": _stage_label(key),
                    "total": len(values),
                    "buckets": [
                        {
                            "label": label,
                            "status": status,
                            "count": sum(
                                1
                                for days in values
                                if days >= low and (high is None or days <= high)
                            ),
                        }
                        for low, high, label, status in AGE_BUCKETS
                    ],
                }
            )
    return result


def _by_person(queryset, field: str) -> list[dict]:
    """Row counts per user in ``field``, busiest first.

    Names are read through the base manager: someone who has since left and
    been deactivated still did the work they did.
    """
    counts = dict(_counted(queryset, field))
    user_model = get_user_model()
    names = {
        user.pk: user.full_name
        for user in user_model._base_manager.filter(pk__in=[pk for pk in counts if pk])
    }
    return _top(
        ((names.get(pk) if pk else None, n) for pk, n in counts.items()),
        limit=50,
    )


def market(period: Period) -> dict:
    """What the lab is seeing: the market behind the work.

    - **Species / varieties / origins / nature / treatments** - over findings
      finalized in the period (by ``identified_at``).
    - **Stone types** - stones identified in the period, by type.
    - **Regions** - stones received in the period, by the customer's region.
    """
    reports = _finalized_reports(period)
    regions = (
        _orders_received(period)
        .order_by()
        .values("customer__region")
        .annotate(n=Sum("stone_count"))
        .values_list("customer__region", "n")
    )
    return {
        "range": period.as_dict(),
        "reports": reports.count(),
        "species": _top(_counted(reports, "species__name")),
        "varieties": _top(_counted(reports, "variety__name")),
        "origins": _top(_counted(reports, "origin__name")),
        "nature": _labelled(_counted(reports, "nature_type"), NatureType),
        "treatments": _labelled(_counted(reports, "treatment"), Treatment),
        "stone_types": _top(
            _counted(_in(Stone.objects.all(), "created_at", period), "stone_type__name")
        ),
        "regions": _top((_region_name(region), n) for region, n in regions),
    }
