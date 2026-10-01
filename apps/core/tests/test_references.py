"""The one reference shape every document in the system carries."""

import re
from datetime import datetime

import pytest

from apps.core import services
from apps.core.services import financial_year, generate_reference_number
from apps.orders.models import Order
from apps.orders.tests.factories import OrderFactory

pytestmark = pytest.mark.django_db


def _stem() -> str:
    """This financial year as it appears in a reference, e.g. ``2627``."""
    start, end = financial_year()
    return f"{start % 100:02d}{end % 100:02d}"


def test_financial_year_runs_july_to_june():
    """The lab reports on a July-June year, so August and March share one."""
    assert financial_year(datetime(2026, 8, 1)) == (2026, 2027)
    assert financial_year(datetime(2027, 3, 1)) == (2026, 2027)

    # The boundaries themselves, which is where an off-by-one would hide.
    assert financial_year(datetime(2026, 6, 30)) == (2025, 2026)
    assert financial_year(datetime(2026, 7, 1)) == (2026, 2027)


def test_every_reference_takes_the_same_shape():
    """PREFIX-<fy>-NNNNN, whatever the document is.

    Asserted as a shape rather than against today's calendar, since the year pair
    moves. The point is that one regex matches all of them - a number read aloud
    is recognisable without knowing which document it came from.
    """
    stem = _stem()
    for prefix in ("ORD", "BILL", "CERT", "TGC"):
        number = generate_reference_number(Order, "reference_number", prefix)
        assert re.fullmatch(rf"{prefix}-\d{{4}}-\d{{5}}", number)
        assert number.startswith(f"{prefix}-{stem}-")

    # No slashes anywhere: these end up in filenames and URL path segments.
    assert "/" not in generate_reference_number(Order, "reference_number", "TGC")


def test_the_sequence_counts_up_within_a_financial_year():
    """Each new document takes the next number, soft-deleted ones included."""
    stem = _stem()
    OrderFactory(reference_number=f"ORD-{stem}-00007")

    assert generate_reference_number(Order, "reference_number", "ORD") == (
        f"ORD-{stem}-00008"
    )

    # A soft-deleted order still holds its number: `all_objects` is scanned, so
    # a number is never handed out twice.
    OrderFactory(reference_number=f"ORD-{stem}-00008").delete()
    assert generate_reference_number(Order, "reference_number", "ORD") == (
        f"ORD-{stem}-00009"
    )


def test_the_sequence_runs_past_the_old_four_digit_ceiling():
    """Four digits capped a year at 9,999 of each document; five lifts that.

    The step that matters is the rollover: the 10,000th number must still be
    five digits wide, so it keeps sorting after every earlier one - `Max()`
    compares these as text.
    """
    stem = _stem()
    OrderFactory(reference_number=f"ORD-{stem}-09999")

    assert generate_reference_number(Order, "reference_number", "ORD") == (
        f"ORD-{stem}-10000"
    )


def test_the_sequence_restarts_each_financial_year(monkeypatch):
    """The year pair says when, the sequence says how many since July."""
    OrderFactory(reference_number="ORD-2627-00042")

    monkeypatch.setattr(services, "financial_year", lambda when=None: (2026, 2027))
    assert generate_reference_number(Order, "reference_number", "ORD") == (
        "ORD-2627-00043"
    )

    # July arrives: a new year pair is a new stem, so the scan finds nothing to
    # continue from and the count starts over rather than running on at 00044.
    monkeypatch.setattr(services, "financial_year", lambda when=None: (2027, 2028))
    assert generate_reference_number(Order, "reference_number", "ORD") == (
        "ORD-2728-00001"
    )


def test_prefixes_do_not_borrow_each_other_s_sequence():
    """Each document type counts on its own, even sharing a table."""
    stem = _stem()
    OrderFactory(reference_number=f"ORD-{stem}-00050")

    assert generate_reference_number(Order, "reference_number", "CERT") == (
        f"CERT-{stem}-00001"
    )


def test_the_year_pair_is_written_as_four_digits(monkeypatch):
    """2026/2027 reads `2627` - short enough to say over a counter."""
    monkeypatch.setattr(services, "financial_year", lambda when=None: (2026, 2027))
    assert generate_reference_number(Order, "reference_number", "ORD") == (
        "ORD-2627-00001"
    )

    # A year ending in 0x keeps its leading zero, or the segment would shrink to
    # three digits and stop sorting against its neighbours.
    monkeypatch.setattr(services, "financial_year", lambda when=None: (2029, 2030))
    assert generate_reference_number(Order, "reference_number", "ORD") == (
        "ORD-2930-00001"
    )
    monkeypatch.setattr(services, "financial_year", lambda when=None: (2099, 2100))
    assert generate_reference_number(Order, "reference_number", "ORD") == (
        "ORD-9900-00001"
    )
