# Testing the API

Three ways to exercise an endpoint by hand, the query contract every list route
shares, and the automated suite underneath.

Everything below assumes a running server against a seeded database:

```bash
uv run python manage.py migrate
uv run python manage.py setup_roles
uv run python manage.py seed
uv run python manage.py runserver
```

`seed` creates one account per role — `<role>@tgc.com`, password `1234567890` —
and enough orders at different stages that every worklist has something in it.

---

## 1. Swagger UI — for finding out what exists

<http://localhost:8000/api/schema/swagger-ui/>

Generated from the code by `drf-spectacular`, so it cannot drift from what the
API actually does. Every path, parameter and response shape is there.

To call anything but the health probes you need a token first:

1. `POST /api/v1/auth/login/` → **Try it out** → send
   `{"email": "administrator@tgc.com", "password": "1234567890"}`
2. Copy `access` out of the response
3. **Authorize** (top right) → paste `Bearer <token>` → Authorize

Best for discovering an endpoint. Poor for repeating a flow: the access token
expires after 60 minutes and you re-paste it by hand each time.

ReDoc is at `/api/schema/redoc/` if you prefer reading to clicking, and the raw
OpenAPI document at `/api/schema/`.

---

## 2. `api.http` — for the flows you run repeatedly

[`api.http`](../../api.http) in the project root is a request collection that
runs in PyCharm and IntelliJ out of the box — click the green arrow beside any
request — and in VS Code with the **REST Client** extension.

**Run "Sign in" first.** It captures the token into a client variable that every
later request reuses:

```
> {%
    client.global.set("access", response.body.access);
    client.global.set("refresh", response.body.refresh);
%}
```

So there is no token to copy, and — on Windows — no shell quoting to get wrong.

The file walks the whole pipeline in order, chaining ids as it goes: sign in →
reference data → soft delete and restore → customer → order → register stones →
transition → generate a bill → the GePG callbacks → findings and finalize →
audit and health. Run it top to bottom and you have exercised the system end to
end — 35 requests, all green.

It is **re-runnable**, which took three fixes worth knowing about because each
one is a trap the API itself sets:

- Unique columns carry a `{{$timestamp}}`, so a second run does not collide with
  the first on `name` or `phone`.
- Stones are registered against the stone type the collection created itself,
  never a hardcoded id — ids drift as rows come and go.
- The payment notification carries a **per-run transaction id**, captured once
  at sign-in as `{{run}}`. A fixed `trx_id` makes every run after the first look
  like a *redelivery* to the idempotency guard: the payment is quietly
  re-pointed at the new bill and the settlement is never recomputed, so the bill
  stays `pending` while showing the full amount paid. The two notification
  requests deliberately share one `{{run}}`, which is what proves the guard
  works.

A request marked `# @expect 400` is a negative test — the lock, the cap — where
a 400 is the pass condition.

### Testing a role

Change one line at the top and re-run:

```
"email": "receptionist@tgc.com"
```

Then watch what starts returning 403. This is the fastest way to check the role
matrix, and it is worth doing after any change to
[`apps/users/roles.py`](../../apps/users/roles.py) — a permission that was never
granted to anyone fails silently until someone opens the screen.

---

## 3. `curl` — for one-offs

Fine for a single request. Two Windows-specific traps:

- Use `curl.exe`, not `curl`. In PowerShell `curl` can be an alias for
  `Invoke-WebRequest`, which takes entirely different flags.
- Wrap JSON in **single** quotes. PowerShell strips the backslash-escaped double
  quotes that work in `cmd.exe`, and the API then reports a JSON parse error at
  column 2 — which looks like a payload bug rather than a shell one.

```bash
curl.exe -s -X POST http://localhost:8000/api/v1/auth/login/ -H "Content-Type: application/json" -d '{"email":"administrator@tgc.com","password":"1234567890"}'
```

---

## Authentication

```
POST /api/v1/auth/login/     {email, password}  -> {access, refresh, user}
POST /api/v1/auth/refresh/   {refresh}          -> {access, refresh}
POST /api/v1/auth/logout/    {refresh}          -> 205
GET  /api/v1/auth/me/                           -> the user, roles, permissions
```

Send the access token as `Authorization: Bearer <access>`.

> **Refresh tokens rotate.** Every refresh returns a *new* refresh token and
> blacklists the one you sent. A client that stores only the new access token
> keeps working for one more access lifetime and then fails on the *following*
> refresh — an hour later, seemingly at random. Store both.

`/api/v1/auth/me/` is the endpoint to reach for when a screen is unexpectedly
empty: it returns the caller's roles and every permission they hold, which is
exactly what the UI gates on.

---

## The query contract

Every list endpoint shares it, driven by
[`apps/core/filters.py`](../../apps/core/filters.py) and
[`apps/core/pagination.py`](../../apps/core/pagination.py). A parameter that is
not whitelisted on the ViewSet is ignored rather than erroring.

| Parameter | Meaning |
|---|---|
| `?search=ruby` | Case-insensitive OR across the view's `search_fields` |
| `?ordering=name` / `?ordering=-price` | One field, checked against `ordering_fields` |
| `?filter[category]=precious` | Exact match |
| `?filter[category]=precious,diamond` | `IN` match |
| `?filter[is_active]=true` | Coerced only on a real boolean column |
| `?filter[species]=null` | `IS NULL` |
| `?filter[created_at][from]=2026-01-01` | Inclusive date range, `date_filter_fields` only |
| `?page=2&page_size=50` | Paging; `page_size` caps at 100 |
| `?with_trashed=1` / `?only_trashed=1` | Include or isolate soft-deleted rows |

