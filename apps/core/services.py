"""Shared service helpers available to every app."""

import re

from django.db.models import Max

_ORDER_REFERENCE_RE = re.compile(r"^ORD-(\d{4})-(\d{1,5})$")
_DISPLAY_REFERENCE_RE = re.compile(
    r"^(?P<prefix>[A-Z]+)-(?P<year>\d{4})-(?P<sequence>\d{1,5})(?P<label>-[A-Za-z0-9]+)?$"
)


def financial_year(when=None) -> tuple[int, int]:
    """The Tanzanian financial year containing ``when``, as ``(start, end)``.

    Runs July to June, so a date in August 2026 falls in 2026/2027 and a date in
    March 2027 falls in the same one. Ported from the legacy system's
    ``reception_app/lib.py``, which is what has been printing these year pairs on
    certificates to date.

    Args:
        when: The moment to place. Defaults to now.
    """
    from django.utils import timezone

    moment = when or timezone.now()
    if moment.month >= 7:
        return moment.year, moment.year + 1
    return moment.year - 1, moment.year


def generate_reference_number(model, field: str, prefix: str, *, width: int = 5) -> str:
    """Allocate the next order sequence, e.g. ``ORD-2627-00001``.

    Related bill, findings, and certificate numbers derive their year and
    sequence from the order instead of maintaining their own counters.

    The year component is the financial year rather than the calendar one,
    because that is the period the lab reports on, and the sequence restarts with
    it - the year pair says when, the sequence says how many since July. Both
    years are written as two digits, so 2026/2027 reads ``2627``: short enough to
    say over a counter and to fit a printed line, and still unambiguous for a lab
    whose records do not reach back to 1926.

    Scans ``all_objects`` rather than the default manager so a soft-deleted
    record never has its number handed out a second time. This is a
    read-then-write, so the caller's model needs a unique constraint on
    ``field`` as the backstop against a concurrent duplicate.

    Args:
        model: The model class to scan.
        field: Name of the field holding the reference.
        prefix: Short uppercase prefix, e.g. ``"ORD"``.
        width: Zero-padded width of the sequence component.
    """
    start, end = financial_year()
    stem = f"{prefix}-{start % 100:02d}{end % 100:02d}-"
    latest = (
        model.all_objects.filter(**{f"{field}__startswith": stem})
        .aggregate(peak=Max(field))
        .get("peak")
    )
    # Max() orders lexically, which is what we want only because the sequence is
    # zero-padded to a fixed width - hence `width` being fixed rather than a
    # per-call whim. It is also why changing `width` needs a clean sequence: with
    # "0010" and "00011" in the same year, "0010" sorts higher, the scan keeps
    # returning 11, and the unique constraint rejects the duplicate. Five digits
    # (99,999 a year per document type) replaced four on a flushed database.
    sequence = int(latest.rsplit("-", 1)[1]) + 1 if latest else 1
    return f"{stem}{sequence:0{width}d}"


def reference_number_for_order(
    order, prefix: str, *, stone_label: str | None = None
) -> str:
    """Build a related document reference from its order's year and sequence.

    Order numbers are the sequence source of truth. Bills share the order number
    at order level; findings and certificates add the stone label so each
    per-stone record remains distinguishable.
    """
    match = _ORDER_REFERENCE_RE.fullmatch(order.reference_number)
    if match is None:
        raise ValueError(
            f"Order reference {order.reference_number!r} does not contain a valid "
            "year and sequence."
        )

    year, sequence = match.groups()
    reference = f"{prefix}-{year}-{int(sequence):05d}"
    return f"{reference}-{stone_label}" if stone_label else reference


def format_reference_number(value: str | None) -> str | None:
    """Format a stored reference's financial year for people, not integrations.

    Stored identifiers deliberately remain slash-free so they are safe as
    GePG values, filenames, and verification URL path segments.
    """
    if value is None:
        return None
    match = _DISPLAY_REFERENCE_RE.fullmatch(value)
    if match is None:
        return value

    prefix = match.group("prefix")
    year = match.group("year")
    sequence = match.group("sequence")
    label = match.group("label") or ""
    return f"{prefix}-{year[:2]}/{year[2:]}-{sequence}{label}"
