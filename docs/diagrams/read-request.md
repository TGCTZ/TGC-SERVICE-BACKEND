# Read request

`GET /api/v1/stones/?search=ruby&ordering=label&page_size=20`

```mermaid
flowchart TD
    REQ(["GET /api/v1/stones/<br/>Authorization: Bearer ..."]) --> MW

    MW["Middleware stack<br/><i>see middleware-stack.md</i>"]
    MW --> ROUTE["DefaultRouter<br/><b>apps/orders/urls.py</b><br/>stones/ + GET to StoneViewSet.list"]
    ROUTE --> DISPATCH["ViewSet.dispatch()"]
    DISPATCH --> INITIAL["initial()"]

    INITIAL --> AUTHN{"JWTAuthentication<br/>token valid?"}
    AUTHN -->|no| E401["401<br/>Unauthenticated"]
    AUTHN -->|yes| PERM

    PERM{"StrictModelPermissions<br/>has orders.view_stone?"}
    PERM -->|no| E403["403<br/>Permission denied"]
    PERM -->|yes| THROTTLE

    THROTTLE{"ScopedRateThrottle<br/>within rate?"}
    THROTTLE -->|no| E429["429<br/>Too many requests"]
    THROTTLE -->|yes| QS

    QS["get_queryset()<br/><b>SoftDeleteViewSetMixin</b><br/>picks objects vs all_objects"]
    QS --> EAGER["select_related: order, customer,<br/>stone_type, created_by, updated_by"]
    EAGER --> FILTER

    FILTER["WhitelistFilterBackend<br/><b>apps/core/filters.py</b>"]
    FILTER --> F1["_search — OR icontains<br/>across search_fields"]
    F1 --> F2["_filter — exact / IN / date range<br/>against filter_fields"]
    F2 --> F3["_order — validated against<br/>ordering_fields"]

    F3 --> PAGE["StandardPagination<br/>page_size capped at 100"]
    PAGE --> SER["StoneSerializer(many=True)<br/>nested *_detail objects"]
    SER --> RENDER["JSONRenderer"]
    RENDER --> OK(["200<br/>count / next / previous / results"])

    style REQ stroke:#4d90d9,stroke-width:2px
    style OK stroke:#3fa860,stroke-width:2px
    style AUTHN stroke:#d99a2b,stroke-width:2px
    style PERM stroke:#d99a2b,stroke-width:2px
    style THROTTLE stroke:#d99a2b,stroke-width:2px
    style E401 stroke:#d9534f,stroke-width:2px
    style E403 stroke:#d9534f,stroke-width:2px
    style E429 stroke:#d9534f,stroke-width:2px
```

## The three gates, in order

DRF always runs authentication, then permissions, then throttling. The ordering
is deliberate: you cannot decide what someone may do until you know who they
are, and there is no point rate-limiting a request that was going to be refused
anyway.

`DEFAULT_PERMISSION_CLASSES` is `IsAuthenticated`, so a view that forgets to
declare its own permissions **fails closed** rather than open.

## Why the eager loading appears before the filter

`select_related` and `prefetch_related` are declared on the ViewSet's
`queryset`, so they are already attached when the filter backend receives it.
Both are lazy — nothing executes until pagination slices the queryset — so the
joins compose with whatever the filter added.

Without them, serialising one page of 15 stones would issue dozens of queries
instead of a handful. `test_listing_stones_does_not_n_plus_one` asserts a
ceiling of 12 queries, so a regression fails the suite rather than quietly
slowing production.
