# Tech stack

Every dependency, what it does, and why it was chosen over the alternative.
Versions are the floors declared in `pyproject.toml`; `uv.lock` pins the exact
resolved graph.

## Runtime

| Component | Version | Support window |
| --- | --- | --- |
| Python | 3.13 | Security fixes until October 2029 |
| Django | 5.2 LTS | Extended support until April 2028 |
| PostgreSQL | 14+ | Any currently supported release |

Django 5.2 is a Long-Term Support release. A template is copied and then left
alone for years, so the three-year window matters more here than the newest
feature set — a project started from this one should not need a framework
upgrade in its first eighteen months.

## Core dependencies

| Package | Version | Role |
| --- | --- | --- |
| `django` | 5.2.17 | Framework, ORM, migrations, auth primitives |
| `djangorestframework` | 3.18.0 | Serialisation, ViewSets, routers, permissions |
| `djangorestframework-simplejwt` | 5.5.1 | JWT access/refresh tokens with blacklisting |
| `django-filter` | 26.1 | Filter backend infrastructure |
| `drf-spectacular` | 0.30.0 | OpenAPI 3 schema, Swagger UI, ReDoc |
| `django-auditlog` | 3.4.1 | Field-level change history |
| `django-environ` | 0.14.0 | Typed environment variable parsing |
| `django-cors-headers` | 4.9.0 | Cross-origin access for browser clients |
| `psycopg[binary]` | 3.3.5 | PostgreSQL driver |
| `pillow` | 12.3.0 | Image handling for `ImageField` |
| `requests` | 2.34.2 | Outbound HTTP to the GePG gateway |
| `cryptography` | 50.0.1 | PKCS#12 loading and SHA256withRSA signing for GePG |
| `defusedxml` | 0.7.1 | Parsing untrusted XML from the payment callbacks |

### Why each one

**`defusedxml`** — not a preference, a requirement. The payment-notification
webhook parses XML posted by anyone who can reach the URL, and Python's own
`xml.etree.ElementTree` is documented as unsafe against maliciously constructed
input: an entity-expansion payload a few hundred bytes long can exhaust the
process. `defusedxml` is a drop-in replacement that refuses those constructs and
raises instead, which the service turns into a `7102` acknowledgement.

**`cryptography`** — loads the PKCS#12 key and signs outbound payloads. Note the
signing path **fails open**: a missing key logs an error and sends the request
unsigned rather than refusing. That is inherited behaviour and is on the
follow-up list, not a decision.

**`djangorestframework`** — the default choice for Django APIs, and the reason
is ecosystem rather than elegance. Authentication, permissions, pagination,
filtering and schema generation all assume DRF's extension points, so choosing
anything else means giving up most of that.

**`djangorestframework-simplejwt`** — stateless access tokens with a refresh
flow. `ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION` are both on, and
the `token_blacklist` app is installed, which is what makes logout and
"revoke every other session" possible. Without the blacklist app a JWT cannot be
revoked at all before it expires.

**`django-filter`** — installed for its infrastructure, though the project's
list endpoints go through the custom `WhitelistFilterBackend` in
`apps/core/filters.py` instead. That backend reads plain whitelists off the
ViewSet rather than requiring a `FilterSet` class per model, which suits a
template where most endpoints filter on a handful of obvious columns.

**`drf-spectacular`** — generates OpenAPI 3 from the serializers and views that
already exist, so the schema cannot drift from the implementation the way a
hand-maintained document does.

**`django-auditlog`** — model change history with field-level diffs. Registration
is automatic: `apps/core/audit.py` walks the app registry and registers every
concrete `BaseModel` subclass, so a new model is audited the moment it inherits
the base.

**`django-environ`** — typed reads (`env.int`, `env.bool`, `env.db`) rather than
`os.environ` string-wrangling, and `env.db()` parses a `DATABASE_URL` into
Django's `DATABASES` dict in one line.

**`django-cors-headers`** — a browser refuses a cross-origin API call unless
the server says otherwise, so any SPA on a different host or port needs this.
`CORS_ALLOWED_ORIGINS` is read from the environment and defaults to empty, so a
misconfigured deployment blocks requests rather than accepting them from
anywhere; development sets `CORS_ALLOW_ALL_ORIGINS` instead. Credentials are off
because the JWT travels in the `Authorization` header rather than a cookie.

