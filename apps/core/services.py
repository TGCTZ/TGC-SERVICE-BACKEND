"""Shared service helpers available to every app."""

from django.db.models import Max


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
    """Return the next human-readable reference, e.g. ``ORD-2627-00001``.

    One shape for every identifier the system issues - orders, bills, reports and
    certificates - so a number read aloud or typed into a search box is
    recognisable without knowing which document it came from. Reports used to
    carry slashes (``TGC/2026/2027/0765``), which made them unsafe in a filename
    or a URL path segment; the separator is now a dash everywhere.

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
