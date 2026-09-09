# Project structure

Every directory, and what belongs in it. `(optional)` marks a file that many
apps will not need.

## Root

| Path | Purpose |
|---|---|
| `manage.py` | Django entry point. Defaults to `config.settings.development`. |
| `pyproject.toml` | Dependencies plus the single control panel for ruff, pytest and coverage. |
| `uv.lock` | Resolved dependency graph. Committed, so installs are reproducible. |
| `conftest.py` | Root pytest fixtures. Imports are deferred into fixture bodies because this module loads before the app registry. |
| `.env.example` | Committed template. `.env` itself is git-ignored. |
| `docs/` | Engineering and domain documentation. |

## `config/`

The settings package is named `config`, not after the project, so a new project
never has to find-and-replace a name across `manage.py`, `wsgi.py` and every
`DJANGO_SETTINGS_MODULE` reference.

| Path | Purpose |
|---|---|
| `settings/base.py` | Everything shared. Reads the environment via django-environ. |
| `settings/development.py` | Debug toolbar, browsable API, console email. |
| `settings/production.py` | HSTS, secure cookies, SSL redirect, JSON-only renderer. |
| `settings/test.py` | In-memory SQLite, MD5 hasher, throttling disabled. |
| `urls.py` | Root URLconf. Mounts each app under `/api/v1/` and the schema outside it. |

## `apps/`

Each app follows the same shape. Only `models.py`, `serializers.py`, `views.py`
and `urls.py` are load-bearing for a simple CRUD app.

| Path | Purpose |
|---|---|
| `models.py` or `models/` | Data. Promote to a package once it passes roughly 300 lines, re-exporting from `__init__.py` so import paths stay stable. |
| `serializers.py` | Validation and representation. No business logic. |
| `views.py` | Thin. Permissions, querysets and delegation to services. |
| `urls.py` | Router registrations for this app. |
| `services/` `(optional)` | Multi-step business operations. Module-level functions, keyword-only arguments, `@transaction.atomic`, raising `ServiceError`. |
| `filters.py` `(optional)` | Only if the shared whitelist backend is not enough. |
| `admin.py` `(optional)` | Django admin registration. |
| `management/commands/` `(optional)` | Operational commands. |
| `tests/factories.py` | `factory_boy` factories. Reused by `seed`. |
| `tests/test_*.py` | The suite. |

## The layers

`INSTALLED_APPS` lists local apps in dependency order, annotated with their
layer. The rule is one line long and worth enforcing in review:

> Imports point downward only. Never sideways, never up. Data shared by two apps
> in the same layer belongs one layer down, in `core`.

| Layer | App | Holds |
|---|---|---|
| L1 | `apps.core` | Base models, managers, shared DRF machinery. Imports nothing local. |
| L2 | `apps.users` | Custom user, authentication, RBAC. |
| L2 | `apps.audit` | Read-only APIs over the activity log and log file. |
| L2 | `apps.gems` | Every domain enum, and the stone reference tables. |
| L3 | `apps.orders` | Customers, orders, stones, and the stone status trail. |
| L4 | `apps.billing` | Bills, payments, and the GePG payment gateway. |
| L4 | `apps.identification` | Gemmological findings recorded against a stone. |
| L5 | `apps.certificates` | Certificates and their public verification. |

`apps.billing` and `apps.identification` sit at the same layer and must not
import one another. Where one needs the other's state - the findings queue is
gated on the bill being paid - it is reached by ORM traversal
(`stone.order.bill`) with the enum coming from `apps.gems` at L2. That is the
reason every domain enum lives in `gems` rather than beside the model it
describes.
