# Query layer

One filter backend serves every list endpoint. Instead of a `FilterSet` class
per model, each ViewSet publishes four plain whitelists and
`apps/core/filters.py` reads them.

## Composition order

```mermaid
flowchart TD
    VS["ViewSet.get_queryset()"] --> TRASH{"trashed flags"}

    TRASH -->|"only_trashed=1"| ONLY["all_objects.filter(deleted_at NOT NULL)"]
    TRASH -->|"with_trashed=1"| WITH["all_objects.all()"]
    TRASH -->|neither| LIVE["objects — live rows only"]

    ONLY --> BACKEND
    WITH --> BACKEND
    LIVE --> BACKEND

    BACKEND["WhitelistFilterBackend.filter_queryset()"]
    BACKEND --> S["_search"]
    S --> F["_filter"]
    F --> O["_order"]
    O --> PAGE["StandardPagination"]
    PAGE --> SQL[("single SQL query<br/><i>evaluated only here</i>")]

    style VS stroke:#4d90d9,stroke-width:2px
    style TRASH stroke:#d99a2b,stroke-width:2px
    style SQL stroke:#3fa860,stroke-width:2px
```

Trashed handling lives in the **ViewSet**, not the backend, because switching
managers has to happen before the view attaches its `select_related` and
`prefetch_related` — which the backend never sees.

Everything above is lazy. No query runs until pagination slices the queryset, so
the three stages compose into one statement.

## The four whitelists

```mermaid
flowchart LR
    subgraph declared["Declared on the ViewSet"]
        SF["search_fields"]
        FF["filter_fields"]
        OF["ordering_fields"]
        DF["date_filter_fields"]
    end

    subgraph params["Accepted query parameters"]
        P1["?search=laptop"]
        P2["?filter[stone_type]=3<br/>?filter[stone_type]=3,4,5<br/>?filter[is_active]=true"]
        P3["?ordering=-price"]
        P4["?filter[created_at][from]=2026-01-01<br/>?filter[created_at][to]=2026-06-30"]
    end

    SF --> P1
    FF --> P2
    OF --> P3
    DF --> P4

    style declared stroke:#4d90d9,stroke-width:2px
    style params stroke:#3fa860,stroke-width:2px
```

Whitelisting is the point. Query parameters name real database columns, so an
open-ended implementation would let a client filter or order by **any** field on
the model — including ones it has no business reading.

## Per-parameter handling

```mermaid
flowchart TD
    P["query parameter"] --> MATCH{"matches<br/>filter[field] pattern?"}
    MATCH -->|no| SKIP["ignored"]
    MATCH -->|yes| BOUND{"has [from] or [to]?"}

    BOUND -->|yes| DATEOK{"field in<br/>date_filter_fields?"}
    DATEOK -->|no| SKIP
    DATEOK -->|yes| RANGE["field__date__gte / __lte<br/><i>calendar day, so 'to' is inclusive</i>"]

    BOUND -->|no| ALLOWED{"field in<br/>filter_fields?"}
    ALLOWED -->|no| SKIP
    ALLOWED -->|yes| COMMA{"value contains<br/>a comma?"}

    COMMA -->|yes| IN["field__in = [coerced values]"]
    COMMA -->|no| NULLQ{"value is<br/>null / none / empty?"}
    NULLQ -->|yes| ISNULL["field__isnull = True"]
    NULLQ -->|no| EXACT["field = coerced value"]

    style P stroke:#4d90d9,stroke-width:2px
    style MATCH stroke:#d99a2b,stroke-width:2px
    style BOUND stroke:#d99a2b,stroke-width:2px
    style DATEOK stroke:#d99a2b,stroke-width:2px
    style ALLOWED stroke:#d99a2b,stroke-width:2px
    style COMMA stroke:#d99a2b,stroke-width:2px
    style NULLQ stroke:#d99a2b,stroke-width:2px
    style SKIP stroke:#d9534f,stroke-width:2px
```

An un-whitelisted parameter is **ignored, not rejected**. A stricter design
would 400 on an unknown filter; ignoring keeps old clients working after a field
is removed. The trade-off is that a typo in a filter name silently returns
unfiltered data — worth knowing when debugging "why is this returning everything".

Values are coerced: `true`/`false`/`1`/`0`/`yes`/`no` become booleans, and
`null`/`none` become an `IS NULL` lookup.

## Ordering

```mermaid
flowchart TD
    REQ["?ordering=-price"] --> STRIP["strip leading '-'"]
    STRIP --> CHECK{"in ordering_fields?"}
    CHECK -->|yes| APPLY["order_by('-price')"]
    CHECK -->|no| DEFAULT["fall back to the<br/>ViewSet's own ordering"]

    style REQ stroke:#4d90d9,stroke-width:2px
    style CHECK stroke:#d99a2b,stroke-width:2px
    style APPLY stroke:#3fa860,stroke-width:2px
```

A default ordering always applies. Without one, PostgreSQL may return rows in
any order it likes, and pagination over an unordered set can show the same row
on two pages while omitting another entirely.

## Schema

`get_schema_operation_parameters()` advertises `search`, `ordering` and every
`filter[...]` key to drf-spectacular, so the whitelists appear in Swagger UI
rather than being undocumented tribal knowledge.
