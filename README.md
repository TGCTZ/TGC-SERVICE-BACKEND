# Django API Template

A reusable Django REST Framework starting point: authentication, role-based
access control, soft deletes, an audit trail, a whitelist-driven query layer,
OpenAPI docs and a real test suite, all working on day one.

Clone it, delete the domain apps you do not need, and start building.

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
createdb -U postgres djangoapitemplate

uv run python manage.py migrate
uv run python manage.py setup_roles
uv run python manage.py seed_demo
uv run python manage.py runserver
```

Then open <http://localhost:8000/api/schema/swagger-ui/>.

Health probes sit outside the versioned API, so they survive a version bump:

| Endpoint | Purpose |
|---|---|
| `GET /api/health/` | Liveness. Touches nothing external; 200 while the process runs. |
| `GET /api/health/ready/` | Readiness. Checks the database and pending migrations; 503 if either fails. |

Demo accounts are `<role>@example.com` with the password printed by `seed_demo`,
for each of `superadmin`, `admin`, `manager`, `editor` and `viewer`.

## Everyday commands

```bash
uv run pytest                       # run the suite
uv run pytest --cov                 # with coverage
uv run ruff check . && uv run ruff format .
uv run pre-commit install           # once per clone
uv run python manage.py setup_roles # re-apply the role matrix after editing roles.py
```

## Documentation

New to the codebase? Read them in this order.

| Document | What it covers |
|---|---|
| [Tech stack](docs/engineering/tech-stack.md) | Every dependency, and the alternatives rejected |
| [Diagrams](docs/diagrams/README.md) | Request flows, drawn — start here if you prefer pictures |
| [Project structure](docs/engineering/project-structure.md) | Every folder, and what belongs in it |
| [Conventions](docs/engineering/conventions.md) | The numbered rules this project holds itself to |
| [API lifecycle](docs/engineering/api-lifecycle.md) | A request traced from URL to response |
| [Permissions](docs/engineering/permissions.md) | How roles, permissions and gates fit together |
| [Starting a new project](docs/engineering/starting-a-project.md) | What to strip out and what to keep |

## Layout

```
config/          settings package (base/development/production/test), root urls
apps/
  core/          L1 - base models, managers, shared DRF machinery
  users/         L2 - custom user, authentication, RBAC
  audit/         L2 - activity-log and system-log read APIs
  catalog/       L3 - the product domain (the worked example)
docs/            engineering documentation
```

Apps are listed in dependency-layer order. Imports point downward only: an app
may import from a lower layer, never from the same layer or a higher one.
