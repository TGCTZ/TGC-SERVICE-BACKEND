"""Management statistics: who may read them, how periods work, what is counted."""

import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from django.core.management import call_command
from django.utils import timezone

from apps.analytics import selectors
from apps.analytics.periods import DAY, MONTH, WEEK, Period, local_date
from apps.billing.models import Bill, Payment
from apps.gems.enums import BillStatus, StoneStatus
from apps.gems.tests.factories import SpeciesFactory
from apps.identification.models import IdentificationReport
from apps.orders.models import Order, StatusHistory
from apps.orders.tests.factories import CustomerFactory, OrderFactory, StoneFactory

pytestmark = pytest.mark.django_db

LAB = ZoneInfo("Africa/Dar_es_Salaam")
SECTIONS = ("summary", "volume", "revenue", "turnaround", "market")
JANUARY = Period(date(2026, 1, 1), date(2026, 1, 31))


def at(day: date, hour: int = 12) -> datetime:
    """A time of day on a lab-calendar day, as an aware datetime."""
    return datetime(day.year, day.month, day.day, hour, tzinfo=LAB)


def _bill(currency="TZS", total="1000", status=BillStatus.PENDING, issued=None, due=None):
    order = OrderFactory()
    return Bill.objects.create(
        order=order,
        bill_number=f"BILL-{order.pk}",
        currency=currency,
        total_amount=Decimal(total),
        status=status,
        issued_at=issued,
        due_date=due,
    )


def _pay(bill, amount, when):
    return Payment.objects.create(
        bill=bill,
        paid_amount=Decimal(amount),
        currency=bill.currency,
        trx_dt_tm=when,
        psp_name="CRDB",
    )


# ------------------------------------------------------------- access ---


@pytest.mark.parametrize("section", SECTIONS)
def test_statistics_need_their_own_permission(
    section, auth_client, viewer_user, admin_user
):
    """Reception can read orders and bills, but not the lab's whole picture."""
    url = f"/api/v1/analytics/{section}/"

    assert auth_client(viewer_user).get(url).status_code == 403
    assert auth_client(admin_user).get(url).status_code == 200


def test_a_backwards_or_overlong_range_is_refused(auth_client, admin_user):
    """A range must run forwards and stay within what is cheap to compute."""
    client = auth_client(admin_user)
    url = "/api/v1/analytics/summary/"

    assert client.get(url, {"from": "2026-02-01", "to": "2026-01-01"}).status_code == 400
    assert client.get(url, {"from": "2020-01-01", "to": "2026-01-01"}).status_code == 400


# ------------------------------------------------------------ periods ---


def test_the_bucket_size_follows_the_length_of_the_range():
    """A chart should never have three bars, nor three hundred."""
    assert JANUARY.granularity == DAY
    assert len(JANUARY.buckets()) == 31

    quarter = Period(date(2026, 1, 1), date(2026, 3, 31))
    assert quarter.granularity == WEEK
    # 1 January 2026 is a Thursday; its ISO week opens on the Monday before.
    assert quarter.buckets()[0] == date(2025, 12, 29)

    year = Period(date(2026, 1, 1), date(2026, 12, 31))
    assert year.granularity == MONTH
    assert len(year.buckets()) == 12


def test_quiet_buckets_are_zeros_not_gaps():
    """A missing day would let the chart draw its line straight across it."""
    OrderFactory(received_date=date(2026, 1, 10), stone_count=2)

    series = selectors.volume(JANUARY)["series"]

    assert len(series) == 31
    assert series[0]["orders"] == 0
    assert [row["stones"] for row in series if row["stones"]] == [2]


def test_days_are_counted_on_the_lab_calendar_not_utc():
    """22:30 UTC on 31 January is already 1 February in Dar es Salaam."""
    _pay(_bill(), "500", datetime(2026, 1, 31, 22, 30, tzinfo=ZoneInfo("UTC")))
    february = Period(date(2026, 2, 1), date(2026, 2, 28))

    assert selectors.summary(JANUARY)["revenue_collected"] == []
    assert selectors.summary(february)["revenue_collected"][0]["current"] == 500.0


# ------------------------------------------------------------ revenue ---


def test_money_is_never_added_across_currencies():
    """A total of shillings plus dollars is not a number."""
    issued = at(date(2026, 1, 5))
    _pay(_bill("TZS", "100000", issued=issued), "60000", at(date(2026, 1, 6)))
    _pay(_bill("USD", "40", issued=issued), "40", at(date(2026, 1, 7)))

    rows = {row["currency"]: row for row in selectors.revenue(JANUARY)["by_currency"]}

    assert (rows["TZS"]["collected"], rows["TZS"]["billed"]) == (60000.0, 100000.0)
    assert rows["TZS"]["collection_rate"] == 0.6
    assert (rows["USD"]["collected"], rows["USD"]["billed"]) == (40.0, 40.0)


def test_outstanding_is_what_open_bills_still_ask_for():
    """Balance after payments, aged by issue date; expired bills kept apart."""
    now = timezone.now()
    part_paid = _bill(
        total="1000", status=BillStatus.PARTIALLY_PAID, issued=now - timedelta(days=40)
    )
    _pay(part_paid, "400", now)
    _bill(total="500", status=BillStatus.PENDING, issued=now - timedelta(days=2))
    _bill(total="900", status=BillStatus.PAID, issued=now)
    _bill(total="300", status=BillStatus.EXPIRED, issued=now)

    [row] = selectors.summary(JANUARY)["outstanding"]

    assert (row["amount"], row["bills"]) == (1100.0, 2)
    assert [bucket["amount"] for bucket in row["aging"]] == [500.0, 0.0, 600.0, 0.0]
    assert (row["expired_amount"], row["expired_bills"]) == (300.0, 1)


