"""Behavior shared by the four mixed workflow feeds."""

from types import SimpleNamespace

import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.core.workflow_feed import feed_row, paginated_workflow_feed

pytestmark = pytest.mark.django_db


def _view(request):
    """Small paginator stub so these tests exercise the shared feed contract."""
    view = SimpleNamespace()
    view.paginate_queryset = lambda rows: rows[
        (int(request.query_params.get("page", 1)) - 1)
        * int(request.query_params.get("page_size", 10)) : int(
            request.query_params.get("page", 1)
        )
        * int(request.query_params.get("page_size", 10))
    ]
    view.get_paginated_response = lambda rows: rows
    return view


def _row(pk, *, waiting, date, reference=None, status="Ready", detail=None):
    return feed_row(
        kind="order",
        record_id=pk,
        reference=reference or f"ORD-{pk}",
        customer=f"Customer {pk}",
        type_name="Order",
        status=status,
        date=date,
        waiting=waiting,
        detail=detail or {},
    )


def test_waiting_records_precede_newest_completed_records():
    """Waiting rows lead; completed rows then use descending date order."""
    rows = [
        _row(1, waiting=False, date="2026-10-04"),
        _row(2, waiting=True, date="2026-09-01"),
        _row(3, waiting=False, date="2026-10-05"),
    ]
    request = Request(APIRequestFactory().get("/", {"page_size": 10}))

    result = paginated_workflow_feed(_view(request), rows, request)

    assert [row["record_id"] for row in result] == [2, 3, 1]


def test_search_status_type_filter_and_pagination_apply_to_the_combined_rows():
    """All common filters run before slicing the shared page."""
    rows = [
        _row(
            1,
            waiting=True,
            date="2026-10-01",
            reference="ORD-A",
            status="Identifying",
            detail={"control_number": "CN-ABC"},
        ),
        _row(2, waiting=False, date="2026-10-02", reference="ORD-B", status="Ready"),
    ]
    request = Request(
        APIRequestFactory().get(
            "/",
            {
                "search": "cn-abc",
                "status": "Identifying",
                "type": "Order",
                "source": "waiting",
                "page_size": 1,
            },
        )
    )

    result = paginated_workflow_feed(_view(request), rows, request)

    assert [row["record_id"] for row in result] == [1]


def test_search_and_status_filters_remove_nonmatching_mixed_rows():
    """A filter that misses one row removes it from the mixed result."""
    rows = [
        _row(1, waiting=True, date="2026-10-01", reference="ORD-A", status="Identifying"),
        _row(2, waiting=False, date="2026-10-02", reference="ORD-B", status="Ready"),
    ]
    request = Request(
        APIRequestFactory().get("/", {"search": "absent", "status": "Ready"})
    )

    result = paginated_workflow_feed(_view(request), rows, request)

    assert result == []
