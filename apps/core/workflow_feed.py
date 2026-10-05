"""Shared in-memory normalization for mixed workflow pages.

The feeds are deliberately read-only projections. Mutations still go through
the owning resource endpoints, where the existing workflow permissions apply.
"""


def paginated_workflow_feed(view, records, request):
    """Filter, globally order, and paginate normalized workflow records."""
    params = request.query_params
    search = params.get("search", "").strip().casefold()
    status_filter = params.get("status")
    type_filter = params.get("type")
    source_filter = params.get("source")
    rows = records
    if search:

        def searchable_values(value):
            """Include searchable resource fields such as control numbers."""
            if isinstance(value, dict):
                return " ".join(searchable_values(item) for item in value.values())
            if isinstance(value, (list, tuple)):
                return " ".join(searchable_values(item) for item in value)
            return str(value or "")

        rows = [row for row in rows if search in searchable_values(row).casefold()]
    if status_filter:
        rows = [row for row in rows if row["status"] == status_filter]
    if type_filter:
        rows = [row for row in rows if row["type"] == type_filter]
    if source_filter == "waiting":
        rows = [row for row in rows if row["waiting"]]
    elif source_filter == "records":
        rows = [row for row in rows if not row["waiting"]]

    sort = params.get("sort", "")
    reverse = sort.startswith("-")
    key = sort.lstrip("-")
    if key in {"reference", "customer", "type", "status", "date"}:
        rows.sort(key=lambda row: str(row[key] or "").casefold(), reverse=reverse)
    else:
        # Pending work leads by default; records then follow newest-first.
        rows.sort(key=lambda row: str(row["date"] or ""), reverse=True)
        rows.sort(key=lambda row: not row["waiting"])

    page = view.paginate_queryset(rows)
    return view.get_paginated_response(page)


def feed_row(
    *, kind, record_id, reference, customer, type_name, status, date, waiting, detail
):
    """Create a stable common row shape while preserving resource detail."""
    return {
        "id": f"{kind}:{record_id}",
        "kind": kind,
        "record_id": record_id,
        "reference": reference or "—",
        "customer": customer or "—",
        "type": type_name,
        "status": str(status),
        "date": date.isoformat() if hasattr(date, "isoformat") else date,
        "waiting": waiting,
        "detail": detail,
    }
