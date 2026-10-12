# Backend stack

Dependency versions and the supported Python range are maintained in
[`pyproject.toml`](../../pyproject.toml); `uv.lock` records the resolved
environment. Update those files when changing dependencies rather than copying
version numbers into this guide.

## Runtime components

| Area | Main packages | Use |
| --- | --- | --- |
| API and persistence | Django, Django REST Framework, psycopg | Models, migrations, serializers, viewsets, permissions, and PostgreSQL access. |
| Authentication | Simple JWT | Access and refresh tokens, refresh-token rotation and blacklisting, plus project session checks. |
| Filtering and schema | django-filter, drf-spectacular | Request filtering and generated OpenAPI documentation. |
| Audit and configuration | django-auditlog, django-environ | Model-change history and typed environment settings. |
| Gateway | requests, defusedxml, cryptography | GePG HTTP calls, safe XML parsing, and optional outbound signing. |
| Certificate output | WeasyPrint, qrcode, Pillow | PDF rendering, verification QR codes, and image support. |

The certificate renderer loads WeasyPrint on demand. Its native system
dependencies are needed for PDF rendering; other API endpoints can start without
them. The [operations guide](operations.md#what-to-back-up) describes the
runtime assets used by deployments.

The GePG adapter signs outbound messages only when configured. Signing currently
logs and continues with the unsigned XML for missing or invalid key material;
inbound callbacks do not verify signatures. See the
[integration limitations](../gepg/README.md#current-limitations).

## Development and checks

| Area | Tools |
| --- | --- |
| Environment and dependencies | `uv`, `uv.lock` |
| Tests | `pytest`, `pytest-django`, `factory-boy` |
| Lint, format, and docstrings | Ruff, configured in `pyproject.toml` |
| CI | GitHub Actions workflows in `.github/workflows/` |

Common setup, test, and schema commands are in the [backend README](../../README.md).
The committed CI workflows define the automated checks; verify those files when
updating this summary.

## Project-specific choices

- DRF is integrated throughout the API for authentication, permission checks,
  filtering, pagination, and OpenAPI generation.
- Django groups and permissions provide role-based access; the project adds
  role-rank checks for account and role administration.
- Soft deletion and audit logging are implemented in shared model behavior.
  These are project conventions, not third-party packages.
- Billing callbacks are request-driven. Explicit retry actions exist, but there
  is no background job runner or scheduled GePG retry worker.
