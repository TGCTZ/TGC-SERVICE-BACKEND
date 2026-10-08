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
| `tests/factories.py` | `factory_boy` factories for tests and selected demo records. |
| `tests/test_*.py` | The suite. |

## The layers

`INSTALLED_APPS` lists local apps in dependency order, annotated with their
layer. The rule is one line long and worth enforcing in review:

> Prefer dependencies on lower layers. Keep same-layer apps independent where practical; shared behavior belongs in a lower-level module. Check existing imports before applying this as a strict rule.

| Layer | App | Holds |
|---|---|---|
| L1 | `apps.core` | Base models, managers, shared DRF machinery. Imports nothing local. |
| L2 | `apps.users` | Custom user, authentication, RBAC. |
| L2 | `apps.audit` | Read-only APIs over the activity log and log file. |
| L2 | `apps.notifications` | Per-user notifications for workflow handoffs. |
| L2 | `apps.gems` | Every domain enum, and the stone reference tables. |
| L3 | `apps.orders` | Customers, orders, stones, and the stone status trail. |
| L4 | `apps.billing` | Bills, payments, and the GePG payment gateway. |
| L4 | `apps.identification` | Gemmological findings recorded against a stone. |
| L5 | `apps.certificates` | Certificates and their public verification. |
| L6 | `apps.reports` | Read-only financial and operational reports and exports. |

`apps.billing` and `apps.identification` share L4. Identification currently imports certificate services to issue and refresh snapshots; this is an existing cross-layer dependency to consider during future refactors. Billing and identification use ORM traversal (for example `stone.order.bill`) and shared enums in `apps.gems` to read each other’s state without importing each other.
