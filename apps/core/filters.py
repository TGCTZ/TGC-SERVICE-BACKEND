"""Whitelist-driven filtering, searching and ordering.

One filter backend serves every list endpoint. Rather than declaring a
FilterSet per model, each ViewSet publishes plain whitelists and this backend
reads them. Whitelisting is the point: query parameters name real database
columns, so an open-ended implementation would let a client filter or order by
any field on the model, including ones it cannot read.

Supported query parameters::

    ?search=laptop                     OR icontains across search_fields
    ?ordering=-price                   single field, must be in ordering_fields
    ?filter[brand_id]=3                exact match
    ?filter[brand_id]=3,4,5            IN match (comma-separated)
    ?filter[is_active]=true            booleans are coerced
    ?filter[created_at][from]=2026-01-01
    ?filter[created_at][to]=2026-06-30 inclusive range, date fields only
"""

import re

from rest_framework.filters import BaseFilterBackend

from django.db.models import Q

# Matches filter[field] and filter[field][from] / filter[field][to].
FILTER_PARAM = re.compile(
    r"^filter\[(?P<field>[A-Za-z0-9_]+)\](?:\[(?P<bound>from|to)\])?$"
)

TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "f", "no", "n", "off"}


def _coerce(value: str):
    """Turn a query-string value into a bool or None where it clearly is one."""
    lowered = value.strip().lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    if lowered in {"null", "none", ""}:
        return None
    return value


class WhitelistFilterBackend(BaseFilterBackend):
    """Apply search, field filters and ordering from ViewSet-declared whitelists.

    Reads four optional attributes off the view, each a sequence of field names:
    ``search_fields``, ``filter_fields``, ``ordering_fields`` and
    ``date_filter_fields``. An attribute left unset simply disables that feature
    for the view.
    """

    def filter_queryset(self, request, queryset, view):
        """Apply every supported query parameter in turn."""
        params = request.query_params
        queryset = self._search(params, queryset, view)
        queryset = self._filter(params, queryset, view)
        return self._order(params, queryset, view)

    def _search(self, params, queryset, view):
        """OR an ``icontains`` match across the view's ``search_fields``."""
        term = params.get("search", "").strip()
        fields = getattr(view, "search_fields", None)
        if not term or not fields:
            return queryset
        condition = Q()
        for field in fields:
            condition |= Q(**{f"{field}__icontains": term})
        return queryset.filter(condition)

    def _filter(self, params, queryset, view):
        """Apply ``filter[...]`` parameters against the whitelists."""
        allowed = set(getattr(view, "filter_fields", ()) or ())
        date_allowed = set(getattr(view, "date_filter_fields", ()) or ())
        if not allowed and not date_allowed:
            return queryset

        for key in params:
            match = FILTER_PARAM.match(key)
            if not match:
                continue
            field, bound = match["field"], match["bound"]
            raw = params.get(key, "").strip()
            if raw == "":
                continue

            if bound:
                if field not in date_allowed:
                    continue
                lookup = "gte" if bound == "from" else "lte"
                # __date compares the calendar day, so a "to" bound includes
                # everything that happened on that date.
                queryset = queryset.filter(**{f"{field}__date__{lookup}": raw})
                continue

            if field not in allowed:
                continue
            if "," in raw:
                values = [_coerce(part) for part in raw.split(",") if part.strip()]
                queryset = queryset.filter(**{f"{field}__in": values})
            else:
                value = _coerce(raw)
                if value is None:
                    queryset = queryset.filter(**{f"{field}__isnull": True})
                else:
                    queryset = queryset.filter(**{field: value})
        return queryset

    def _order(self, params, queryset, view):
        """Order by a whitelisted field, falling back to the view's default."""
        allowed = set(getattr(view, "ordering_fields", ()) or ())
        requested = params.get("ordering", "").strip()
        field = requested.lstrip("-")
        if requested and field in allowed:
            return queryset.order_by(requested)
        default = getattr(view, "ordering", None)
        return queryset.order_by(*default) if default else queryset

    def get_schema_operation_parameters(self, view):
        """Advertise the supported parameters to drf-spectacular."""
        parameters = []
        if getattr(view, "search_fields", None):
            parameters.append(
                {
                    "name": "search",
                    "required": False,
                    "in": "query",
                    "description": "Case-insensitive search across: "
                    + ", ".join(view.search_fields),
                    "schema": {"type": "string"},
                }
            )
        if getattr(view, "ordering_fields", None):
            parameters.append(
                {
                    "name": "ordering",
                    "required": False,
                    "in": "query",
                    "description": "Order by one of: "
                    + ", ".join(view.ordering_fields)
                    + ". Prefix with '-' to reverse.",
                    "schema": {"type": "string"},
                }
            )
        for field in getattr(view, "filter_fields", ()) or ():
            parameters.append(
                {
                    "name": f"filter[{field}]",
                    "required": False,
                    "in": "query",
                    "description": "Exact match, or comma-separated for IN.",
                    "schema": {"type": "string"},
                }
            )
        return parameters
