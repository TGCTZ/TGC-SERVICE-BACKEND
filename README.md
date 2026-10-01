# TGC Service - API

The Tanzania Gemmological Centre's stone-certification system, as a REST API.

A customer brings stones in; a gemmologist identifies each one's type, which
prices it; the order is billed through the GePG government payment gateway;
once settled the gemmologist records the findings; and the stone is
finally certified with a printable PDF certificate.

```
received -> under identification -> billed -> paid -> certified
         -> ready for collection -> collected
```

Identification comes *before* billing, because typing the stone is what
determines the fee. Each arrow is a service with its own guard, and each stage
has a worklist that is the queue someone actually works from.

The React client lives alongside this one, in [`../frontend`](../frontend/README.md).

## Stack

| Concern | Choice |
|---|---|
| Runtime | Python 3.13, Django 5.2 LTS |
| API | Django REST Framework |
| Auth | `djangorestframework-simplejwt` (access + refresh, blacklist on logout) |
| RBAC | Django `Group` + `Permission`, defined in code |
| Database | PostgreSQL (SQLite in tests) |
| Dependencies | `uv` with a committed lockfile |
| Docs | `drf-spectacular` (OpenAPI 3, Swagger UI, ReDoc) |
| Tests | `pytest`, `pytest-django`, `factory_boy` |
| Quality | `ruff` (lint + format + import sort), `pre-commit` |

## Quick start

Certificate PDFs are rendered by WeasyPrint, which needs system libraries
present **before** `uv sync` — a missing one raises `OSError` at import time and
takes the whole app down, not just the PDF endpoint. On Debian/Ubuntu:

```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
  libcairo2 libgdk-pixbuf-2.0-0 libffi8 shared-mime-info
```

```bash
uv sync
cp .env.example .env
uv run python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
# paste the result into SECRET_KEY in .env, then create the database:
createdb -U postgres tgcservice

uv run python manage.py migrate
uv run python manage.py setup_roles
uv run python manage.py seed
uv run python manage.py runserver
```

Then open <http://localhost:8000/api/schema/swagger-ui/>.

Health probes sit outside the versioned API, so they survive a version bump:

| Endpoint | Purpose |
|---|---|
| `GET /api/health/` | Liveness. Touches nothing external; 200 while the process runs. |
| `GET /api/health/ready/` | Readiness. Checks the database and pending migrations; 503 if either fails. |

Demo accounts are `<role>@example.com` with the password printed by `seed`, for each
of `superadmin`, `admin`, `manager`, `receptionist`, `gemmologist` and `accountant`.
For the dashboard's management statistics to have trends to show, seed a fresh
database with history instead:
`uv run python manage.py seed --orders 150 --history-months 12`.

Outside the demo data, accounts are created from the Users screen by an email and
a role - there is no sign-up. New users get a temporary password by email and
must set their own and complete their profile on first sign-in; see
[Accounts and first login](docs/engineering/accounts.md).

## Everyday commands

```bash
uv run pytest                       # run the suite
uv run pytest --cov                 # with coverage
uv run ruff check . && uv run ruff format .
uv run pre-commit install           # once per clone
uv run python scripts/check_docs.py # documentation links still resolve
uv run python manage.py setup_roles # re-apply the role matrix after editing roles.py
uv run python manage.py setup_roles --prune  # also drop roles the matrix no longer declares
```

## Documentation

New to the codebase? Read them in this order — what the system does first, then
how it is built.

| Document | What it covers |
|---|---|
| [Business workflow](docs/domain/business-workflow.md) | The stone's journey: stages, roles, status lifecycle |
| [Business decisions](docs/domain/decisions.md) | The rules behind the workflow - settled, provisional, still open |
| [Project structure](docs/engineering/project-structure.md) | Every app and layer, and what belongs in each |
| [Diagrams](docs/diagrams/README.md) | Request flows, drawn — start here if you prefer pictures |
| [API lifecycle](docs/engineering/api-lifecycle.md) | A request traced from URL to response |
| [Testing the API](docs/engineering/testing-the-api.md) | Swagger, `api.http`, the query contract, the test suite |
| [Permissions](docs/engineering/permissions.md) | Roles, the hierarchy, permissions, module gates, workflow verbs |
| [Accounts and first login](docs/engineering/accounts.md) | Staff-created accounts, the credentials email, first login, password resets |
| [GePG integration](docs/gepg/README.md) | The payment gateway, and the gaps in it |
| [Certificates](docs/engineering/certificates.md) | Snapshots, the PDF, QR verification and report numbering |
| [Management statistics](docs/engineering/analytics.md) | The dashboard's figures: what each counts, periods, currencies |
| [Reference data](docs/domain/reference-data.md) | The lookup lists, and Tanzania's regions |
| [Operations](docs/engineering/operations.md) | Configuration, email, and what to run after a deploy |
| [Conventions](docs/engineering/conventions.md) | The numbered rules this project holds itself to |
| [Adding an app](docs/engineering/adding-an-app.md) | The shape every domain app follows |
| [Tech stack](docs/engineering/tech-stack.md) | Every dependency, and the alternatives rejected |

## Layout

```
config/            settings package (base/development/production/test), root urls
apps/
  core/            L1 - base models, managers, shared DRF machinery
  users/           L2 - custom user, authentication, RBAC
  audit/           L2 - activity-log and system-log read APIs
  notifications/   L2 - per-user in-app notifications
  gems/            L2 - domain enums and the stone reference tables
  orders/          L3 - customers, orders, stones, status trail
  billing/         L4 - bills, payments, the GePG gateway
  identification/  L4 - full gemmological identification
  certificates/    L5 - certificates and their PDF documents
  analytics/       L6 - management statistics over all of the above
docs/              engineering, domain and GePG documentation
api.http           a runnable request collection for the whole pipeline
```

Apps are listed in dependency-layer order. Imports point downward only: an app
may import from a lower layer, never from the same layer or a higher one.
