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