**`psycopg[binary]`** — psycopg **3**, not the legacy `psycopg2`. Version 3 is
the actively developed line, with native async support and better `JSONField`
handling. The `[binary]` extra ships prebuilt wheels, so no local C toolchain is
needed.

## Development dependencies

| Package | Version | Role |
| --- | --- | --- |
| `pytest` | 9.1.1 | Test runner |
| `pytest-django` | 4.14.0 | Database fixtures, settings integration |
| `pytest-cov` | 7.1.0 | Coverage measurement |
| `factory-boy` | 3.3.3 | Test data factories, reused by `seed` |
| `ruff` | 0.16.6 | Linter, formatter, import sorter, docstring checker |
| `pre-commit` | 4.6.2 | Git hook management |
| `django-debug-toolbar` | 8.0.0 | Local SQL and request inspection |
| `django-stubs` | 6.1.0 | Type stubs for Django |
| `djangorestframework-stubs` | 3.18.1 | Type stubs for DRF |

**`ruff`** replaces what used to be four separate tools — `black`, `flake8`,
`isort` and `pydocstyle` — with one binary and one config block. Enabled rule
families are listed in `pyproject.toml`, each annotated with what it enforces.
Notably `D` runs with `convention = "google"`, so docstring format is checked
automatically rather than in review.

**`factory-boy`** factories live in `apps/<app>/tests/factories.py` and are
imported by the `seed` management command. One definition serves both the
test suite and demo data, so the two cannot disagree about what a valid row
looks like.

## Tooling

| Concern | Choice |
| --- | --- |
| Dependency management | `uv` with a committed `uv.lock` |
| Configuration | `pyproject.toml` — ruff, pytest and coverage in one file |
| Git hooks | `pre-commit`, with `manage.py check` on push only |
| CI | GitHub Actions — lint, deploy security check, migration check, migrate against PostgreSQL, test |

`uv` resolves and installs an order of magnitude faster than pip, and the
lockfile means every clone and every CI run installs precisely the same graph.

## Rejected alternatives

The reasoning matters more than the verdict, since a future project may weigh
these differently.

| Considered | Chosen instead | Why |
| --- | --- | --- |
| `django-ninja` | DRF | Better developer experience and built-in OpenAPI, but a far smaller ecosystem and weaker transferable skill |
| `django-rest-knox` | `simplejwt` | Knox's multiple revocable DB tokens are the closer match to Laravel Sanctum, but JWT is the industry default for SPA backends |
| DRF `TokenAuthentication` | `simplejwt` | One token per user — no multi-device sessions, no selective revocation |
| `django-guardian` | Django `Group`/`Permission` | Object-level permissions solve a problem this template does not have |
| Custom role/permission tables | Django `Group`/`Permission` | Reimplements what Django ships, and loses admin integration |
| `django-safedelete` | Custom `SoftDeleteModel` | Roughly 80 lines, no dependency, and fully understood by whoever maintains it |
| `psycopg2` | `psycopg` 3 | v2 is maintenance-only |
| `poetry` / `pip-tools` | `uv` | Faster, and now the direction the ecosystem is moving |
| `black` + `flake8` + `isort` | `ruff` | One tool, one config, materially faster |
| Django `TestCase` | `pytest` | Function-based tests, better fixtures, far better failure output |
| Custom response envelope | DRF defaults | A bespoke envelope means every generated client and schema tool needs special-casing |

## Absent by design

Not oversights — each is a decision to add per project rather than carry in the
template.

| Not included | Add when |
| --- | --- |
| Celery / background jobs | Something genuinely needs to run outside the request cycle |
| Redis / caching | A measured bottleneck exists, not before |
| Email and password reset | The project has a mail provider and a verified sender |
| Channels / WebSockets | Real-time delivery is an actual requirement |
| Docker | The deployment target is known |
| Multi-tenancy | The tenancy model is decided — it is very hard to retrofit, so decide early |
| Sentry or APM | There is production traffic to observe |

## Upgrade notes

- **Django 6.0** is available but is not an LTS. Stay on 5.2 unless a specific
  6.x feature is needed; the next LTS is the natural upgrade target.
- **`AUTH_USER_MODEL` cannot be changed** after the first migration without
  unpicking foreign keys across every table. Settle the user model before
  running `migrate` for the first time.
- **Renew the lockfile deliberately**, with `uv lock --upgrade`, then run the
  suite. Do not let it drift as a side effect of adding an unrelated package.