# --------------------------------------------------------- turnaround ---


def test_stage_durations_are_read_off_the_status_history():
    """Each stay runs from the move in to the move out; the first from the order."""
    registered = at(date(2026, 1, 1))
    order = OrderFactory(received_date=registered.date())
    Order.objects.filter(pk=order.pk).update(created_at=registered)
    stone = StoneFactory(order=order, status=StoneStatus.CERTIFIED)

    moves = (
        ("", StoneStatus.RECEIVED, 1),
        (StoneStatus.RECEIVED, StoneStatus.BILLED, 2),
        (StoneStatus.BILLED, StoneStatus.PAID, 5),
        (StoneStatus.PAID, StoneStatus.CERTIFIED, 6),
    )
    for from_status, to_status, day in moves:
        row = StatusHistory.objects.create(
            stone=stone, from_status=from_status, to_status=to_status
        )
        # changed_at is auto_now_add, so the timeline is written afterwards.
        StatusHistory.objects.filter(pk=row.pk).update(
            changed_at=registered + timedelta(days=day)
        )

    result = selectors.turnaround(JANUARY)

    assert {stage["key"]: stage["median_days"] for stage in result["stages"]} == {
        "identification": 1.0,
        "received": 1.0,
        "billed": 3.0,
        "paid": 1.0,
    }
    assert result["turnaround_days"]["median"] == 6.0


def test_work_in_the_lab_is_aged_against_the_usual_one_to_three_days():
    """A stage should clear within a day; two to three is a warning, four is late."""
    now = timezone.now()
    order = OrderFactory(stone_count=3)
    Order.objects.filter(pk=order.pk).update(created_at=now - timedelta(hours=5))
    waiting = StoneFactory(order=order, status=StoneStatus.BILLED)
    row = StatusHistory.objects.create(
        stone=waiting, from_status=StoneStatus.RECEIVED, to_status=StoneStatus.BILLED
    )
    StatusHistory.objects.filter(pk=row.pk).update(changed_at=now - timedelta(days=5))

    aging = {row["key"]: row for row in selectors.turnaround(JANUARY)["aging"]}

    def counts(key):
        return {
            b["label"]: (b["count"], b["status"])
            for b in aging[key]["buckets"]
            if b["count"]
        }

    # Billed five days ago and still unpaid: overdue.
    assert counts("billed") == {"4-7 days": (1, "late")}
    # Two of the order's three stones are not identified yet, five hours in.
    assert counts("identification") == {"Under 1 day": (2, "normal")}


# ---------------------------------------------------- volume and market ---


def test_a_customer_is_new_only_in_the_period_of_their_first_order():
    """Back for a second visit is returning, even when the first was last year."""
    regular = CustomerFactory()
    OrderFactory(customer=regular, received_date=date(2025, 12, 1))
    OrderFactory(customer=regular, received_date=date(2026, 1, 12))
    OrderFactory(received_date=date(2026, 1, 20))

    totals = selectors.volume(JANUARY)["totals"]

    assert (totals["new_customers"], totals["returning_customers"]) == (1, 1)


def test_the_market_mix_keeps_ten_names_and_folds_the_rest_into_other():
    """A chart of thirty slivers answers nothing; the tail is summed instead."""
    for index in range(12):
        species = SpeciesFactory(name=f"Species {index:02d}")
        for copy in range(2 if index < 10 else 1):
            IdentificationReport.objects.create(
                stone=StoneFactory(),  # one report per stone, by constraint
                report_number=f"RPT-{index:02d}-{copy}",
                species=species,
                is_finalized=True,
                identified_at=at(date(2026, 1, 15)),
            )

    rows = selectors.market(JANUARY)["species"]

    assert len(rows) == 11
    assert rows[0] == {"name": "Species 00", "count": 2}
    assert rows[-1] == {"name": "Other", "count": 2}


def test_soft_deleted_orders_are_in_no_statistic():
    """A deleted order was a mistake, not work the lab did."""
    OrderFactory(received_date=date(2026, 1, 10), stone_count=2)
    OrderFactory(received_date=date(2026, 1, 10), stone_count=5).delete()

    assert selectors.summary(JANUARY)["stones_received"]["current"] == 2


# ------------------------------------------------------------ dev data ---


def test_seeded_history_gives_every_section_something_to_show():
    """``seed --history-months`` is how the dashboard is looked at in dev."""
    random.seed(7)  # the seed command draws from the module-level generator
    call_command("seed", users=0, orders=40, history_months=6, verbosity=0)
    today = local_date(timezone.now())
    period = Period(today - timedelta(days=200), today)

    turnaround = selectors.turnaround(period)
    revenue = selectors.revenue(period)
    market = selectors.market(period)

    assert turnaround["certified_stones"] > 0
    assert {stage["key"] for stage in turnaround["stages"]} >= {
        "identification",
        "received",
        "billed",
        "paid",
    }
    assert revenue["by_currency"][0]["collected"] > 0
    assert len(revenue["channels"]) > 1
    assert market["species"] and market["regions"]
    # Spread over months, not stacked on today.
    assert sum(1 for row in selectors.volume(period)["series"] if row["orders"]) > 3
