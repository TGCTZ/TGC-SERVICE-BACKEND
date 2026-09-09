# API request lifecycle

One `GET /api/v1/stones/?search=ruby&ordering=label` traced end to end.

> For rendered flowcharts of each stage, see [docs/diagrams](../diagrams/README.md).
> This page is the same material as text, for quick scanning.

```
HTTP request
     |
     v
[1] MIDDLEWARE (config/settings/base.py)
     |   SecurityMiddleware, SessionMiddleware, CommonMiddleware, CsrfViewMiddleware
     |   AuthenticationMiddleware      -> populates request.user
     |   CurrentUserMiddleware         -> binds that user to a contextvar
     |   AuditlogMiddleware            -> records the actor for change history
     v
[2] URL RESOLUTION (config/urls.py -> apps/orders/urls.py)
     |   DefaultRouter maps "stones/" + GET to StoneViewSet.list
     v
[3] AUTHENTICATION (JWTAuthentication)
     |   Decodes the Bearer token, resolves the user, or raises 401
     v
[4] PERMISSIONS (StrictModelPermissions)
     |   GET requires orders.view_stone, or raises 403
     v
[5] QUERYSET (StoneViewSet.queryset + SoftDeleteViewSetMixin.get_queryset)
     |   Stone.objects excludes soft-deleted rows by default
     |   created_by / updated_by joined here, for the audit labels
     |   select_related / prefetch_related declared up front
     |   with_trashed / only_trashed switch to all_objects
     v
[6] FILTER BACKEND (apps/core/filters.py)
     |   search   -> OR icontains across search_fields
     |   filter[] -> exact / IN / date range, against filter_fields
     |   ordering -> validated against ordering_fields
     v
[7] PAGINATION (apps/core/pagination.py)
     |   page / page_size, capped at 100
     v
[8] SERIALIZER (apps/orders/serializers.py)
     |   Model instances -> primitives; nested *_detail objects for reads
     v
[9] RESPONSE
     {"count": 42, "next": "...", "previous": null, "results": [...]}
```

## Where a write differs

Steps 1-4 are identical. From there:

```
[5] SERIALIZER.is_valid()      -> 400 with DRF's field-keyed error shape
[6] VIEW delegates to a SERVICE (for anything beyond a plain save)
[7] SERVICE raises ServiceError on a business-rule violation
[8] apps/core/handlers.py maps ServiceError -> 400
[9] MODEL.save() stamps created_by / updated_by from the contextvar
[10] django-auditlog records the field-level diff
```

## Where a workflow verb differs

A business action is a `POST` to its own route, not a field write, so that the
service runs and the change is recorded:

```
POST /api/v1/stones/1/transition/   {"to_status": "billed", "note": "..."}
     |
[4]  ActionPermissions -> orders.transition_stone, not add_stone
     |
[5]  VIEW: get_object(), call the service, serialize. Four lines.
     |
[6]  SERVICE transition_stone() writes the StatusHistory row
     v
     200 with the updated stone
```

`Stone.status` is read-only on the serializer for the same reason: a `PATCH`
that moved it would leave no trace of who moved it or when. The same pattern
carries `finalize`, `generate`, `revoke` and the four worklists.

## Where errors are shaped

`apps/core/handlers.py` is the single funnel:

| Raised | Becomes |
|---|---|
| `ServiceError` | 400, `{"detail": "..."}` |
| Django `ValidationError` | 400, field-keyed |
| `Http404` | 404 |
| `IntegrityError` | 400, logged as a warning |
| Anything unhandled | 500, `{"detail": "A server error occurred."}`, logged with traceback |

Internals never reach the client: an unrecognised exception is logged in full
and reported as a bare 500.

## The soft-delete wrinkle

`DELETE /api/v1/customers/1/` does not remove a row - it stamps `deleted_at`.
django-auditlog therefore sees an ordinary `UPDATE`, which would make a deletion
indistinguishable from any other field change in the history. `SoftDeleteViewSetMixin`
writes an explicit `LogEntry` for both delete and restore to compensate.