Responses use DRF's envelope:

```json
{ "count": 42, "next": "...", "previous": null, "results": [] }
```

### Relations come back twice

A writable id and a read-only expanded object:

```json
{ "stone_type": 3, "stone_type_detail": { "id": 3, "name": "Ruby", "price": "125000.00" } }
```

Write the id; read the `_detail`. This is Django's convention, not Laravel's —
there is no `stone_type_id` field.

---

## Soft delete and restore

Nothing is really deleted. `DELETE` stamps `deleted_at`, and the row is
reachable again through `?only_trashed=1` and `POST {id}/restore/`.

```
DELETE /api/v1/stone-types/7/           -> 204
GET    /api/v1/stone-types/?only_trashed=1
POST   /api/v1/stone-types/7/restore/   -> 200
```

Restore is a `POST`, so it requires `add_<model>` — see
[permissions.md](permissions.md).

---

## Workflow actions

Business verbs are `POST` actions rather than field writes, so each one goes
through its service and leaves an audit trail:

```
POST /api/v1/orders/{id}/stones/       register the next stone (labels A, B, C…)
POST /api/v1/stones/{id}/transition/   {to_status, note}
POST /api/v1/bills/generate/           {order}
GET  /api/v1/orders/worklist-registration/
GET  /api/v1/bills/worklist/
```

Two things worth trying, because they are the guards most likely to regress:

- Register more stones than `order.stone_count` — the extra call must return
  **400** with the cap message, not create a stone.
- `PATCH /api/v1/stones/{id}/` with `{"status": "certified"}` — it must return
  200 and leave the status **unchanged**. The field is read-only precisely so a
  status cannot move without a `StatusHistory` row naming who moved it.

---

## The GePG callbacks

Two server-to-server XML endpoints, mounted **outside** `/api/v1/` because their
URLs are registered with the gateway and must survive an API version bump:

```
POST /gepg/payments/notification/   pmtSpNtfReq  -> signed 7101 / 7102 ack
POST /gepg/bill/response/           billSubRes   -> signed ack
```

They take **no authentication** — the gateway has no credentials — and they
answer in XML on every path, including failure. `api.http` has ready-made
payloads for all three cases worth checking:

1. A valid notification settles the bill and moves every stone to `paid`.
2. The **same notification sent twice** must leave exactly one `Payment` row and
   one history entry. GePG redelivers until acknowledged, so without the
   `trx_id` guard a retry would double-count.
3. A malformed body must still return a well-formed `7102`. An error page here
   would make the gateway retry forever.

Set `GEPG_SIMULATE=True` in `.env` to work offline: bill submission skips the
network and returns a fake control number.

```bash
uv run python manage.py simulate_payment BILL-2026-0004
```

settles a bill by feeding a fake notification through the *real* handler, so the
whole path is exercised.

> **Known gap:** nothing verifies that a request actually came from GePG.
> `GEPG_PUBLIC_CERT_PATH` is configured but never read, so a forged
> `pmtSpNtfReq` posted to this URL will mark a bill paid. Carried over from the
> system being ported; the first follow-up to close.

---

## The automated suite

```bash
uv run pytest                     # everything
uv run pytest apps/billing        # one app
uv run pytest -k transition       # by name
uv run pytest --cov               # with coverage
uv run pytest -x -vv              # stop at the first failure, verbose
```

Fixtures in [`conftest.py`](../../conftest.py):

| Fixture | What it gives you |
|---|---|
| `api_client` | An unauthenticated DRF client |
| `user` | A user with no roles at all |
| `admin_user` | A user holding `administrator` |
| `viewer_user` | A user holding `receptionist` — the least privileged station |
| `roles` | Runs `setup_roles`, so the matrix exists |
| `auth_client` | A **factory**: `auth_client(admin_user)` returns a credentialed client |

Every app's `tests/factories.py` is shared with `manage.py seed`, so demo data
and test data can never disagree about what a valid row looks like.

Conventions the suite follows are in [conventions.md](conventions.md) — module
level `pytestmark = pytest.mark.django_db`, plain functions named for the
behaviour, one behaviour per test, and a query-count assertion on every list
endpoint.

---

## When something looks wrong

| Symptom | First thing to check |
|---|---|
| `404` on an endpoint you just wrote | **Is the running server stale?** A `--noreload` server started before your app existed keeps serving the old URLconf. Check its age before you check your URLs. |
| `401` | No or expired token. Re-run Sign in. |
| `403` | Authenticated but unauthorised. `GET /api/v1/auth/me/` shows what the caller actually holds. |
| `400` with a plain `detail` string | A `ServiceError` — a business rule refused it. The message is the rule. |
| `400` keyed by field | Serializer validation. |
| `405` | The route exists but the verb does not, e.g. `PATCH` on a read-only ViewSet. |
| Empty list where rows should be | A `filter[...]` naming a field that is not whitelisted is **ignored**, not rejected. Check the ViewSet's `filter_fields`. |
| `port is already in use` | An orphaned server. `Get-NetTCPConnection -LocalPort 8000 -State Listen \| ForEach-Object { Stop-Process -Id $_.OwningProcess }` |

The Django console log is the fastest triage tool of all: it prints every
request with its status, which immediately separates "never reached the server"
from "reached it and was refused".
