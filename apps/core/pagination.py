"""Project-wide pagination."""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Page-number pagination with a client-controllable, capped page size.

    Emits DRF's standard envelope - ``count``, ``next``, ``previous``,
    ``results`` - so generated clients and drf-spectacular need no
    special-casing.
    """

    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 100
