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
| Gateway | requests, defusedxml, cryptography | GePG HTTP calls, safe XML parsing, outbound signing, and inbound signature verification. |
| Background work | Celery, Redis | Asynchronous callback processing, outbound retry scheduling, and periodic recovery. |
| Durable message state | Django ORM, PostgreSQL | Callback inbox and outbound request records; the database remains the recovery source if Redis or a worker restarts. |
| Certificate output | WeasyPrint, qrcode, Pillow | PDF rendering, verification QR codes, and image support. |

The certificate renderer loads WeasyPrint on demand. Its native system
dependencies are needed for PDF rendering; other API endpoints can start without
them. The [operations guide](operations.md#what-to-back-up) describes the
runtime assets used by deployments.

The GePG adapter requires outbound signing and callback verification in
production. Production settings fail to start when the signing key, GePG public
certificate, or registered `GEPG_COM`/`GEPG_ALG` header values are missing. The
callback endpoints persist verified messages before acknowledging them, and
Celery workers process the inbox and retry exact persisted outbound requests.
See the [GePG integration guide](../gepg/README.md) for protocol behavior and
the [deployment guide](../deployment.md) for worker and Redis setup.

## Development and checks

| Area | Tools |
| --- | --- |
| Environment and dependencies | `uv`, `uv.lock` |
| Background processing | Celery workers and Celery Beat, backed by Redis |
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
- Callback delivery is backed by a PostgreSQL inbox and Celery processing;
  outbound transport retries use persisted payloads with bounded exponential
  backoff. Reconciliation applies payment transactions through the same
  idempotent settlement path as notifications.
