# TGC Service - API

The Tanzania Gemmological Centre's stone-certification system, as a REST API.

A customer brings stones in; they are registered and typed, billed through the
GePG government payment gateway, identified by a gemmologist once the bill is
settled, and finally certified with a publicly verifiable certificate.

```
received -> billed -> paid -> findings -> finalized -> certified
```

Each arrow is a service with its own guard, and each stage has a worklist that
is the queue someone actually works from. The React client lives alongside this
repository in `TGC-SERVICE-FRONTEND`.

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

Demo accounts are `<role>@tgc.com` with the password printed by `seed`, for each
of `superadmin`, `administrator`, `receptionist`, `gemmologist` and `accountant`.

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
| [Domain questions](docs/domain/domain-questions.md) | Business decisions — settled, and still open |
| [Project structure](docs/engineering/project-structure.md) | Every app and layer, and what belongs in each |
| [Diagrams](docs/diagrams/README.md) | Request flows, drawn — start here if you prefer pictures |
| [API lifecycle](docs/engineering/api-lifecycle.md) | A request traced from URL to response |
| [Testing the API](docs/engineering/testing-the-api.md) | Swagger, `api.http`, the query contract, the test suite |
| [Permissions](docs/engineering/permissions.md) | Roles, permissions, module gates, workflow verbs |
| [GePG integration](docs/gepg/README.md) | The payment gateway, and the gaps in it |
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
  gems/            L2 - domain enums and the stone reference tables
  orders/          L3 - customers, orders, stones, status trail
  billing/         L4 - bills, payments, the GePG gateway
  identification/  L4 - gemmological findings
  certificates/    L5 - certificates and public verification
docs/              engineering, domain and GePG documentation
api.http           a runnable request collection for the whole pipeline
```

Apps are listed in dependency-layer order. Imports point downward only: an app
may import from a lower layer, never from the same layer or a higher one.
