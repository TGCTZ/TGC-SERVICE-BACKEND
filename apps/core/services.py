"""Shared service helpers available to every app."""

from django.db.models import Max


def generate_reference_number(model, field: str, prefix: str, *, width: int = 4) -> str:
    """Return the next human-readable reference, e.g. ``ORD-2026-0001``.

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
    from django.utils import timezone

    year = timezone.now().year
    stem = f"{prefix}-{year}-"
    latest = (
        model.all_objects.filter(**{f"{field}__startswith": stem})
        .aggregate(peak=Max(field))
        .get("peak")
    )
    sequence = int(latest.rsplit("-", 1)[1]) + 1 if latest else 1
    return f"{stem}{sequence:0{width}d}"


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


def generate_tgc_report_number(model, field: str, *, width: int = 4) -> str:
    """Return the next TGC reference, e.g. ``TGC/2026/2027/0765``.

    The shape the lab already issues on paper: lab code, financial year pair,
    sequence. Kept separate from :func:`generate_reference_number` rather than
    parameterised into it - the separator, the two-year component and the reset
    rule all differ, and one function serving both would be a thicket of flags.

    **The sequence never resets.** The legacy system took it from the order
    number's digits instead, which meant every stone in a multi-stone order was
    handed the same report number; a single ever-increasing counter avoids that
    while keeping the printed shape identical. It follows that the number in a
    ``2027/2028`` reference continues from where ``2026/2027`` left off, which is
    intended - the year pair says when, the sequence says how many.

    Only rows already in this format are scanned, so references left over from an
    earlier scheme are ignored rather than parsed and misread.

    Args:
        model: The model class to scan.
        field: Name of the field holding the reference.
        width: Zero-padded width of the sequence component.
    """
    start, end = financial_year()
    latest = (
        model.all_objects.filter(**{f"{field}__startswith": "TGC/"})
        .aggregate(peak=Max(field))
        .get("peak")
    )
    # Max() orders lexically, which is what we want only because the sequence is
    # zero-padded to a fixed width - hence `width` being fixed rather than a
    # per-call whim.
    sequence = int(latest.rsplit("/", 1)[1]) + 1 if latest else 1
    return f"TGC/{start}/{end}/{sequence:0{width}d}"
